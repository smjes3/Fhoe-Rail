"""utils/flows/handle.py —— 战斗判定、F 键分支、移动循环、疾跑线程。"""

import time
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pytest
import win32api
import win32con
from pynput.keyboard import Key as KeyboardKey

import utils.flows.handle as handle_module
from utils.core.exceptions import CustomException
from utils.flows.handle import Handle
from utils.drivers.img import Img


class TickingTime:
    """每次读时间就前进 1 秒，让带超时的循环能确定性地退出。"""

    def __init__(self):
        self.now = 0.0
        self.slept = []

    def time(self):
        self.now += 1.0
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)

    def perf_counter(self):
        self.now += 1.0
        return self.now


class StubController:
    """pynput 键盘控制器的替身。"""

    def __init__(self, released=None, pressed=None):
        self.released = released if released is not None else []
        self.pressed = pressed if pressed is not None else []

    def press(self, key):
        self.pressed.append(key)

    def release(self, key):
        self.released.append(key)

    def tap(self, key):
        self.pressed.append(key)


@pytest.fixture
def handle(make_instance, monkeypatch):
    """一个不依赖游戏窗口的 Handle。"""
    controller = StubController()
    monkeypatch.setattr(handle_module, "KeyboardController", lambda: controller)
    instance = make_instance(
        Handle,
        cfg=SimpleNamespace(config_file={"auto_run_in_map": False}),
        img=SimpleNamespace(
            switch_run="switch_run.png",
            scan_screenshot=lambda *a, **k: {"max_val": 0.0},
        ),
        thread_check_sprint=None,
        running=False,
        run_fix_time=0,
        run_fixed=False,
        last_step_run=False,
        tatol_save_time=0,
        time_error_cnt=0,
        error_fight_cnt=0,
        error_fight_threshold=3,
    )
    instance.stop_check_sprint_task = lambda: None
    instance.controller = controller
    return instance


class TestAnalyzeFoundImages:
    """_analyze_found_images 是一张纯决策表，是 handle 里最值得覆盖的部分。"""

    @pytest.mark.parametrize(
        "found,expected",
        [
            ({}, (True, 15, False)),
            ({"target": 0.99}, (True, 15, True)),
            ({"target": 0.99, "dream_pop": 0.99}, (True, 3, True)),
            ({"target": 0.99, "teleport": 0.99}, (False, 0, True)),
            ({"target": 0.99, "space_anchor": 0.99}, (False, 0, False)),
            ({"target": 0.99, "dream_module": 0.99}, (True, 4, True)),
            ({"target": 0.99, "listen": 0.99}, (False, 0, False)),
            ({"target": 0.99, "dream_scape": 0.99}, (True, 5, True)),
            ({"target": 0.99, "go_to": 0.99}, (False, 0, True)),
            ({"dream_pop": 0.99}, (True, 15, False)),
        ],
    )
    def test_decision_table(self, handle, found, expected):
        assert handle._analyze_found_images(found, 15) == expected

    def test_keeps_default_delay_for_plain_target(self, handle):
        assert handle._analyze_found_images({"target": 0.99}, 8)[1] == 8

    def test_earlier_branch_wins(self, handle):
        """elif 顺序决定优先级：dream_pop 排在 teleport 之前。"""
        both = {"target": 0.99, "dream_pop": 0.99, "teleport": 0.99}
        assert handle._analyze_found_images(both, 15) == (True, 3, True)


class TestCheckFImg:
    @pytest.fixture
    def f_handle(self, make_instance, monkeypatch):
        monkeypatch.setattr(
            Img, "get_img", staticmethod(lambda path: np.zeros((4, 4, 3), np.uint8))
        )
        instance = make_instance(Handle)
        instance.img = SimpleNamespace(
            scan_screenshot=lambda *a, **k: {"max_val": 0.0},
            scan_temp_screenshot=lambda *a, **k: {"max_val": 0.0},
        )
        monkeypatch.setattr(handle_module, "time", TickingTime())
        return instance

    def test_nothing_found_forbids_pressing_f(self, f_handle):
        assert f_handle._check_f_img(15, timeout=2) == (True, 15, False)

    def test_target_found_allows_pressing_f(self, f_handle):
        f_handle.img = SimpleNamespace(
            scan_screenshot=lambda *a, **k: {"max_val": 0.99},
            scan_temp_screenshot=lambda *a, **k: {"max_val": 0.0},
        )
        use_absolute, delay, allow = f_handle._check_f_img(15, timeout=2)
        assert (use_absolute, delay, allow) == (True, 15, True)

    def test_stops_early_once_target_plus_two_seconds(self, f_handle):
        """找到 target 后最多再等 2 秒就停，不会耗满整个 timeout。"""
        scans = []

        def scan(*args, **kwargs):
            scans.append(1)
            return {"max_val": 0.99}

        f_handle.img = SimpleNamespace(
            scan_screenshot=scan, scan_temp_screenshot=scan
        )
        f_handle._check_f_img(15, timeout=30)
        assert len(scans) == 8, "一轮扫描 8 张图后即满足退出条件"


