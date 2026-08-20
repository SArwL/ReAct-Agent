import json
import os
import platform
import re
from string import Template

import anthropic

from prompt_template import prompt_template
from tool import execute_tool, get_tools
from tool.security import classify_call, summarize_call


def extract_tag(text: str, tag: str) -> str | None:
    """提取 <tag>...</tag> 之间的内容，找不到返回 None。

    模型偶尔会漏写闭合标签（如只写 <final_answer> 不写 </final_answer>），
    此时也尽量提取到下一个标签或文本末尾，避免白白多跑一轮。
    """
    # 1) 先匹配完整闭合的标签
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.S)
    if m:
        return m.group(1).strip()
    # 2) 未闭合的情况：提取到下一个标签（<）或文本末尾
    m = re.search(rf"<{tag}>(.*?)(?=<|$)", text, re.S)
    return m.group(1).strip() if m else None


def parse_action(content: str) -> tuple[str, dict]:
    """解析 <action> 内容，返回 (工具名, 参数字典)。

    例如：
        'run_command({"command": "dir /b"})' → ('run_command', {'command': 'dir /b'})
        'get_location()'                     → ('get_location', {})
    """
    # 工具名：开头的第一个标识符（字母/下划线开头），
    # 用正则而不是 split("(") —— 因为参数 JSON 里也可能出现 "("
    name = re.match(r"\s*([A-Za-z_]\w*)", content).group(1)

    # 参数：第一个 ( 到最后一个 ) 之间的 JSON
    if "(" in content:
        args_str = content[content.find("(") + 1: content.rfind(")")].strip()
        return name, json.loads(args_str) if args_str else {}
    return name, {}


def format_tools(tools: list) -> str:
    """把工具定义列表格式化成模型能读的文本。"""
    return "\n".join(f"- {t['name']}：{t['description']}" for t in tools)


def format_files(files: list) -> str:
    """把文件列表格式化成文本。"""
    if not files:
        return "（空目录）"
    return "\n".join(f"- {f}" for f in files)


