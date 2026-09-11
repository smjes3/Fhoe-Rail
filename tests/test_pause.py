"""utils/drivers/pause.py —— F7~F10 暂停控制与监听器去重。"""

import threading
import time

import pytest

import utils.ui.pause as pause_module
from utils.ui.pause import _INSTALLED_HANDLERS, Pause


class StubKeyboard:
    """记录 on_press_key / unhook 调用，避免注册真实的全局键盘钩子。"""

    def __init__(self):
        self.registered = []
        self.unhooked = []

    def on_press_key(self, key, callback):
        handle = (key, callback)
        self.registered.append(handle)
        return handle

    def unhook(self, handle):
        self.unhooked.append(handle)
        if handle in self.registered:
            self.registered.remove(handle)


@pytest.fixture
def keyboard(monkeypatch):
    stub = StubKeyboard()
    monkeypatch.setattr(pause_module, "keyboard", stub)
    monkeypatch.setattr(pause_module, "cv2", SimpleCv2())
    _INSTALLED_HANDLERS.clear()
    yield stub
    _INSTALLED_HANDLERS.clear()


class SimpleCv2:
    def __init__(self):
        self.destroyed = 0

    def destroyAllWindows(self):
        self.destroyed += 1

    def imshow(self, *args, **kwargs):
        return None

    def waitKey(self, delay):
        return None


class TestHandlerRegistration:
    def test_registers_four_shortcut_keys(self, keyboard):
        Pause(dev=False)
        assert [key for key, _ in keyboard.registered] == ["F7", "F8", "F9", "F10"]

    def test_recreating_pause_unhooks_previous_handlers(self, keyboard):
        Pause(dev=False)
        first = list(keyboard.registered)
        Pause(dev=False)
        assert sorted(keyboard.unhooked) == sorted(first), "旧监听器必须被注销，否则会泄漏"

    def test_tolerates_unhook_failure(self, keyboard, monkeypatch):
        Pause(dev=False)

        def boom(handle):
            raise RuntimeError("已经失效的钩子")

        monkeypatch.setattr(keyboard, "unhook", boom)
        Pause(dev=False)  # 不应抛出


class TestTogglePause:
    def test_f8_engages_pause(self, keyboard):
        pause = Pause(dev=False)

        pause.toggle_pause(None)

        assert pause.pause_event.is_set() is True
        assert pause.last_key_pressed == "F8"

    def test_f8_while_paused_is_a_noop(self, keyboard):
        pause = Pause(dev=False)
        pause.pause_event.set()

        pause.toggle_pause(None)

        assert pause.pause_event.is_set() is True

    def test_f7_releases_pause(self, keyboard):
        pause = Pause(dev=False)
        pause.pause_event.set()

        pause.continue_in_map(None)

        assert pause.pause_event.is_set() is False
        assert pause.last_key_pressed == "F7"

    def test_f7_without_pause_is_a_noop(self, keyboard):
        pause = Pause(dev=False)
        pause.continue_in_map(None)
        assert pause.last_key_pressed is None

    @pytest.mark.parametrize("handler_name", ["continue_and_restart", "continue_new_map"])
    def test_dev_only_shortcuts_are_ignored_in_normal_mode(self, keyboard, handler_name):
        pause = Pause(dev=False)
        pause.pause_event.set()

        getattr(pause, handler_name)(None)

        assert pause.pause_event.is_set() is True
        assert pause.last_key_pressed is None

    def test_dev_shortcuts_work_in_dev_mode(self, keyboard):
        pause = Pause(dev=True)
        pause.pause_event.set()

        pause.continue_and_restart(None)

        assert pause.pause_event.is_set() is False
        assert pause.last_key_pressed == "F9"

    def test_f10_reruns_map_in_dev_mode(self, keyboard):
        pause = Pause(dev=True)
        pause.pause_event.set()

        pause.continue_new_map(None)

        assert pause.last_key_pressed == "F10"


class TestCheckPause:
    def test_returns_false_when_not_paused(self, keyboard):
        pause = Pause(dev=False)
        assert pause.check_pause(dev=False, last_point="") is False

    def test_returns_the_key_that_resumed(self, keyboard):
        pause = Pause(dev=False)
        pause.pause_event.set()
        resume = threading.Timer(0.05, pause.continue_in_map, args=(None,))
        resume.start()

        try:
            assert pause.check_pause(dev=False, last_point="") == "F7"
        finally:
            resume.join()

    def test_destroys_windows_after_pause(self, keyboard, monkeypatch):
        pause = Pause(dev=False)
        pause.pause_event.set()
        resume = threading.Timer(0.05, pause.continue_in_map, args=(None,))
        resume.start()

        try:
            pause.check_pause(dev=False, last_point="")
        finally:
            resume.join()

        assert pause_module.cv2.destroyed == 1

    @pytest.mark.xfail(
        strict=True,
        reason="dev=False 且 last_point 为空时，循环体只剩 `press = True`，没有 time.sleep，"
        "按下 F8 会把一个 CPU 核心跑满",
    )
    def test_does_not_burn_cpu_while_paused(self, keyboard):
        pause = Pause(dev=False)
        pause.pause_event.set()
        resume = threading.Timer(0.3, pause.continue_in_map, args=(None,))
        resume.start()

        cpu_before = time.process_time()
        try:
            pause.check_pause(dev=False, last_point="")
        finally:
            resume.join()
        cpu_used = time.process_time() - cpu_before

        assert cpu_used < 0.1


class TestShowImg:
    def test_skips_when_image_missing(self, keyboard, monkeypatch):
        pause = Pause(dev=False)
        pause.pause_event.set()
        monkeypatch.setattr("utils.ui.pause.Img.get_img", staticmethod(lambda path: None))

        pause.pause_event.clear()
        pause._show_img("x.png")  # 不应抛出

    def test_loops_until_pause_is_released(self, keyboard, monkeypatch):
        import numpy as np

        pause = Pause(dev=False)
        monkeypatch.setattr(
            "utils.ui.pause.Img.get_img",
            staticmethod(lambda path: np.zeros((4, 4, 3), dtype=np.uint8)),
        )
        pause.pause_event.set()
        resume = threading.Timer(0.05, pause.continue_in_map, args=(None,))
        resume.start()

        try:
            pause._show_img("x.png")
        finally:
            resume.join()

        assert pause.pause_event.is_set() is False