class TestHandleF:
    def test_skips_and_flags_error_when_not_allowed(self, make_instance):
        instance = make_instance(Handle)
        instance._check_f_img = lambda value, timeout=5: (True, 15, False)

        instance.handle_f(10, allow_skip=True)

        assert instance.f_key_error is True

    def test_continues_when_skip_disallowed(self, make_instance):
        instance = make_instance(Handle)
        instance._check_f_img = lambda value, timeout=5: (True, 15, False)

        instance.handle_f(10, allow_skip=False)

        assert instance.f_key_error is False

    def test_presses_f_with_absolute_delay(self, make_instance, monkeypatch):
        pressed = []
        monkeypatch.setattr(
            handle_module,
            "KeyboardEvent",
            SimpleNamespace(keyboard_press=lambda key, delay=0: pressed.append(key)),
        )
        monkeypatch.setattr(handle_module, "time", TickingTime())
        instance = make_instance(Handle)
        instance._check_f_img = lambda value, timeout=5: (True, 3, True)

        instance.handle_f(10)

        assert pressed == ["f"]

    def test_waits_for_main_interface_when_delay_is_zero(
        self, make_instance, monkeypatch
    ):
        monkeypatch.setattr(
            handle_module,
            "KeyboardEvent",
            SimpleNamespace(keyboard_press=lambda key, delay=0: None),
        )
        monkeypatch.setattr(handle_module, "time", TickingTime())
        detected = []
        instance = make_instance(Handle)
        instance._check_f_img = lambda value, timeout=5: (False, 0, True)
        instance.img = SimpleNamespace(on_main_interface=lambda *a, **k: detected.append(1))

        instance.handle_f(10)

        assert detected == [1]

    def test_allow_skip_helper_passes_through(self, make_instance):
        instance = make_instance(Handle)
        seen = []
        instance.handle_f = lambda value, allow_skip=True: seen.append((value, allow_skip))

        instance.handle_allow_skip_f(7)

        assert seen == [(7, False)]


class TestHandleCheck:
    def test_none_means_skip(self, make_instance):
        assert make_instance(Handle).handle_check(None, "周一") is False

    def test_value_one_means_every_day(self, make_instance):
        assert make_instance(Handle).handle_check(1, "周一") is True

    def test_today_matches(self, make_instance):
        today = datetime.now().weekday()
        assert make_instance(Handle).handle_check([today], "今天") is True

    def test_other_day_does_not_match(self, make_instance):
        tomorrow = (datetime.now().weekday() + 1) % 7
        assert make_instance(Handle).handle_check([tomorrow], "明天") is False

    def test_empty_list_means_skip(self, make_instance):
        assert make_instance(Handle).handle_check([], "无") is False


