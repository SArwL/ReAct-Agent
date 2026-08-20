# ReAct Agent（学习项目）

一个基于 **ReAct（Reasoning + Acting）** 范式实现的最小化 Agent，支持调用文件 / Shell / 代码工具完成任务，带三层命令安全策略与流式思考输出。

> 学习用途项目，用于理解 Agent 的核心闭环：**思考 → 行动 → 观察**。

## 功能特性

- 🧠 **ReAct 循环**：模型反复输出 `<thought>`（思考）与 `<action>`（行动），直到给出 `<final_answer>`
- 🛠️ **三类工具**：文件操作（`file_tools`）、Shell 命令（`shell_tools`）、代码执行（`code_tools`）
- 🔒 **三层安全判定**：白名单放行 / 黑名单拒绝 / 其余人工确认（`tool/security.py`）
- 📡 **流式输出**：实时打印模型思考与执行过程，防超时
- 🛡️ **循环保护**：超过 `max_steps` 自动止损，防止烧 API 额度

## 快速开始

1. 安装依赖：

   ```bash
   pip install -r requirements.txt
   ```

2. 配置 API Key：

   ```bash
   copy setting.example.json setting.json   # Windows
   # cp setting.example.json setting.json   # macOS / Linux
   ```

   然后编辑 `setting.json`，填入你的 DeepSeek API Key（`base_url` 使用 Anthropic 兼容端点）。

3. 运行：

   ```bash
   python MyAgent.py
   ```

4. 输入你的问题，Agent 会边思考边执行工具，最后给出答案。

## 目录结构

```
.
├── MyAgent.py            # 程序入口
├── ReActAgent.py         # ReAct 循环核心逻辑
├── prompt_template.py    # 系统提示词模板
├── tool/
│   ├── file_tools.py     # 文件工具
│   ├── shell_tools.py    # Shell 工具
│   ├── code_tools.py     # 代码工具
│   ├── security.py       # 安全策略
│   └── __init__.py       # 工具统一入口
├── security.json         # 命令白/黑名单配置
├── setting.example.json  # 配置模板（复制为 setting.json 使用）
└── requirements.txt
```

## 工作原理

1. **思考**：模型输出 `<thought>` 说明推理过程
2. **行动**：模型输出 `<action>工具名({"参数": 值})</action>` 请求调用工具
3. **观察**：系统执行工具并把结果作为 `observation:` 喂回模型
4. 循环直到模型输出 `<final_answer>` 或达到 `max_steps`

```
question: 用户的问题
        ↓
   [模型] <thought>...</thought> <action>...</action>
        ↓
   [系统] observation: 工具执行结果
        ↓
   [模型] ...（继续循环）
        ↓
   [模型] <final_answer>最终答案</final_answer>
```

## 安全机制

`tool/security.py` 对每次工具调用做三层判定：

| 判定 | 行为 |
|------|------|
| `allow` | 白名单内命令，直接执行 |
| `deny` | 黑名单内命令，拒绝并让模型重新规划 |
| `ask` | 其余操作，打印概要后人工确认 |
