"""utils/core/log.py —— 版本号获取、日志 patcher、webhook 转发。"""

import builtins
import json

import pytest

import utils.core.log as log_module
from utils.core.log import fetch_php_file_content, get_folder_modified_time, get_ver, log


@pytest.fixture
def version_file(isolated_cwd):
    def _write(content):
        (isolated_cwd / "version.txt").write_text(content, encoding="utf-8")
        return isolated_cwd / "version.txt"

    return _write


class TestGetVer:
    def test_reads_version_txt(self, version_file):
        version_file("4.5.0_260828")
        assert get_ver() == "4.5.0_260828"

    def test_strips_whitespace(self, version_file):
        version_file("  1.2.3\n")
        assert get_ver() == "1.2.3"

    def test_empty_file_falls_back_to_map_mtime(self, version_file, isolated_cwd):
        version_file("")
        (isolated_cwd / "map").mkdir()
        result = get_ver()
        assert result != ""
        assert result != "00000000"
        assert len(result) == 8 and result.isdigit()

    def test_missing_file_and_missing_map_dir_returns_sentinel(self, isolated_cwd):
        (isolated_cwd / "version.txt").unlink()
        assert get_ver() == "00000000"

    def test_failure_is_silent(self, isolated_cwd, log_records):
        """get_ver 在 loguru patcher 里被调用，出错时绝不能写日志（否则无限递归）。"""
        (isolated_cwd / "version.txt").unlink()
        get_ver()
        assert log_records == []


class TestGetFolderModifiedTime:
    def test_returns_month_day_hour_minute(self, tmp_path):
        target = tmp_path / "folder"
        target.mkdir()
        assert get_folder_modified_time(target) is not None
        month, day, hour, minute = get_folder_modified_time(target)
        assert 1 <= month <= 12
        assert 0 <= hour <= 23
        assert 0 <= minute <= 59

    def test_returns_none_for_missing_folder(self, tmp_path):
        assert get_folder_modified_time(tmp_path / "nope") is None


class TestUpdateExtra:
    def test_adds_module_and_version_fields(self):
        record = {"module": "m", "function": "f", "line": 7}
        log_module.update_extra(record)
        assert record["new_module"] == "m.f:7"
        assert record["VER"]

    def test_raises_when_record_is_missing_keys(self):
        """patcher 依赖 record 结构，键缺失时会抛 KeyError —— 记录当前契约。"""
        with pytest.raises(KeyError):
            log_module.update_extra({})


class TestLoggingCost:
    @pytest.mark.xfail(
        strict=True,
        reason="loguru 的 patcher 对每条日志都调用 get_ver()，每次都 open('version.txt')；"
        "version.txt 是构建产物、进程内不变，应缓存",
    )
    def test_logging_does_not_read_version_file_per_record(self, monkeypatch, isolated_cwd):
        (isolated_cwd / "version.txt").write_text("v1", encoding="utf-8")
        reads = []
        real_open = builtins.open

        def counting_open(file, *args, **kwargs):
            if str(file) == "version.txt":
                reads.append(file)
            return real_open(file, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", counting_open)
        # loguru 在没有任何 handler 时会直接跳过整条记录（patcher 也不会执行），
        # 所以必须挂一个空 handler，否则这个测试什么都测不到。
        from utils.core.log import logger

        handler_id = logger.add(lambda message: None, level="DEBUG")
        try:
            for _ in range(20):
                log.info("hello")
        finally:
            logger.remove(handler_id)

        assert len(reads) < 20


class TestWebhookAndLog:
    def test_returns_early_without_url(self, log_records, monkeypatch):
        sent = []
        monkeypatch.setattr(log_module, "post", lambda *a, **k: sent.append(a))
        log_module.webhook_and_log("hello")
        assert sent == []
        assert any("hello" in r["message"] for r in log_records)

    def test_posts_when_url_configured(self, isolated_cwd, monkeypatch):
        config = json.loads((isolated_cwd / "config.json").read_text(encoding="utf-8"))
        config["webhook_url"] = "https://example.invalid/hook"
        (isolated_cwd / "config.json").write_text(
            json.dumps(config, ensure_ascii=False), encoding="utf-8"
        )
        sent = []
        monkeypatch.setattr(log_module, "post", lambda url, **kw: sent.append((url, kw)))

        log_module.webhook_and_log("hello")

        assert sent and sent[0][0] == "https://example.invalid/hook"
        assert sent[0][1]["json"] == {"content": "hello"}

    def test_post_failure_is_swallowed(self, isolated_cwd, monkeypatch, log_records):
        config = json.loads((isolated_cwd / "config.json").read_text(encoding="utf-8"))
        config["webhook_url"] = "https://example.invalid/hook"
        (isolated_cwd / "config.json").write_text(
            json.dumps(config, ensure_ascii=False), encoding="utf-8"
        )

        def boom(*args, **kwargs):
            raise RuntimeError("network down")

        monkeypatch.setattr(log_module, "post", boom)
        log_module.webhook_and_log("hello")  # 不应抛出
        assert any("Webhook发送失败" in r["message"] for r in log_records)


class TestFetchPhpFileContent:
    def test_returns_first_successful_response(self, monkeypatch):
        class Response:
            text = "一句土味情话"

            def raise_for_status(self):
                return None

        monkeypatch.setattr(log_module.requests, "get", lambda url, timeout: Response())
        assert fetch_php_file_content() == "一句土味情话"

    def test_returns_empty_when_all_fail(self, monkeypatch):
        import requests as real_requests

        def boom(url, timeout):
            raise real_requests.exceptions.RequestException("nope")

        monkeypatch.setattr(log_module.requests, "get", boom)
        assert fetch_php_file_content() == ""

    @pytest.mark.xfail(
        strict=True,
        reason="第一个 URL 超时就直接 return ''，没有继续尝试列表里的下一个备用接口，"
        "与 for 循环的降级意图矛盾",
    )
    def test_timeout_tries_next_url(self, monkeypatch):
        import requests as real_requests

        attempts = []

        class Response:
            text = "备用接口"

            def raise_for_status(self):
                return None

        def get(url, timeout):
            attempts.append(url)
            if len(attempts) == 1:
                raise real_requests.exceptions.Timeout()
            return Response()

        monkeypatch.setattr(log_module.requests, "get", get)
        assert fetch_php_file_content() == "备用接口"