class TestHandleFighting:
    def test_rejects_unknown_value(self, make_instance):
        with pytest.raises(CustomException):
            make_instance(Handle).handle_fighting(3)

    def test_value_two_clicks_cursor(self, make_instance, monkeypatch):
        monkeypatch.setattr(win32api, "GetCursorPos", lambda: (11, 22))
        monkeypatch.setattr(handle_module, "time", TickingTime())
        clicked = []
        instance = make_instance(
            Handle, mouse_event=SimpleNamespace(click=lambda points: clicked.append(points))
        )

        instance.handle_fighting(2)

        assert clicked == [(11, 22)]

    def test_last_fight_uses_e_when_enabled(self, make_instance):
        instance = make_instance(
            Handle,
            cfg=SimpleNamespace(
                config_file={"auto_final_fight_e": True, "auto_final_fight_e_cnt": 3}
            ),
            current_fighting_index=0,
            fighting_count=1,
            auto_final_fight_e_cnt=0,
        )
        actions = []
        instance.handle_e = lambda value: actions.append("e")
        instance.fighting = lambda: actions.append("fight")

        instance.handle_fighting(1)

        assert actions == ["e"]
        assert instance.current_fighting_index == 1
        assert instance.auto_final_fight_e_cnt == 1

    def test_non_last_fight_uses_normal_attack(self, make_instance):
        instance = make_instance(
            Handle,
            cfg=SimpleNamespace(
                config_file={"auto_final_fight_e": True, "auto_final_fight_e_cnt": 3}
            ),
            current_fighting_index=0,
            fighting_count=2,
            auto_final_fight_e_cnt=0,
        )
        actions = []
        instance.handle_e = lambda value: actions.append("e")
        instance.fighting = lambda: actions.append("fight")

        instance.handle_fighting(1)

        assert actions == ["fight"]

    def test_e_budget_is_capped(self, make_instance):
        instance = make_instance(
            Handle,
            cfg=SimpleNamespace(
                config_file={"auto_final_fight_e": True, "auto_final_fight_e_cnt": 1}
            ),
            current_fighting_index=0,
            fighting_count=1,
            auto_final_fight_e_cnt=1,
        )
        actions = []
        instance.handle_e = lambda value: actions.append("e")
        instance.fighting = lambda: actions.append("fight")

        instance.handle_fighting(1)

        assert actions == ["fight"]


class TestFightErrorCounting:
    def test_counts_only_fights_shorter_than_threshold(self, make_instance):
        instance = make_instance(Handle, error_fight_cnt=0, error_fight_threshold=3)
        instance.fight_error_cnt(2)
        instance.fight_error_cnt(3)
        instance.fight_error_cnt(30)
        assert instance.error_fight_cnt == 1


class TestHandleEsc:
    def test_rejects_other_values(self, make_instance):
        with pytest.raises(CustomException):
            make_instance(Handle).handle_esc(2)

    def test_sends_key_down_and_key_up(self, make_instance, monkeypatch):
        flags = []
        monkeypatch.setattr(
            win32api, "keybd_event", lambda vk, scan, value, extra: flags.append(value)
        )
        monkeypatch.setattr(handle_module, "time", TickingTime())

        make_instance(Handle).handle_esc(1)

        assert flags == [0, win32con.KEYEVENTF_KEYUP]


class TestHandleAwait:
    def test_uses_absolute_value(self, make_instance, monkeypatch):
        fake = TickingTime()
        monkeypatch.setattr(handle_module, "time", fake)

        make_instance(Handle).handle_await(-1.5)

        assert fake.slept == [1.5]


class TestHandleR:
    def test_repeats_press_at_random_interval(self, make_instance, monkeypatch):
        pressed = []
        monkeypatch.setattr(
            handle_module,
            "KeyboardEvent",
            SimpleNamespace(keyboard_press=lambda key, delay=0: pressed.append(key)),
        )
        fake = TickingTime()
        monkeypatch.setattr(handle_module, "time", fake)
        monkeypatch.setattr(handle_module.random, "uniform", lambda low, high: 0.5)

        make_instance(Handle).handle_r(1.0, "r")

        assert len(pressed) == 2
        assert fake.slept == [0.5, 0.5]

    def test_sleeps_remainder_when_not_divisible(self, make_instance, monkeypatch):
        monkeypatch.setattr(
            handle_module, "KeyboardEvent", SimpleNamespace(keyboard_press=lambda *a, **k: None)
        )
        fake = TickingTime()
        monkeypatch.setattr(handle_module, "time", fake)
        monkeypatch.setattr(handle_module.random, "uniform", lambda low, high: 0.3)

        make_instance(Handle).handle_r(1.0, "r")

        # int(1.0/0.3) == 3 次按下，剩 0.1 秒补睡
        assert fake.slept == [0.3, 0.3, 0.3, pytest.approx(0.1)]


class TestHandleBAndScroll:
    def test_handle_b_presses_b(self, make_instance, monkeypatch):
        pressed = []
        monkeypatch.setattr(handle_module.pyautogui, "press", lambda key: pressed.append(key))
        monkeypatch.setattr(handle_module, "time", TickingTime())

        make_instance(Handle).handle_b()

        assert pressed == ["b"]

    def test_scroll_delegates_to_pyautogui(self, make_instance, monkeypatch):
        scrolled = []
        monkeypatch.setattr(handle_module.pyautogui, "scroll", lambda clicks: scrolled.append(clicks))
        monkeypatch.setattr(handle_module, "time", TickingTime())

        make_instance(Handle).scroll(-3)

        assert scrolled == [-3]


