import os
import orjson
import hashlib
import asyncio
import time

try:
    from .requests import *
except:
    from requests import *



class ConfigurationManager:
    def __init__(self):
        self.CONFIG_FILE_NAME = "config.json"
        self._config = None
        self._last_updated = None

    @property
    def CONFIG(self):
        # 检查配置是否需要更新
        if self._config is None or self._config_needs_update():
            self._update_config()
        return self._config

    def _update_config(self):
        self._config = self.read_json_file(self.CONFIG_FILE_NAME)
        self._last_updated = time.time()

    def _config_needs_update(self):
        if self._last_updated is None:
            return True

        file_modified_time = os.path.getmtime(self.CONFIG_FILE_NAME)
        return file_modified_time > self._last_updated
        
        
        
        
        
    def normalize_file_path(self, filename):
        # 尝试在当前目录下读取文件
        current_dir = os.getcwd()
        file_path = os.path.join(current_dir, filename)
        if os.path.exists(file_path):
            return file_path
        else:
            # 如果当前目录下没有该文件，则尝试在上一级目录中查找
            parent_dir = os.path.dirname(current_dir)
            file_path = os.path.join(parent_dir, filename)
            if os.path.exists(file_path):
                return file_path
            else:
                # 如果上一级目录中也没有该文件，则返回None
                return None


    def read_json_file(self, filename: str, path=False):
        """
        说明：
            读取文件
        参数：
            :param filename: 文件名称
            :param path: 是否返回路径
        """
        # 找到文件的绝对路径
        file_path = self.normalize_file_path(filename)
        if file_path:
            with open(file_path, "rb") as f:
                data = orjson.loads(f.read())
                if path:
                    return data, file_path
                else:
                    return data
        else:
            self.init_config_file(0, 0)
            return self.read_json_file(filename, path)


    def modify_json_file(self, filename: str, key, value):
        """
        说明：
            写入文件
        参数：
            :param filename: 文件名称
            :param key: key
            :param value: value
        """
        # 先读，再写
        data, file_path = self.read_json_file(filename, path=True)
        data[key] = value
        with open(file_path, "wb") as f:
            f.write(orjson.dumps(data))

    def init_config_file(self, real_width, real_height):
        if self.normalize_file_path(self.CONFIG_FILE_NAME) is None:
            with open(self.CONFIG_FILE_NAME, "wb+") as f:
                f.write(
                    orjson.dumps(
                        {
                            "version": "",
                            "real_width": real_width,
                            "real_height": real_height,
                            "map_debug": False,
                            "github_proxy": "",
                            "rawgithub_proxy": "",
                            "webhook_url": "",
                            "start": False,
                            "picture_version": "0",
                            "star_version": "0",
                            "open_map": "m",
                            "script_debug": False,
                            "auto_shutdown": False,
                            "auto_final_fight_e": False,
                            "auto_run_in_map": False
                        }
                    )
                )


    def get_file(self, path, exclude, exclude_file=None, get_path=False):
        """
        获取文件夹下的文件
        """
        if exclude_file is None:
            exclude_file = []
        file_list = []
        
        exclude_set = set(exclude)
        
        for root, dirs, files in os.walk(path):
            if any(ex_dir in root for ex_dir in exclude_set):
                # 如果当前文件夹在排除列表中，则跳过该文件夹
                continue
            
            for file in files:
                if any(ex_file in file for ex_file in exclude_file):
                    # 如果当前文件在排除文件列表中，则跳过该文件
                    continue
                
                if get_path:
                    file_path = os.path.join(root, file)
                    file_list.append(file_path.replace("//", "/"))
                else:
                    file_list.append(file)
        
        return file_list

    async def check_file(self, github_proxy, filename='map'):
        """
        说明：
            检测文件是否完整
        参数：
            :param github_proxy: github代理
            :param filename: 文件名称
        """
        try:
            from .log import log
        except:
            from log import log
        try:
            map_list = await get(
                f'{github_proxy}https://raw.githubusercontent.com/Starry-Wind/Honkai-Star-Rail/map/{filename}_list.json',
                follow_redirects=True)
            map_list = map_list.json()
        except Exception:
            log.warning('读取资源列表失败，请尝试更换github资源地址')
            return
        flag = False
        for map in map_list:
            file_path = Path() / map['path']
            if os.path.exists(file_path):
                if hashlib.md5(file_path.read_bytes()).hexdigest() == map['hash']:
                    continue
            try:
                await download(
                    url=f'{github_proxy}https://raw.githubusercontent.com/Starry-Wind/Honkai-Star-Rail/map/{map["path"]}',
                    save_path=file_path)
                await asyncio.sleep(0.2)
                flag = True
            except Exception:
                log.warning(f'下载{map["path"]}时出错，请尝试更换github资源地址')
        log.info('资源下载完成' if flag else '资源完好，无需下载')
