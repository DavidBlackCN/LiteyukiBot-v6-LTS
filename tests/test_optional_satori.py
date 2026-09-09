"""Regression coverage for the optional Satori adapter boundary."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_without_satori(source: str) -> subprocess.CompletedProcess[str]:
    blocker = """
import importlib.abc
import importlib.util
import sys
from pathlib import Path

class BlockSatori(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "nonebot.adapters.satori" or fullname.startswith(
            "nonebot.adapters.satori."
        ):
            raise ModuleNotFoundError(
                "No module named 'nonebot.adapters.satori'",
                name="nonebot.adapters.satori",
            )
        return None

sys.meta_path.insert(0, BlockSatori())
ROOT = Path.cwd()

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(blocker + source)],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    )


def test_disabled_satori_does_not_import_optional_adapter() -> None:
    result = run_without_satori(
        """
import os
import nonebot

os.environ.pop("SATORI_CLIENTS", None)
nonebot.init()
manager_root = ROOT / "src/liteyuki_plugins/liteyukibot_plugin_nonebot/nb_utils/adapter_manager"
satori = load_module("test_satori_manager", manager_root / "satori.py")
onebot = load_module("test_onebot_manager", manager_root / "onebot.py")

satori.init({"satori": {"enable": False}})
onebot.register()
satori.register()
assert nonebot.get_adapter("OneBot V11")
assert nonebot.get_adapter("OneBot V12")
assert "SATORI_CLIENTS" not in os.environ
"""
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "uniseg adapter satori" not in result.stderr


def test_enabled_satori_without_adapter_has_clear_error() -> None:
    result = run_without_satori(
        """
import os
import nonebot

os.environ.pop("SATORI_CLIENTS", None)
nonebot.init()
satori = load_module(
    "test_satori_manager",
    ROOT / "src/liteyuki_plugins/liteyukibot_plugin_nonebot/nb_utils/adapter_manager/satori.py",
)

config = {"satori": {"enable": True, "hosts": [{"host": "127.0.0.1"}]}}
satori.init(config)
assert "SATORI_CLIENTS" in os.environ
try:
    satori.register()
except RuntimeError as error:
    assert "nonebot-adapter-satori" in str(error)
else:
    raise AssertionError("missing optional Satori adapter was not rejected")
"""
    )
    assert result.returncode == 0, result.stdout + result.stderr
