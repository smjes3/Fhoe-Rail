"""tools/shutdown.py —— 独立 GUI 脚本的导入安全。

这个模块**故意不被 import**：它在模块级创建 Tk 窗口并调用 mainloop()，
导入即阻塞，且 30 秒后会自动启动关机倒计时（终点是 os.system("shutdown /s /t 1")）。
所以这里只做静态分析与源码检索，绝不执行它。
"""

import ast
from pathlib import Path

import pytest

SHUTDOWN_PATH = Path(__file__).resolve().parent.parent / "tools" / "shutdown.py"
SOURCE = SHUTDOWN_PATH.read_text(encoding="utf-8")
REPO_ROOT = SHUTDOWN_PATH.parent.parent


def scanned_files():
    """会参与「谁 import 了 shutdown」扫描的所有源码。"""
    files = list((REPO_ROOT / "utils").rglob("*.py"))
    files += list((REPO_ROOT / "tools").rglob("*.py"))
    files += list((REPO_ROOT / "webui").rglob("*.py"))
    entry = REPO_ROOT / "fhoe.py"
    if entry.exists():
        files.append(entry)
    return files


def module_level_calls(tree):
    """模块顶层的裸调用表达式（不含函数体内部）。"""
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            yield ast.unparse(node.value)


def module_level_assignments(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            yield ast.unparse(node)


class TestShutdownIsImportSafe:
    @pytest.mark.xfail(
        strict=True,
        reason="模块级直接调用 window.mainloop()，任何 `import tools.shutdown` 都会永久阻塞",
    )
    def test_mainloop_is_not_called_at_module_level(self):
        calls = list(module_level_calls(ast.parse(SOURCE)))
        assert not any("mainloop" in call for call in calls), calls

    @pytest.mark.xfail(
        strict=True,
        reason="模块级创建 Tk 根窗口（window = tk.Tk()），导入就会弹窗并注册 after 回调",
    )
    def test_tk_root_is_not_created_at_module_level(self):
        assignments = list(module_level_assignments(ast.parse(SOURCE)))
        assert not any("Tk()" in assignment for assignment in assignments), assignments

    def test_source_still_contains_a_mainloop_somewhere(self):
        """如果哪天 GUI 循环被搬进函数里，这个测试会提醒你上面的 xfail 可以删了。"""
        assert "mainloop" in SOURCE

    def test_module_is_not_imported_anywhere(self):
        """一旦有人 import 它，那条代码路径就会卡死。"""
        offenders = [
            path.relative_to(REPO_ROOT).as_posix()
            for path in scanned_files()
            if path != SHUTDOWN_PATH
            and "tools.shutdown" in path.read_text(encoding="utf-8")
        ]
        assert offenders == [], f"这些文件 import 了 shutdown：{offenders}"

    def test_shutdown_is_never_re_exported(self):
        """tools/ 不是包，没有 __init__.py；utils/ 的也必须是空的。"""
        assert not (REPO_ROOT / "tools" / "__init__.py").exists(), (
            "tools/ 是按路径调用的脚本目录，不应变成可 import 的包"
        )
        init_file = REPO_ROOT / "utils" / "__init__.py"
        assert init_file.read_text(encoding="utf-8").strip() == ""