class ReActAgent:
    """目标 Agent 的容器。"""

    def __init__(self, workspace: str = None, settings_path: str = "setting.json"):
        self.workspace = workspace if workspace else os.path.join(os.getcwd(), "workspace")

        # ① 加载 LLM 配置（setting.json）并构造客户端
        with open(settings_path, encoding="utf-8") as f:
            config = json.load(f)
        self.client = anthropic.Anthropic(
            api_key=config["api_key"],
            base_url=config["base_url"],
        )
        self.model = config["model"]
        self.max_steps = config.get("max_steps", 30)   # ReAct 循环上限，防死循环烧额度

        # ② 取三个占位符所需的信息
        os_info = platform.platform()
        tools = get_tools()
        file_list = os.listdir(self.workspace)

        # 加载提示词模板，替换占位符 → 得到最终 prompt
        self.prompt = Template(prompt_template).substitute(
            operating_system=os_info,
            tool_list=format_tools(tools),
            file_list=format_files(file_list),
        )

    def run(self, user_input: str) -> str | int:
        # 用户问题前加 "question: " 前缀，与提示词示例格式保持一致
        messages = [{"role": "user", "content": f"question: {user_input}"}]

        # 最大循环次数保护：for 代替 while True，到点兜底返回（防死循环烧 API 额度）
        for step in range(1, self.max_steps + 1):
            # ① 调用 LLM（流式接口）
            # 非流式 create() 有 10 分钟硬上限：SDK 按 max_tokens 估算时长，
            # 大 max_tokens（如 100000）必然触发 "Streaming is required..." 报错。
            # 流式没有该上限，且能实时看到模型逐字输出。
            with self.client.messages.stream(
                model=self.model,
                max_tokens=100000,
                system=self.prompt,
                messages=messages,
            ) as stream:
                response = stream.get_final_message()

            """**********************************************取出LLM输出返回内容**********************************************"""

            # ② 取出文本输出（跳过 ThinkingBlock，只取 TextBlock）
            output_text = "".join(b.text for b in response.content if b.type == "text")

            # ②.5 输出被截断（撞上 max_tokens 上限）→ 残缺内容喂回，让它重新完整输出
            # 注意：DeepSeek 兼容端点截断时可能返回 "length"（原生格式）而非 "max_tokens"，两个都判
            if response.stop_reason in ("max_tokens", "length"):
                messages.append({"role": "assistant", "content": output_text})
                messages.append({"role": "user", "content":
                    "observation: 错误：你的输出被截断了（达到 max_tokens 上限），"
                    "请重新完整输出 <thought>...</thought> 和 <action>...</action> "
                    "或 <final_answer>...</final_answer>"})
                continue

            """***********************************************打印LLM思考的内容***********************************************"""

            # ③ 打印思考内容，让用户看到 agent 在想什么
            # DeepSeek 原生 thinking 块常会"抢走"思考，模型在文本里可能不写 <thought> 标签，
            # 所以：先按协议取 <thought>，取不到就回退显示 thinking 块的内容
            thought = extract_tag(output_text, "thought")
            if not thought:
                thought = "".join(getattr(b, "thinking", "") or ""
                                  for b in response.content if b.type == "thinking")
            if thought:
                print(f"🧠 思考：{thought}")

            """******************************************判断是否得到最终答案并输出答案******************************************"""

            # ④ 有 final_answer → 返回答案，循环结束
            final_answer = extract_tag(output_text, "final_answer")
            if final_answer:
                return final_answer

            """*****************************************未得出答案则调用工具进一步分析问题****************************************"""

            # ⑤ 没有 final_answer → 期望 <action>
            action_content = extract_tag(output_text, "action")
            if action_content is None:
                # 模型输出不符合协议（一个标签都没有）→ 把错误喂回，让它自己修正
                messages.append({"role": "assistant", "content": output_text})
                messages.append({"role": "user", "content":
                    "observation: 错误：输出不符合格式要求，必须包含 "
                    "<action>...</action> 或 <final_answer>...</final_answer>，请按格式重新输出"})
                continue

            try:
                tool_name, tool_args = parse_action(action_content)
            except Exception as e:
                # action 内容解析失败（如 JSON 不合法）→ 同样喂回错误，让它修正
                messages.append({"role": "assistant", "content": output_text})
                messages.append({"role": "user", "content":
                    f"observation: 错误：无法解析 action：{e}，请确保格式为 "
                    f'<action>工具名("参数": 值)</action>'})
                continue

            # ⑤.5 三层安全判定：白名单放行 / 黑名单拒绝 / 其余人工确认
            verdict, reason = classify_call(tool_name, tool_args)
            summary = summarize_call(tool_name, tool_args)

            if verdict == "deny":
                # 安全策略拒绝 → 把原因喂回模型，让它重新规划方案（循环继续）
                print(f"⛔ 安全策略拒绝：{summary}（{reason}）")
                messages.append({"role": "assistant", "content": output_text})
                messages.append({"role": "user", "content":
                    f"observation: 错误：该操作被安全策略禁止（{reason}），"
                    "请重新规划方案，改用其他允许的方式完成用户需求"})
                continue

            if verdict == "ask":
                # 其余操作 → 打印概要，人工确认
                print(f"🔧 待确认：{summary}")
                choice = input("是否执行？[y/n]：").strip().lower()
                if choice != "y":
                    return -1   # 用户拒绝 → 停止运行，返回错误码

            print(f"⚙️ 执行：{summary}")   # allow 直接执行，不弹确认
            self.observation = execute_tool(tool_name, tool_args)

            # ⑥ 把助手回复和 observation 追加进历史，继续下一轮循环
            messages.append({"role": "assistant", "content": output_text})
            messages.append({"role": "user", "content": f"observation: {self.observation}"})

        # for 走完 = 达到上限还没出结果 → 优雅兜底（止损 + 让用户知道原因）
        return (f"已用完最大循环次数（{self.max_steps} 轮），未能得到最终答案。"
                "可能原因：任务过于复杂或模型陷入循环，请换一种说法重试。")
