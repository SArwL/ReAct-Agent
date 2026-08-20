"""
工具：执行 Python 代码 —— 【参考实现】

⚠️ 高危：让模型写代码并执行 = 任意代码执行（RCE）。
本实现加了 timeout 和输出截断，防止把电脑跑死 / 撑爆对话。

注意两个设计点：
- 用 sys.executable 而不是 "python" —— 用的是当前解释器，
  能拿到 agent 所在的 Anaconda 环境，不会踩到别的 Python
- 代码里有死循环时，timeout 会兜住，不会真的把电脑跑死
"""

import locale
import subprocess
import sys

CODE_TIMEOUT = 30        # 秒
MAX_OUTPUT_LEN = 2000    # 字符

# 与 shell_tools 同理：子进程输出在中文 Windows 上是 GBK，
# 用系统本地编码解码，避免中文乱码
OUTPUT_ENCODING = locale.getpreferredencoding(False)


def run_python(code: str) -> str:
    """执行一段 Python 代码，返回其输出。"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            encoding=OUTPUT_ENCODING,
            errors="replace",
            timeout=CODE_TIMEOUT,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            if output:
                output += "\n"
            output += "[stderr] " + result.stderr
        if len(output) > MAX_OUTPUT_LEN:
            output = output[:MAX_OUTPUT_LEN] + \
                f"\n...[输出过长，已截断，共 {len(output)} 字符]"
        return output if output.strip() else \
            f"(代码执行成功，无输出，退出码 {result.returncode})"
    except subprocess.TimeoutExpired:
        return f"错误：代码执行超时（超过 {CODE_TIMEOUT} 秒），可能有死循环"
    except Exception as e:
        return f"错误：代码执行失败：{e}"


TOOLS = [
    {
        "name": "run_python",
        "description": "执行一段 Python 代码并返回其输出（超时30秒）。参数：code（Python 代码字符串）",
        "func": run_python,
    },
]
