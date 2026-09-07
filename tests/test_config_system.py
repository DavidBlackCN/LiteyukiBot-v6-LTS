from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml

from liteyuki.config import BasicConfig, ensure_config_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_first_start_copies_maintained_example_verbatim(tmp_path: Path) -> None:
    template = tmp_path / "config.example.yml"
    target = tmp_path / "config.yml"
    template.write_bytes((PROJECT_ROOT / "config.example.yml").read_bytes())

    assert ensure_config_file(str(target), str(template)) is True
    assert target.read_bytes() == template.read_bytes()
    assert ensure_config_file(str(target), str(template)) is False

    generated = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert generated["command_start"] == ["/"]
    assert generated["nickname"] == ["Liteyuki"]
    assert generated["default_language"] == "zh-CN"
    assert generated["default_interact_language"] == "zh-CN"
    assert generated["satori"] == {"enable": False}
    assert "chromium_path" not in generated


def test_first_start_falls_back_to_basic_config_without_template(tmp_path: Path) -> None:
    target = tmp_path / "config.yml"
    missing_template = tmp_path / "missing.example.yml"

    assert ensure_config_file(str(target), str(missing_template)) is True
    generated = yaml.safe_load(target.read_text(encoding="utf-8"))
    defaults = BasicConfig()

    assert generated["command_start"] == defaults.command_start == ["/"]
    assert generated["nickname"] == defaults.nickname == ["Liteyuki"]
    assert generated["default_language"] == defaults.default_language == "zh-CN"
    assert generated["default_interact_language"] == "zh-CN"
    assert generated["satori"] == {"enable": False}
    assert "chromium_path" not in generated


def test_yaml_reaches_nonebot_and_legacy_get_config_does_not_reread(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "plugin.yml").write_text(
        "complex_plugin_option: from-split-file\n", encoding="utf-8"
    )
    (tmp_path / "config.yml").write_text(
        "plugin_setting: from-root\ncommand_start: ['/']\n", encoding="utf-8"
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    source = textwrap.dedent(
        """
        import nonebot
        from pydantic import BaseModel
        from nonebot import get_plugin_config
        from liteyuki.config import load_config_in_default

        loaded = load_config_in_default()
        assert loaded["plugin_setting"] == "from-root"
        assert loaded["complex_plugin_option"] == "from-split-file"

        nonebot.init(**loaded)

        class PluginConfig(BaseModel):
            plugin_setting: str
            complex_plugin_option: str

        plugin_config = get_plugin_config(PluginConfig)
        assert plugin_config.plugin_setting == "from-root"
        assert plugin_config.complex_plugin_option == "from-split-file"

        from src.utils.base import config as compat

        def disk_read_is_a_regression(*args, **kwargs):
            raise AssertionError("get_config reread config.yml")

        compat.load_from_yaml = disk_read_is_a_regression
        assert compat.get_config("plugin_setting") == "from-root"
        assert compat.get_config("plugin_setting") == "from-root"

        original_get_driver = compat.nonebot.get_driver
        compat.nonebot.get_driver = lambda: (_ for _ in ()).throw(ValueError())
        assert compat.get_config("complex_plugin_option") == "from-split-file"
        compat.nonebot.get_driver = original_get_driver
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
