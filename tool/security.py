"""安全模块：工具调用的三层判定（白名单放行 / 黑名单拒绝 / 其余人工确认）。

供 ReActAgent 在 execute_tool 之前调用：
- classify_call(name, args)  → 返回 (verdict, reason)，verdict ∈ {"allow", "deny", "ask"}
- summarize_call(name, args) → 返回一行人类可读的调用概要（隐藏长内容）

策略存于 security.json（配置与代码分离）。fail-closed：配置缺失/损坏时
白名单为空集合，所有调用落入 ask/deny，绝不静默放行。
"""

import json
import os

# 项目根目录（tool/ 的上一级），保证无论 cwd 在哪都能找到配置
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECURITY_PATH = os.path.join(_ROOT, "security.json")

# 结构级禁令（安全不变量，放代码不放配置，防止误改放行）：
# 命令链 / 重定向操作符会让"命令名判断"形同虚设，如 `dir & del 文件`。
# 含这些操作符的命令判为 ask（让用户看到整条命令再决定），而非自动放行。
CHAIN_OPERATORS = ("&&", "||", "&", "|", ">", "<", "^", ";")

# 可执行文件后缀：比较时忽略，tasklist.exe 与 tasklist 视为同一命令
_EXE_SUFFIXES = (".exe", ".com", ".bat", ".cmd")


def _load_config() -> dict:
    """读取 security.json；缺失/损坏 → 空配置 + 警告（fail-closed）。"""
    try:
        with open(SECURITY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[安全] 警告：{SECURITY_PATH} 加载失败，按最保守策略运行：{e}")
        return {}


_CONFIG = _load_config()
CMD_ALLOW = {n.strip().lower() for n in _CONFIG.get("command_whitelist", [])}
CMD_DENY = {n.strip().lower() for n in _CONFIG.get("command_blacklist", [])}
TOOL_ALLOW = set(_CONFIG.get("tool_whitelist", []))
TOOL_DENY = set(_CONFIG.get("tool_blacklist", []))


def _normalize_command_name(command: str) -> str:
    """取命令名并规范化：去前导空格 → 取首词 → 去路径 → 去可执行后缀 → 转小写。

    带路径的调用（含 \\ 或 /）一律返回空串 → 不会命中白名单（默认拒绝）。
    """
    cmd = command.strip()
    if not cmd:
        return ""
    first = cmd.split()[0]
    if "\\" in first or "/" in first:
        return ""  # 只认简单命令名，不支持带路径调用
    name = first.lower()
    if name.endswith(_EXE_SUFFIXES):
        name = name.rsplit(".", 1)[0]
    return name


def classify_call(name: str, args: dict) -> tuple[str, str]:
    """对一次工具调用做三层判定，返回 (verdict, reason)。

    verdict ∈ {"allow", "deny", "ask"}；deny/ask 时 reason 给出原因。
    判定优先级：黑名单 > 白名单 > ask（同名同时出现在两张表时黑名单优先）。
    """
    if name == "run_command":
        command = args.get("command", "")
        if not command.strip():
            return "deny", "命令为空"
        for op in CHAIN_OPERATORS:
            if op in command:
                return "ask", f"命令含命令链/重定向操作符 {op!r}，需人工确认"
        cmd = _normalize_command_name(command)
        if cmd in CMD_DENY:
            return "deny", f"命令 {cmd!r} 在黑名单中，禁止执行"
        if cmd in CMD_ALLOW:
            return "allow", ""
        return "ask", f"命令 {cmd!r} 不在白名单中，需人工确认"

    # 非命令工具：按工具级黑/白名单分类，未配置的工具默认 ask
    if name in TOOL_DENY:
        return "deny", f"工具 {name} 被安全策略禁用"
    if name in TOOL_ALLOW:
        return "allow", ""
    return "ask", f"工具 {name} 需人工确认"


def summarize_call(name: str, args: dict) -> str:
    """给用户看的一行概要：显示命令/路径，隐藏长内容（文件内容、代码）。"""
    if name == "run_command":
        return f"[run_command] {args.get('command', '')}"
    if name == "read_file":
        return f"[read_file] 读取文件：{args.get('path', '')}"
    if name == "write_file":
        content = args.get("content", "")
        return f"[write_file] 写入文件：{args.get('path', '')}（内容 {len(content)} 字符，已省略）"
    if name == "run_python":
        code = args.get("code", "")
        return f"[run_python] 执行 Python 代码（{len(code)} 字符，内容省略）"
    return f"[{name}] {args}"
