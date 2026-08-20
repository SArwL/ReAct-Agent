"""
工具：文件读取与写入 —— 【参考实现】

对照"三要素契约"：
- 函数参数名 = action JSON 里的 key
- 永远返回字符串，出错也返回字符串
- 文件末尾用 TOOLS 列表注册

安全提示：目前可以读写进程权限内的任意路径。以后可以加"只允许
读写某个工作目录"的限制（把工具关进沙箱），到时再说。
"""

import os


def read_file(path: str) -> str:
    """读取指定文本文件的内容。"""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"错误：文件不存在：{path}"
    except IsADirectoryError:
        return f"错误：{path} 是文件夹，不是文件"
    except PermissionError:
        return f"错误：没有读取权限：{path}"
    except UnicodeDecodeError:
        return f"错误：无法按 utf-8 解码，可能是二进制文件：{path}"


def write_file(path: str, content: str) -> str:
    """向指定文件写入内容（覆盖已有内容）。"""
    try:
        # 目标路径的父目录不存在时自动创建
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"已写入：{path}（{len(content)} 字符）"
    except PermissionError:
        return f"错误：没有写入权限：{path}"
    except OSError as e:
        return f"错误：写入失败：{e}"


TOOLS = [
    {
        "name": "read_file",
        "description": "读取指定文本文件的内容。参数：path（文件路径）",
        "func": read_file,
    },
    {
        "name": "write_file",
        "description": "向指定文件写入文本内容，覆盖已有内容；父目录不存在会自动创建。参数：path（文件路径）、content（文本内容）",
        "func": write_file,
    },
]
