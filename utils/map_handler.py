import time
import cv2 as cv
import pyautogui

from .calculated import Calculated
from .config import ConfigurationManager
from .log import log, webhook_and_log
from .time_utils import TimeUtils
import datetime

class MapActionHandler:
    def __init__(self):
        self.calculated = Calculated()
        self.cfg = ConfigurationManager()
        self.time_mgr = TimeUtils()
        self.open_map_btn = self.cfg.read_json_file(self.cfg.CONFIG_FILE_NAME).get("open_map", "m")
        self.map_statu_minimize = False
        self.now = datetime.datetime.now()
        self.normal_run = False  # 初始化跑步模式为默认
    
    def process_check(self, value=None, key=None):
        """处理周几判断，跳过不执行的地图"""
        if value == 1:
            value = [0, 1, 2, 3, 4, 5, 6]
        if self.time_mgr.day_init(value):  # 1代表周二，4代表周五，6代表周日
            log.info(f"今天是 {self.now.strftime('%A')}，尝试购买")
        else:
            log.info(f"今天是 {self.now.strftime('%A')}，跳过")
            return True

    def process_map_buy(self, value=None, key=None):
        """处理是否允许购买"""
        self.jump_this_map = not self.cfg.read_json_file(self.cfg.CONFIG_FILE_NAME, False).get('allow_map_buy', False)
        if self.jump_this_map:
            log.info(f"config.json 中的 allow_map_buy 为 False ，跳过该图，如果需要开启购买请改为 True 并且【自行确保】能够正常购买对应物品")
        return self.jump_this_map

    def process_snack_buy(self, value=None, key=None):
        """处理是否允许购买"""
        self.jump_this_map = not self.cfg.read_json_file(self.cfg.CONFIG_FILE_NAME, False).get('allow_map_buy', False)
        if self.jump_this_map:
            log.info(f"config.json 中的 allow_snack_buy 为 False ，跳过该图，如果需要开启购买请改为 True 并且【自行确保】能够正常购买对应物品")
        return self.jump_this_map

    def set_normal_run(self, value=None, key=None):
        """此地图json将会被强制设定为禁止疾跑"""
        self.normal_run = True

    def run_mapload_check(self, value=None, key=None):
        """强制执行地图加载检测"""
        self.calculated.run_mapload_check()

    def press_esc(self, value=None, key=None):
        """按下 ESC 键"""
        pyautogui.press('esc')

    def open_map(self, value=None, key=None):
        """
        尝试打开地图并识别地图标志性的目标图片
        """
        target = cv.imread('./picture/contraction.png')
        target_back = cv.imread('./picture/map_back.png')
        start_time = time.time()
        attempts = 0
        speed_open = False
        max_attempts=10

        # 主逻辑
        while attempts < max_attempts:
            log.info(f'尝试打开地图 (尝试次数: {attempts + 1}/{max_attempts})')
            pyautogui.press(self.open_map_btn)
            
            if self._wait_for_main_interface(speed_open, start_time):
                speed_open = True
                if self._handle_target_recognition(target):
                    self._handle_back_button(target_back)
                    break
                else:
                    attempts += 1
                    self.calculated.back_to_main()  # 确保返回主界面以重试

    def back_to_main(self, value=None, key=None):
        """回到主界面"""
        self.calculated.back_to_main()  # 检测并回到主界面
        time.sleep(2)

    def press_b(self, value=None, key=None):
        """按下 B 键"""
        pyautogui.press('b')
        time.sleep(1)

    def await_time(self, value, key=None):
        """等待指定的时间"""
        time.sleep(abs(value))

    def press_space(self, value=None, key=None):
        """按下 Space 键"""
        pyautogui.press('space')

    def handle_max_picture(self, value=None, key=None):
        """处理特殊图片：最大"""
        if self.calculated.allow_buy_item():
            self.jump_this_map = False
            self.calculated.click_target("picture\\max.png", 0.93)
        else:
            self.jump_this_map = True
        return self.jump_this_map

    def handle_transfer_picture(self, value=None, key=None):
        """处理特殊图片：传送"""
        time.sleep(0.2)  # 传送键出现前预留延迟
        if not self.calculated.click_target("picture\\transfer.png", 0.93):
            self.jump_this_map = True
            return self.jump_this_map
        else:
            self.real_planet = MapNavigation.planet
        self.calculated.run_mapload_check()

    def move(self, value, key):
        """处理移动"""
        self.calculated.handle_move(value, key)

    def handle_f(self, value=None, key=None):
        """处理 F 键操作"""
        self.calculated.handle_f()

    def _wait_for_main_interface(self, speed_open, start_time):
        """
        黄泉e的状态下快速打开地图，采用按下s打断技能并且按下地图键的方式
        """
        while self.calculated.on_main_interface(timeout=0.0, allow_log=False):
            if time.time() - start_time > 3:
                return False
            if not speed_open:
                pyautogui.keyDown('s')
                pyautogui.press(self.open_map_btn)
                time.sleep(0.05)
        pyautogui.keyUp('s')
        return True
    
    def _handle_target_recognition(self, target):
        """
        处理目标图片的识别逻辑
        """
        time.sleep(3)  # 增加识别延迟，避免偶现的识别错误
        result = self.calculated.scan_screenshot(target, offset=(530, 960, -1050, -50))
        if result['max_val'] > 0.97:
            points = self.calculated.calculated(result, target.shape)
            log.info(f"识别点位{points}，匹配度{result['max_val']:.3f}")
            if not self.map_statu_minimize:
                log.info(f"地图最小化，识别图片匹配度{result['max_val']:.3f}")
                pyautogui.click(points, clicks=10, interval=0.1)
                self.map_statu_minimize = True
            return True
        return False

    def _handle_back_button(self, target_back):
        """
        处理返回按钮的识别和点击逻辑，用于偶现的卡二级地图，此时使用m键无法关闭地图
        """
        for _ in range(5):
            result_back = self.calculated.scan_screenshot(target_back, offset=(1830, 0, 0, -975))
            if result_back['max_val'] > 0.99:
                log.info(f"找到返回键")
                points_back = self.calculated.calculated(result_back, target_back.shape)
                pyautogui.click(points_back, clicks=1, interval=0.1)
            else:
                break


