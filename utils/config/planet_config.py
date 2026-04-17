from typing import Dict, List, Tuple

class PlanetConfig:
    """星球配置类"""
    
    # 星球ID与名称映射
    PLANETS: Dict[str, str] = {
        "1": "空间站「黑塔」",
        "2": "雅利洛-VI",
        "3": "仙舟「罗浮」",
        "4": "匹诺康尼",
        "5": "翁法罗斯",
        "6": "二相乐园"
    }
    
    # 星球选择选项（用于菜单显示）
    PLANET_OPTIONS: Dict[str, str] = {
        "1 空间站「黑塔」": "1",
        "2 雅利洛-VI": "2",
        "3 仙舟「罗浮」": "3",
        "4 匹诺康尼": "4",
        "5 翁法罗斯": "5",
        "6 二相乐园": "6"
    }
    
    @classmethod
    def get_planet_name(cls, planet_id: str) -> str:
        """根据星球ID获取星球名称"""
        return cls.PLANETS.get(planet_id, planet_id)
    
    @classmethod
    def get_planet_id(cls, planet_name: str) -> str:
        """根据星球名称获取星球ID"""
        for pid, name in cls.PLANETS.items():
            if name == planet_name:
                return pid
        return None
    
    @classmethod
    def get_all_planets(cls) -> List[Tuple[str, str]]:
        """获取所有星球的ID和名称列表"""
        return list(cls.PLANETS.items())
    
    @classmethod
    def get_planet_options(cls) -> Dict[str, str]:
        """获取星球选择选项"""
        return cls.PLANET_OPTIONS.copy()
    
    @classmethod
    def get_planet_options_with_return(cls) -> Dict[str, str]:
        """获取带【返回】选项的星球选择选项"""
        options = cls.PLANET_OPTIONS.copy()
        options["【返回】"] = "back"
        return options
