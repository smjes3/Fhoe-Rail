"""utils/core/map_info.py —— 地图文件名解析、目录扫描与缓存。"""

import pytest

from utils.config.config import ConfigurationManager
from utils.core.map_info import MapInfo


def write_map_file(root, version, filename, name="1-1 空间站「黑塔」", author="tester"):
    folder = root / "map" / version
    folder.mkdir(parents=True, exist_ok=True)
    import json

    (folder / filename).write_text(
        json.dumps(
            {"name": name, "author": author, "start": [], "map": []},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return folder / filename


class TestExtractKeys:
    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("map_1-1_0.json", ("1", "1_0")),
            ("map_12-3_4.json", ("12", "3_4")),
            ("map_2-10_1.json", ("2", "10_1")),
        ],
    )
    def test_splits_filename_into_keys(self, filename, expected):
        assert MapInfo.extract_keys(filename) == expected

    def test_filename_without_dash_raises(self):
        """命名不符合约定时直接抛 ValueError —— 一个坏文件名会让整个版本加载失败。"""
        with pytest.raises(ValueError):
            MapInfo.extract_keys("map_11_0.json")


class TestSortJsonFiles:
    def test_sorts_numerically_not_lexically(self):
        files = ["map_1-10_0.json", "map_1-2_0.json", "map_1-1_0.json"]
        assert MapInfo.sort_json_files(files) == [
            "map_1-1_0.json",
            "map_1-2_0.json",
            "map_1-10_0.json",
        ]

    def test_sorts_across_planets(self):
        files = ["map_3-1_0.json", "map_1-2_0.json", "map_2-1_0.json"]
        assert MapInfo.sort_json_files(files) == [
            "map_1-2_0.json",
            "map_2-1_0.json",
            "map_3-1_0.json",
        ]

    def test_empty_list(self):
        assert MapInfo.sort_json_files([]) == []


class TestFormatMapDataFirstName:
    def test_builds_prefixed_display_name(self):
        assert (
            MapInfo.format_map_data_first_name("1", "1", "1-1 空间站「黑塔」")
            == "1-1 1"
        )

    def test_strips_spaces_before_truncating(self):
        assert MapInfo.format_map_data_first_name("2", "3", "2-3 雅利洛-Ⅵ 大矿区") == "2-3 2"

    def test_map_name_without_dash_raises(self):
        with pytest.raises(ValueError):
            MapInfo.format_map_data_first_name("1", "1", "没有分隔符的名字")


class TestReadMapsVersions:
    def test_lists_subdirectories(self, isolated_cwd):
        (isolated_cwd / "map" / "default").mkdir(parents=True)
        (isolated_cwd / "map" / "HuangQuan").mkdir()
        (isolated_cwd / "map" / "readme.txt").write_text("x", encoding="utf-8")

        assert sorted(MapInfo.read_maps_versions()) == ["HuangQuan", "default"]

    def test_missing_map_dir_raises(self, isolated_cwd):
        with pytest.raises(FileNotFoundError):
            MapInfo.read_maps_versions()

    def test_missing_map_dir_logs_error(self, isolated_cwd, log_records):
        with pytest.raises(FileNotFoundError):
            MapInfo.read_maps_versions()
        assert any("地图文件目录不存在" in r["message"] for r in log_records)


class TestReadMaps:
    def test_reads_single_file(self, isolated_cwd):
        write_map_file(isolated_cwd, "default", "map_1-1_0.json")

        json_files, map_list_map, version = MapInfo.read_maps("default")

        assert json_files == ["map_1-1_0.json"]
        assert version == "default"
        assert map_list_map == {"1": {"1_0": ["1-1 空间站「黑塔」", "1-1 1"]}}

    def test_groups_multiple_submaps_under_one_planet(self, isolated_cwd):
        write_map_file(isolated_cwd, "default", "map_1-1_0.json")
        write_map_file(isolated_cwd, "default", "map_1-2_0.json")

        _, map_list_map, _ = MapInfo.read_maps("default")

        assert list(map_list_map) == ["1"]
        assert sorted(map_list_map["1"]) == ["1_0", "2_0"]

    def test_missing_version_dir_raises(self, isolated_cwd):
        (isolated_cwd / "map").mkdir()
        with pytest.raises(FileNotFoundError):
            MapInfo.read_maps("nope")

    def test_result_is_cached_until_directory_changes(self, isolated_cwd):
        write_map_file(isolated_cwd, "default", "map_1-1_0.json")

        first = MapInfo.read_maps("default")
        second = MapInfo.read_maps("default")

        assert first is second, "目录 mtime 未变时应复用上次的解析结果"

    def test_cache_is_invalidated_when_a_file_is_added(self, isolated_cwd):
        import os

        write_map_file(isolated_cwd, "default", "map_1-1_0.json")
        first = MapInfo.read_maps("default")

        write_map_file(isolated_cwd, "default", "map_2-1_0.json")
        folder = isolated_cwd / "map" / "default"
        os.utime(folder, (os.path.getmtime(folder) + 10, os.path.getmtime(folder) + 10))

        second = MapInfo.read_maps("default")

        assert second is not first
        assert "map_2-1_0.json" in second[0]

    def test_corrupt_json_propagates(self, isolated_cwd, log_records):
        folder = isolated_cwd / "map" / "default"
        folder.mkdir(parents=True)
        (folder / "map_1-1_0.json").write_text("{ broken", encoding="utf-8")

        with pytest.raises(Exception):
            MapInfo.read_maps("default")
        assert any("处理地图文件失败" in r["message"] for r in log_records)


class TestMapInfoProperties:
    @pytest.fixture
    def info(self, make_instance, isolated_cwd):
        write_map_file(isolated_cwd, "default", "map_1-1_0.json")
        write_map_file(isolated_cwd, "default", "map_2-1_0.json")
        return make_instance(
            MapInfo, cfg=ConfigurationManager(), _map_version="default"
        )

    def test_map_list_is_sorted(self, info):
        assert info.map_list == ["map_1-1_0.json", "map_2-1_0.json"]

    def test_map_list_map_groups_by_planet(self, info):
        assert sorted(info.map_list_map) == ["1", "2"]

    def test_map_version_tracks_config_changes(self, info):
        assert info.map_version == "default"
        info.cfg.config_file["map_version"] = "HuangQuan"
        assert info.map_version == "HuangQuan"

    def test_map_version_is_cached_when_config_unchanged(self, info):
        assert info.map_version is info.map_version