class MapNavigation:
    def __init__(self):
        self.calculated = Calculated()
        self.planet = None  # 当前星球初始化
        self.planet_png_lst = ["picture\\orientation_2.png", "picture\\orientation_3.png", "picture\\orientation_4.png", "picture\\orientation_5.png", "picture\\orientation_6.png"]

    def find_transfer_point(self, key, threshold=0.99, min_threshold=0.93, timeout=60, offset=None):
        """
        说明:
            寻找传送点
        参数：
            :param key: 图片地址
            :param threshold: 图片查找阈值
            :param min_threshold: 最低图片查找阈值
            :param timeout: 超时时间（秒）
            :param offset: 查找偏移，None 时使用默认移动逻辑
        """
        start_time = time.time()
        target = cv.imread(key)

        while time.time() - start_time < timeout:
            if self._is_target_found(target, threshold):
                log.info(f"传送点已找到，匹配度：{threshold:.2f}")
                return

            if offset is None:
                self._move_default(target, threshold)
            else:
                self._move_with_offset(offset)

            threshold = max(min_threshold, threshold - 0.01)

        log.error("传送点查找失败：超时或未达到最低阈值")
    
    def find_scene(self, key, threshold=0.99, min_threshold=0.93, timeout=60):
        """
        说明:
            寻找场景
        参数：
            :param key:图片地址
            :param threshold:图片查找阈值
            :param min_threshold:最低图片查找阈值
            :param timeout:超时时间（秒）
        """
        start_time = time.time()
        target = cv.imread(key)
        inverted_target = cv.bitwise_not(target)
        target_list = [target, inverted_target]
        direction_names = ["向下移动", "向上移动"]
        while not self.calculated.have_screenshot(target_list, (0, 0, 0, 0), threshold) and time.time() - start_time < timeout and threshold >= min_threshold:
            # 设置向下、向上的移动数值
            directions = [(1700, 900, 1700, 300), (1700, 300, 1700, 900)]
            for index, direction in enumerate(directions):
                log.info(f"开始移动右侧场景，{direction_names[index]}，当前所需匹配值{threshold}")
                for i in range(1):
                    if not self.calculated.have_screenshot(target_list, (0, 0, 0, 0), threshold):
                        self.calculated.mouse_drag(*direction)
                    else:
                        return
            threshold -= 0.02

    def handle_orientation(self, key, map_data):
        """
        已在当前星球，跳过点击星轨航图
        未在当前星球，点击星轨航图后进行黑屏检测，如果因为客户端黑屏，则返回重试点击星轨航图
        """
        keys_to_find = self.planet_png_lst
        planet_dict = {k: v for item in map_data['start'] for k, v in item.items() if k in keys_to_find}
        planet = list(planet_dict.keys())[0]
        if self.check_planet(planet):
            return
        else:
            orientation_delay = 2
            while True:
                self.calculated.click_target(key, 0.97, retry_in_map=True)
                orientation_delay = min(orientation_delay, 4)
                time.sleep(orientation_delay)
                if self.calculated.blackscreen_check():
                    pyautogui.press('esc')
                    time.sleep(2)
                    orientation_delay += 0.5
                else:
                    return
    def handle_planet(self, key):
        """点击星球
        """
        if self.check_planet(key):
            return
        else:
            self.find_transfer_point(key, threshold=0.975)
            if self.calculated.click_target(key, 0.93, delay=0.1):
                time.sleep(5)
                delay_time = 0.5
                while not self.find_starrail_map():
                    if self.calculated.blackscreen_check():
                        self.planet = key
                        break
                    delay_time += 0.1
                    delay_time = max(delay_time, 1)
                    log.info(f"检测到未成功点击星球，尝试重试点击星球，鼠标点击间隔时间 {delay_time}")
                    self.calculated.click_target(key, 0.93, delay=delay_time)
                    time.sleep(5)
                else:
                    self.planet = key
            time.sleep(1.7)
    
    def handle_floor(self, key):
        """点击楼层
        """
        if self.calculated.img_bitwise_check(target_path=key, offset=(30,740,-1820,-70)):
            self.calculated.click_target(key, 0.93, offset=(30,740,-1820,-70))
        else:
            log.info(f"已在对应楼层，跳过选择楼层")

    def handle_back(self, key):
        """点击右上角返回
        """
        if not self.find_starrail_map():
            self.calculated.click_target(key, 0.94, timeout=3, offset=(1660,100,-40,-910), retry_in_map=False)
        else:
            log.info(f"检测到星轨航图，不进行点击'返回'")

    def find_starrail_map(self):
        """当前页面找到星轨航图"""
        img = cv.imread("./picture/kaituoli_1.png")
        return self.calculated.on_interface(check_list=[img], timeout=1, interface_desc='星轨航图', threshold=0.97, offset=(1580,0,0,-910), allow_log=False)

    def check_planet(self, planet):
        """检查是否已在该星球"""
        if self.planet == planet:
            log.info(f"星球相同，跳过选择星球 {planet}")
        return self.planet == planet

    def _directions(self):
        directions = {
                "down": (250, 900, 250, 300),
                "left": (250, 900, 850, 900),
                "up": (1330, 200, 1330, 800),
                "right": (1330, 200, 730, 200),
            }
        return directions

    def _is_target_found(self, target, threshold):
        """
        判断目标是否找到。
        """
        return self.calculated.have_screenshot([target], (0, 0, 0, 0), threshold)

    def _move_default(self, target, threshold):
        """
        按默认逻辑移动地图。
        """
        for direction_name, direction_coords in self._directions().items():
            log.info(f"尝试 {direction_name} ，当前阈值：{threshold:.2f}")
            for _ in range(3):
                if not self._is_target_found(target, threshold):
                    self.calculated.mouse_drag(*direction_coords)
                else:
                    return

    def _move_with_offset(self, offset):
        """
        按偏移量移动地图。
        """
        for _ in range(offset[0]):  # 向左+向上
            self.calculated.mouse_drag(*self._directions()["left"])
            self.calculated.mouse_drag(*self._directions()["up"])
        for _ in range(offset[1]):  # 向右
            self.calculated.mouse_drag(*self._directions()["right"])
        for _ in range(offset[2]):  # 向下
            self.calculated.mouse_drag(*self._directions()["down"])