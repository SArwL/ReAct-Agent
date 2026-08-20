"""
tool 包：汇总所有工具，对外提供统一接口。

循环代码（react_agent.py）只需要跟这个包打交道，不需要关心具体工具：
- get_tools()    → 拿到所有工具定义，用于拼 ${tool_list} 给模型看
- execute_tool() → 按名字执行工具，返回字符串结果（就是 observation）
"""

from . import file_tools, shell_tools, code_tools

# 汇总所有模块里的 TOOLS 列表
_TOOLS = []
for _module in (file_tools, shell_tools, code_tools):
    _TOOLS.extend(getattr(_module, "TOOLS", []))


def get_tools():
    """返回所有工具定义列表（[{name, description, func}, ...]）。"""
    return _TOOLS


def execute_tool(name: str, args: dict) -> str:
    """按工具名执行工具，返回字符串结果（无论成功失败）。

    args 是 action JSON 解析出来的参数 dict，用 ** 展开成关键字参数调用。
    """
    for tool in _TOOLS:
        if tool["name"] == name:
            try:
                # 铁律 2：参数 dict 用 ** 展开成关键字参数
                result = tool["func"](**args)
            except Exception as e:
                # 铁律 1：任何异常都转成字符串，不让循环崩掉
                return f"错误：工具 {name} 执行失败：{e}"
            return str(result)  # 确保返回值永远是字符串
    return f"错误：找不到工具：{name}"