class TestHandleClickFloor:
    def test_maps_index_to_relative_percentage(self, make_instance):
        instance = make_instance(Handle)
        clicks = []
        instance.mouse_event = SimpleNamespace(
            relative_click=lambda points: clicks.append(points)
        )

        instance.handle_click_floor(0)
        instance.handle_click_floor(1)

        assert clicks[0] == (3.4, pytest.approx(970 / 1080 * 100))
        assert clicks[1] == (3.4, pytest.approx((970 - 86) / 1080 * 100))


class TestViewHelpers:
    def test_handle_view_set_stores_reference_arrow(self, make_instance, monkeypatch):
        monkeypatch.setattr(handle_module, "time", TickingTime())
        instance = make_instance(Handle)
        instance.take_arrow = lambda: "ARROW"

        instance.handle_view_set(0.1)

        assert instance.arrow_begin == "ARROW"


class TestCalAng:
    def test_identical_arrow_is_zero_degrees(self, make_instance):
        """同一张图旋转 0 度时归一化相关为 1，应判定为 0 度。"""
        instance = make_instance(Handle, img=object.__new__(Img))
        arrow = np.zeros((25, 25, 3), dtype=np.uint8)
        arrow[8:17, 11:14] = 255

        assert instance.cal_ang(arrow, arrow) == 0


class TestIsRunning:
    def test_threshold_is_high(self, make_instance):
        instance = make_instance(Handle)
        instance.img = SimpleNamespace(
            switch_run="img", scan_screenshot=lambda *a, **k: {"max_val": 0.997}
        )
        assert instance.is_running() is True

        instance.img = SimpleNamespace(
            switch_run="img", scan_screenshot=lambda *a, **k: {"max_val": 0.99}
        )
        assert instance.is_running() is False


class TestSprintTaskLifecycle:
    def test_start_skips_when_thread_already_alive(self, make_instance, log_records):
        class Alive:
            def is_alive(self):
                return True

        instance = make_instance(Handle, thread_check_sprint=Alive(), running=False)

        instance.start_check_sprint_task()

        assert instance.running is False, "不应重复置位"
        assert any("已在运行" in r["message"] for r in log_records)

    def test_stop_joins_and_clears_thread(self, make_instance):
        joined = []

        class Thread:
            def is_alive(self):
                return True

            def join(self):
                joined.append(1)

        instance = make_instance(Handle, thread_check_sprint=Thread(), running=True)

        instance.stop_check_sprint_task()

        assert instance.running is False
        assert joined == [1]
        assert instance.thread_check_sprint is None

    def test_enable_run_presses_shift_only_when_needed(self, make_instance, monkeypatch):
        controller = StubController()
        monkeypatch.setattr(handle_module, "KeyboardController", lambda: controller)
        instance = make_instance(Handle)

        instance.is_running = lambda: True
        instance.enable_run()
        assert controller.pressed == [], "已经在疾跑时不应重复按 Shift"

        instance.is_running = lambda: False
        instance.enable_run()
        assert controller.pressed == [KeyboardKey.shift]


class TestHandleMove:
    def test_releases_direction_and_shift_keys_on_error(self, handle, monkeypatch):
        """移动循环里抛异常时，方向键与 Shift 必须被释放，否则键盘会卡住。"""

        def boom(*args, **kwargs):
            raise RuntimeError("循环中失败")

        monkeypatch.setattr(handle, "move_run_fix", boom)

        with pytest.raises(RuntimeError):
            handle.handle_move(0.5, "w")

        assert "w" in handle.controller.released
        assert KeyboardKey.shift in handle.controller.released

    def test_releases_keys_on_normal_completion(self, handle):
        handle.handle_move(0.1, "w")
        assert "w" in handle.controller.released
        assert KeyboardKey.shift in handle.controller.released

    def test_presses_the_requested_key(self, handle):
        handle.handle_move(0.1, "a")
        assert "a" in handle.controller.pressed

    @pytest.mark.xfail(
        strict=True,
        reason="计时循环体内没有任何 time.sleep：疾跑分支触发后（或关闭疾跑时），"
        "三个 elif 条件全部为假，剩余的等待时间变成 100% CPU 忙等",
    )
    def test_does_not_burn_cpu_while_waiting(self, handle):
        cpu_before = time.process_time()
        handle.handle_move(0.4, "w")
        cpu_used = time.process_time() - cpu_before
        assert cpu_used < 0.15
