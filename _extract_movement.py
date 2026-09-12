"""一次性脚本：拆移动簇 → flows/movement.py。"""

import ast
import io

HANDLE = "utils/flows/handle.py"
MOVEMENT = "utils/flows/movement.py"

METHODS = [
    "handle_move", "is_running", "async_check_sprint_status",
    "start_check_sprint_task", "stop_check_sprint_task",
    "_run_async_check_sprint", "enable_run", "move_run_fix",
]

HEADER = '''"""移动与疾跑 —— 从 Handle 拆出来的第三簇。

`handle_move` 是 handle 里最长的方法（117 行）：按住方向键 value 秒，
期间处理疾跑开关、强制断开、系统卡顿识别。疾跑状态用一条后台线程轮询
`switch_run.png` 的匹配度维持。

与战斗的交叉点只有一个：黄泉模式下上一步是 `e` 时，要先确认有没有意外进战斗
（`last_key == "e"` 分支）。所以这里注入 `combat` 而不是反向持有 Handle。

:param combat: 战斗簇（见 flows/combat.py）。只用到 technique_points_dialog /
    fight_elapsed / fight_in_map 三样，都是「这一步有没有打起来」。
"""

import asyncio
import random
import threading
import time
from functools import partial

from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key as KeyboardKey

from utils.core.log import log
from utils.core.thresholds import SPRINT_ICON


class Movement:
    """移动、疾跑检测与卡顿识别。"""

    def __init__(self, cfg, img, mouse_event, combat):
        self.cfg = cfg
        self.img = img
        self.mouse_event = mouse_event
        self.combat = combat

        self.run_fix_time = 0  # 强制断开疾跑时间
        self.run_fixed = False  # 强制断开疾跑标志
        self.last_step_run = False  # 上一次是否是疾跑
        self.tatol_save_time = 0  # 疾跑节约时间
        self.time_error_cnt = 0  # 系统卡顿计数
        self.running = False
        self.thread_cancel_sprint = None
        self.thread_check_sprint = None

'''


def main():
    src = io.open(HANDLE, encoding="utf-8").read()
    lines = src.splitlines(keepends=True)
    cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef))
    by_name = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}

    missing = [m for m in METHODS if m not in by_name]
    assert not missing, f"handle.py 里找不到：{missing}"

    def body(name):
        text = ast.get_source_segment(src, by_name[name])
        first, *rest = text.split("\n")
        return "\n".join(["    " + first, *rest])

    flow = "".join(
        body(n)
        .replace("self.technique_points_dialog()", "self.combat.technique_points_dialog()")
        .replace("self.fight_elapsed()", "self.combat.fight_elapsed()")
        .replace("self.fight_in_map = True", "self.combat.fight_in_map = True")
        + "\n\n"
        for n in METHODS
    )
    io.open(MOVEMENT, "w", encoding="utf-8", newline="").write(HEADER + "\n" + flow.rstrip() + "\n")
    tree = ast.parse(io.open(MOVEMENT, encoding="utf-8").read())
    kv = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    print(f"  movement.py: {len([n for n in kv.body if isinstance(n, ast.FunctionDef)])} 个方法")

    # 从 handle.py 删除
    drop = set()
    for name in METHODS:
        node = by_name[name]
        start = node.lineno - 1
        while start > 0 and lines[start - 1].strip() == "":
            start -= 1
        drop.update(range(start, node.end_lineno))
    s = "".join(l for i, l in enumerate(lines) if i not in drop)

    # __init__：移动状态归 Movement；fight_in_map 归 Combat
    for gone in (
        "        self.run_fix_time = 0  # 强制断开疾跑时间\n",
        "        self.run_fixed = False  # 强制断开疾跑标志\n",
        "        self.last_step_run = False  # 初始化\n",
        "        self.tatol_save_time = 0  # 疾跑节约时间\n",
        "        self.time_error_cnt = 0  # 系统卡顿计数\n",
        "        self.fight_in_map = False  # 地图内意外战斗初始化为否\n",
        "        self.running = False\n",
        "        self.thread_cancel_sprint = None  # 用于保存取消疾跑任务的线程\n",
        "        self.thread_check_sprint = None  # 用于保存检测疾跑任务的线程\n",
    ):
        assert s.count(gone) == 1, f"__init__ 锚点缺失：{gone.strip()!r}"
        s = s.replace(gone, "", 1)

    anchor = "        self.combat = Combat(self.cfg, self.img, self.mouse_event)\n"
    assert s.count(anchor) == 1
    s = s.replace(anchor, anchor + (
        "\n        #: 移动与疾跑（见 flows/movement.py）\n"
        "        self.movement = Movement(\n"
        "            self.cfg, self.img, self.mouse_event, self.combat\n"
        "        )\n"), 1)

    deleg = '''    # --- 移动：委派给 self.movement（见 flows/movement.py）-------------------

    def handle_move(self, value, key, normal_run=False, last_key: str = ""):
        """移动并处理疾跑。"""
        return self.movement.handle_move(value, key, normal_run, last_key)

'''
    tail = "    def handle_await(self, value):"
    assert s.count(tail) == 1
    s = s.replace(tail, deleg + tail, 1)

    s = s.replace("from utils.flows.orientation import Orientation\n",
                  "from utils.flows.movement import Movement\n"
                  "from utils.flows.orientation import Orientation\n", 1)
    io.open(HANDLE, "w", encoding="utf-8", newline="").write(s)
    print(f"  handle.py: 删除 {len(drop)} 行，加入装配与委派")

    # combat.py 接收 fight_in_map
    p = "utils/flows/combat.py"
    c = io.open(p, encoding="utf-8").read()
    c = c.replace("        self.snack_used = 0\n",
                  "        self.snack_used = 0\n        self.fight_in_map = False  # 地图内意外战斗\n", 1)
    io.open(p, "w", encoding="utf-8", newline="").write(c)
    print("  combat.py: 接收 fight_in_map")

    # 外部访问点
    def patch(path, pairs):
        t = io.open(path, encoding="utf-8").read()
        for old, new, n in pairs:
            assert t.count(old) >= n, f"{path}: {n} 处 {old[:50]!r}"
            t = t.replace(old, new, n)
        io.open(path, "w", encoding="utf-8", newline="").write(t)
        print("  ", path)

    patch("utils/flows/map.py", [("self.handle.tatol_save_time = 0",
                                  "self.handle.movement.tatol_save_time = 0", 1)])
    patch("utils/flows/map_operations.py", [
        ("self.handle.fight_in_map = False", "self.handle.combat.fight_in_map = False", 2),
        ("if self.handle.fight_in_map", "if self.handle.combat.fight_in_map", 1),
        ("self.handle.last_step_run = False", "self.handle.movement.last_step_run = False", 1),
    ])
    patch("utils/flows/report.py", [
        ("{self.time_mgr.format_time(self.handle.tatol_save_time)}",
         "{self.time_mgr.format_time(self.handle.movement.tatol_save_time)}", 1),
        ("系统卡顿次数：{self.handle.time_error_cnt}",
         "系统卡顿次数：{self.handle.movement.time_error_cnt}", 1),
    ])


if __name__ == "__main__":
    main()
