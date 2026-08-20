"""
工具：系统命令行执行 —— 【参考实现】

⚠️ 高危：shell=True 允许执行任意系统命令，等于把电脑交给模型。
本实现做了三层防护：
1. timeout 30 秒 —— 防止命令卡死
2. 输出截断到 2000 字符 —— 防止输出撑爆对话
3. 所有异常转成字符串返回 —— 铁律 1

仍然危险的地方（后面专门上一课安全再收口）：
- 没有命令黑名单（模型可以执行 del / shutdown 等危险命令）
- 工作目录是整个磁盘，没有沙箱
"""

import locale
import subprocess

COMMAND_TIMEOUT = 30     # 秒
MAX_OUTPUT_LEN = 2000    # 字符

# Windows 上 cmd 的输出是 GBK（cp936），不能用 utf-8 硬解码，
# 否则中文目录名/文件名会变成乱码。用系统本地编码解码：
# 中文 Windows → 'cp936'，英文 Windows → 'cp1252'，Linux → 'utf-8'
OUTPUT_ENCODING = locale.getpreferredencoding(False)


def run_command(command: str) -> str:
    """在系统命令行中执行一条命令，返回输出。"""
    try:
        result = subprocess.run(
            command,
            shell=True,              # 允许 cmd 语法（dir、type、cd 等）
            capture_output=True,
            encoding=OUTPUT_ENCODING,   # 用系统本地编码解码，避免中文乱码
            errors="replace",           # 编码出错不崩，用替换字符顶替
            timeout=COMMAND_TIMEOUT,
        )
        # 组装 stdout 和 stderr
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            if output:
                output += "\n"
            output += "[stderr] " + result.stderr
        if result.returncode != 0:
            output = f"[退出码 {result.returncode}]\n" + output

        # 截断过长输出
        if len(output) > MAX_OUTPUT_LEN:
            output = output[:MAX_OUTPUT_LEN] + \
                f"\n...[输出过长，已截断，共 {len(output)} 字符]"
        return output if output.strip() else \
            f"(命令执行成功，无输出，退出码 {result.returncode})"
    except subprocess.TimeoutExpired:
        return f"错误：命令执行超时（超过 {COMMAND_TIMEOUT} 秒）：{command}"
    except Exception as e:
        return f"错误：命令执行失败：{e}"


TOOLS = [
    {
        "name": "run_command",
        "description": "在系统命令行中执行命令并返回输出（超时30秒）。参数：command（命令字符串）",
        "func": run_command,
    },
]
