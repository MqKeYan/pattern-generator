"""
版本管理模块
============
纯内存语义化版本号管理，不依赖文件存储。

用法:
    from app.version import current_version
    print(current_version())  # "1.2.0"
"""

import sys

MAJOR = 1
MINOR = 2
PATCH = 0


def current_version() -> str:
    """返回当前版本号字符串 (如 '1.2.0')"""
    return f"{MAJOR}.{MINOR}.{PATCH}"


def bump_patch() -> str:
    """升级修订号 (1.2.0 → 1.2.1)"""
    global PATCH
    PATCH += 1
    return current_version()


def bump_minor() -> str:
    """升级次版本号 (1.2.0 → 1.3.0)"""
    global MINOR, PATCH
    MINOR += 1
    PATCH = 0
    return current_version()


def bump_major() -> str:
    """升级主版本号 (1.2.0 → 2.0.0)"""
    global MAJOR, MINOR, PATCH
    MAJOR += 1
    MINOR = 0
    PATCH = 0
    return current_version()


# ── CLI ─────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "patch":
            print(bump_patch())
        elif cmd == "minor":
            print(bump_minor())
        elif cmd == "major":
            print(bump_major())
        else:
            print(f"未知命令: {cmd}")
            print("用法: python -m app.version [patch|minor|major]")
    else:
        print(current_version())
