import time
import cv2 as cv
import pyautogui
import os
import win32api
import win32con
import win32gui
import random

from .calculated import Calculated
from .config import ConfigurationManager
from .log import log, webhook_and_log
from .time_utils import TimeUtils
from .map_handler import MapActionHandler, MapNavigation
import datetime

class Map:
    def __init__(self):
        self.calculated = Calculated()
        self.cfg = ConfigurationManager()
        self.time_mgr = TimeUtils()
        self.map_act = MapActionHandler()
        self.map_nav = MapNavigation()
        self.open_map_btn = self.cfg.read_json_file(self.cfg.CONFIG_FILE_NAME).get("open_map", "m")
        self.map_list = []
        self.map_list_map = {}
        self.map_versions = self.read_maps_versions()
        self.map_version = ""
        self.now = datetime.datetime.now()
        self.retry_cnt_max = 2
        self.map_statu_minimize = False  # 地图最小化
        self.planet = None  # 当前星球初始化
        self.planet_png_lst = ["picture\\orientation_2.png", "picture\\orientation_3.png", "picture\\orientation_4.png", "picture\\orientation_5.png", "picture\\orientation_6.png"]

    def read_maps_versions(self):
        map_dir = './map'
        map_versions = [f for f in os.listdir(map_dir) if os.path.isdir(os.path.join(map_dir, f))]
        
        return map_versions
    
    def read_maps(self, map_version):
        # 从'./map'目录获取地图文件列表（排除'old'）
        map_dir = os.path.join('./map', map_version)
        json_files = [f for f in os.listdir(map_dir) if f.endswith('.json') and not f.startswith('old')]
        json_files = sorted(json_files, key=lambda x: [int(y) for y in x.replace('-','_').replace('.','_').split('_')[1:-1]])
    
        self.map_list = json_files
        self.map_list_map.clear()
        self.map_version = map_version
    
        for map_ in json_files:
            map_data = self.cfg.read_json_file(f"map/{map_version}/{map_}")
            key1 = map_[map_.index('_') + 1:map_.index('-')]
            key2 = map_[map_.index('-') + 1:map_.index('.')]
            key2_front = key2[:key2.index('_')]
            value = self.map_list_map.get(key1)
        
            if value is None:
                value = {}

            map_data_first_name = map_data["name"].replace(' ','')
            map_data_first_name = map_data_first_name[:map_data_first_name.index('-')]
            format_map_data_first_name = key1 + '-' + key2_front + ' ' + map_data_first_name
            value[key2] = [map_data["name"], format_map_data_first_name]
            self.map_list_map[key1] = value
            
        # log.info(f"self.map_list:{self.map_list}")
        # log.info(f"self.map_list_map:{self.map_list_map}")

        return json_files

    def auto_map(self, start, start_in_mid: bool=False, dev: bool = False):
        total_processing_time = 0
        self.teleport_click_count = 0  # 初始化传送点被点击次数
        self.error_check_point = False  # 初始化筑梦机关检查为通过
        self.align_angle()
        if f'map_{start}.json' in self.map_list:
            total_start_time = time.time()

            """重置该锄地轮次相关的计数"""
            self.calculated.total_fight_time = 0
            self.calculated.tatol_save_time = 0
            self.calculated.total_fight_cnt = 0
            self.calculated.total_no_fight_cnt = 0
            self.calculated.auto_final_fight_e_cnt = 0

            map_list = self._get_map_list(start, start_in_mid)
            max_index = max(index for index, _ in enumerate(map_list))
            self.next_map_drag = False  # 初始化下一张图拖动为否
            self.start_map_name, self.end_map_name = None, None
            for index, map_json in enumerate(map_list):
                map_base = map_json.split('.')[0]
                map_data = self.cfg.read_json_file(f"map/{self.map_version}/{map_base}.json")
                map_data_name = map_data['name']
                # 检查是否应该跳过这张地图
                if self._check_and_skip_forbidden_maps(map_data_name):
                    continue

                # 地图处理
                self._process_map(map_data, map_base, index, max_index, map_list, total_start_time, total_processing_time, dev)
        else:
            log.info(f'地图编号 {start} 不存在，请尝试检查地图文件')





    
    def allow_map_drag(self, start):
        self.allow_drap_map_switch = bool(start.get("drag", False))  # 默认禁止拖动地图
        self.drag_exact = None

        if self.allow_drap_map_switch and "drag_exact" in start:
            self.drag_exact = start["drag_exact"]

    def allow_scene_drag(self, start):
        self.allow_scene_drag_switch = 0  # 初始化禁止拖动
        if "scene" in start and start["scene"] >= 1:
            self.allow_scene_drag_switch = True
        
    
    def allow_multi_click(self, start):
        self.multi_click = 1
        self.allow_multi_click_switch = False
        if "clicks" in start and start["clicks"] >= 1:
            self.allow_multi_click_switch = True
            self.multi_click = int(start["clicks"])
    
    def allow_retry_in_map(self, start):
        self.allow_retry_in_map_switch = True
        if "forbid_retry" in start and start["forbid_retry"] >= 1:
            self.allow_retry_in_map_switch = False
    

        
    def align_angle(self):
        """校准视角
        """
        if not self.cfg.CONFIG.get("angle_set", False) or self.cfg.CONFIG.get("angle", "1.0") == "1.0":
            self.calculated.monthly_pass_check()  # 月卡检查
            self.calculated.back_to_main()
            time.sleep(1)
            self.calculated.set_angle()


    




    def _get_map_list(self, start, start_in_mid: bool=False):
        """获取需要锄地的地图"""
        start_index = self.map_list.index(f'map_{start}.json')
        if start_in_mid:
            mid_slice = self.map_list[start_index:]
            map_list = mid_slice + self.map_list[:start_index]
        else:
            map_list = self.map_list[start_index:]
        return map_list

    def _check_and_skip_forbidden_maps(self, map_data_name):
        """检查并跳过配置中禁止的地图"""
        self.forbid_map = self.cfg.CONFIG.get('forbid_map', [])
        if not all(isinstance(item, str) for item in self.forbid_map):
            log.info("配置错误：'forbid_map' 应只包含字符串。")
            return False

        map_data_first_name = map_data_name.split('-')[0]
        if map_data_first_name in self.forbid_map:
            log.info(f"地图 {map_data_name} 在禁止列表中，将跳过此地图。")
            return True
        return False

    def _process_map(self, map_data, map_base, index, max_index, map_list, total_start_time, total_processing_time, dev):
        """处理每个地图的具体任务"""
        map_data_name = map_data['name']
        map_data_author = map_data['author']
        self.map_drag = self.next_map_drag
        self.next_map_drag = False
        
        self.retry = True
        self.retry_cnt = 0
        while self.retry and self.retry_cnt < self.retry_cnt_max:
            self.retry = False
            # 选择地图
            start_time = time.time() 
            self.start_map_name, self.end_map_name = (map_data_name if index == 0 else self.start_map_name, map_data_name if index == max_index else self.end_map_name)
            webhook_and_log(f"\033[0;96;40m{map_data_name}\033[0m")
            self.calculated.monthly_pass_check()  # 月卡检查
            log.info(f"路线领航员：\033[1;95m{map_data_author}\033[0m 感谢她(们)的无私奉献，准备开始路线：{map_base}")
            self.map_act.jump_this_map = False  # 跳过这张地图，一般用于过期邮包购买
            self.temp_point = ""  # 用于输出传送前的点位
            self.map_act.normal_run = False  # 初始化跑步模式为默认

            for start in map_data['start']:
                if self._process_map_start(start, map_data):
                    break
                else:
                    continue


            self.teleport_click_count = 0  # 在每次地图循环结束后重置计数器
            # 'check'过期邮包/传送识别失败/无法购买 时 跳过，执行下一张图
            if self.map_act.jump_this_map:
                return

            # 执行地图逻辑
            start_time = time.time()
            self.calculated.auto_map(map_base, False, self.map_act.normal_run, dev=dev, last_point=self.temp_point)
            end_time = time.time()
            
            # 计算处理时间并输出日志
            processing_time = end_time - start_time
            formatted_time = self.time_mgr.format_time(processing_time)
            total_processing_time += processing_time
            log.info(f"{map_base}用时\033[1;92m『{formatted_time}』\033[0m,总计:\033[1;92m『{self.time_mgr.format_time(total_processing_time)}』\033[0m")

            if index == max_index:
                """输出最终统计信息"""
                total_time = time.time() - total_start_time
                total_fight_time = self.calculated.total_fight_time
                log.info(f"该阶段锄地总用时：{self.time_mgr.format_time(total_time)}，总战斗用时 {self.time_mgr.format_time(total_fight_time)}")
                log.info(f"异常战斗识别（战斗时间 < {self.calculated.error_fight_threshold} 秒）次数：{self.calculated.error_fight_cnt}")
                if self.error_check_point:
                    log.info(f"筑梦机关检查不通过，请将机关调整到正确的位置上")
                log.info(f"疾跑节约的时间为 {self.time_mgr.format_time(self.calculated.tatol_save_time)}")
                log.info(f"战斗次数{self.calculated.total_fight_cnt}")
                log.info(f"未战斗次数{self.calculated.total_no_fight_cnt}")
                log.info(f"未战斗次数在非黄泉地图首次锄地参考值：70-80，不作为漏怪标准，漏怪具体请在背包中对材料进行溯源查找")
                log.info(f"系统卡顿次数：{self.calculated.time_error_cnt}")
                log.debug(f"匹配值小于0.99的图片：{self.calculated.img_search_val_dict}")
                log.info(f"开始地图：{self.start_map_name}，结束地图：{self.end_map_name}")


    def _process_map_start(self, start, map_data):



        key = list(start.keys())[0]
        log.info(key)
        value = start[key]
        self.calculated.search_img_allow_retry = False
        self.allow_map_drag(start)  # 是否强制允许拖动地图初始化
        self.allow_scene_drag(start)  # 是否强制允许拖动右侧场景初始化
        self.allow_multi_click(start)  # 多次点击
        self.allow_retry_in_map(start)  # 是否允许重试

        actions = {
            "check": self.map_act.process_check,
            "need_allow_map_buy": self.map_act.process_map_buy,
            "need_allow_snack_buy":self.map_act.process_snack_buy,
            "normal_run": self.map_act.set_normal_run,
            "blackscreen": self.map_act.run_mapload_check,
            "esc": self.map_act.press_esc,
            "map": self.map_act.open_map,
            "main": self.map_act.back_to_main,
            "b": self.map_act.press_b,
            "await": self.map_act.await_time,
            "space": self.map_act.press_space,
            "picture\\max.png": self.map_act.handle_max_picture,
            "picture\\transfer.png": self.map_act.handle_transfer_picture,
            "w": self.map_act.move,
            "a": self.map_act.move,
            "s": self.map_act.move,
            "d": self.map_act.move,
            "f": self.map_act.handle_f
        }

        if key in actions:
            if actions[key](value, key):
                return True
            else:
                return False
            
        else:
            value = min(value, 0.8)
            time.sleep(value)
            if key in ["picture\\1floor.png","picture\\2floor.png","picture\\3floor.png"]:
                self.map_nav.handle_floor(key)
            elif key in ["picture\\fanhui_1.png","picture\\fanhui_2.png"]:  # 有可能未找到该图片，冗余查找
                self.map_nav.handle_back(key)
            elif key.startswith("picture\\check_4-1_point"):
                self.map_nav.find_transfer_point(key, threshold=0.992)
                if self.calculated.click_target(key, 0.992, retry_in_map=False):
                    log.info(f"筑梦机关检查通过")
                else:
                    log.info(f"筑梦机关检查不通过，请将机关调整到正确的位置上")
                    self.error_check_point = True
                time.sleep(1)
            elif key == "picture\\map_4-1_point_2.png":  # 筑梦边境尝试性修复
                self.map_nav.find_transfer_point(key, threshold=0.975)
                self.calculated.click_target(key, 0.95)
                self.temp_point = key
            elif key == "picture\\orientation_1.png":
                self.map_nav.handle_orientation(key, map_data)
            elif key.startswith("picture\\map_4-3_point"):
                self.map_nav.find_transfer_point(key, threshold=0.975)
                self.calculated.click_target(key, 0.93)
                self.temp_point = key
                time.sleep(1.7)
            elif key in self.planet_png_lst:
                self.map_nav.handle_planet(key)
            else:
                if self.allow_drap_map_switch or self.map_drag:
                    self.map_nav.find_transfer_point(key, threshold=0.975, offset=self.drag_exact)
                if self.allow_scene_drag_switch:
                    self.map_nav.find_scene(key, threshold=0.990)
                if self.calculated.on_main_interface(timeout=0.5, allow_log=False):
                    self.calculated.click_target_with_alt(key, 0.95, clicks=self.multi_click)
                else:
                    self.calculated.click_target(key, 0.95, clicks=self.multi_click, retry_in_map=self.allow_retry_in_map_switch)
                self.temp_point = key
            self.teleport_click_count += 1
            log.info(f'传送点击（{self.teleport_click_count}）')
            
            if self.calculated.search_img_allow_retry:
                self.retry = True
                self.retry_cnt += 1
                if self.retry_cnt == self.retry_cnt_max:
                    self.jump_this_map = True
                    self.next_map_drag = True