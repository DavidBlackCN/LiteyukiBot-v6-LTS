"""Regression tests for Liteyuki v6 Issue #90.

The tests only exercise NoneBot plugin registration. They never start the driver,
so nonebot-plugin-htmlrender does not launch Playwright or Chromium.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_python(source: str, **extra_env: str) -> None:
    env = os.environ.copy()
    env.update(extra_env)
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, (
        f"subprocess failed with code {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def _write_require_plugin(directory: Path, module_name: str) -> None:
    (directory / f"{module_name}.py").write_text(
        textwrap.dedent(
            """
            from nonebot import require

            require("nonebot_plugin_htmlrender")

            from nonebot_plugin_htmlrender import (
                html_to_pic,
                md_to_pic,
                template_to_pic,
            )
            """
        ),
        encoding="utf-8",
    )


def test_runtime_preloads_htmlrender_before_liteyuki_main() -> None:
    _run_python(
        """
        import nonebot
        import liteyuki.utils

        liteyuki.utils.IS_MAIN_PROCESS = False
        from src.liteyuki_plugins import liteyukibot_plugin_nonebot as starter

        load_order = []
        real_load_plugin = nonebot.load_plugin

        def load_plugin(module_path):
            load_order.append(str(module_path))
            if module_path == "src.liteyuki_main":
                return object()
            return real_load_plugin(module_path)

        nonebot.load_plugin = load_plugin
        nonebot.run = lambda *args, **kwargs: None
        starter.driver_manager.init = lambda config: None
        starter.adapter_manager.init = lambda config: None
        starter.adapter_manager.register = lambda: None

        starter.nb_run()

        plugin = nonebot.get_plugin("nonebot_plugin_htmlrender")
        assert plugin is not None
        assert load_order.index("nonebot_plugin_htmlrender") < load_order.index(
            "src.liteyuki_main"
        )
        """
    )


def test_third_party_plugin_can_require_preloaded_htmlrender(tmp_path: Path) -> None:
    module_name = "issue90_require_plugin"
    _write_require_plugin(tmp_path, module_name)

    _run_python(
        """
        import os
        import sys

        import nonebot
        import liteyuki.utils

        liteyuki.utils.IS_MAIN_PROCESS = False
        from src.liteyuki_plugins import liteyukibot_plugin_nonebot as starter

        nonebot.init()
        starter._load_htmlrender_plugin()
        assert nonebot.get_plugin("nonebot_plugin_htmlrender") is not None

        sys.path.insert(0, os.environ["ISSUE90_PLUGIN_DIR"])
        plugin = nonebot.load_plugin(os.environ["ISSUE90_PLUGIN_NAME"])
        assert plugin is not None
        assert nonebot.get_plugin(os.environ["ISSUE90_PLUGIN_NAME"]) is plugin
        """,
        ISSUE90_PLUGIN_DIR=str(tmp_path),
        ISSUE90_PLUGIN_NAME=module_name,
    )


def test_runtime_can_dynamically_load_plugin_requiring_htmlrender(
    tmp_path: Path,
) -> None:
    module_name = "issue90_dynamic_plugin"
    _write_require_plugin(tmp_path, module_name)

    _run_python(
        """
        import os
        import sys

        import nonebot
        import liteyuki.utils

        liteyuki.utils.IS_MAIN_PROCESS = False
        from src.liteyuki_plugins import liteyukibot_plugin_nonebot as starter

        nonebot.init()
        starter._load_htmlrender_plugin()

        # This mirrors Pacman's post-install nonebot.load_plugin(module_name).
        sys.path.insert(0, os.environ["ISSUE90_PLUGIN_DIR"])
        plugin = nonebot.load_plugin(os.environ["ISSUE90_PLUGIN_NAME"])

        assert plugin is not None
        assert "nonebot_plugin_htmlrender" in sys.modules
        assert nonebot.get_plugin("nonebot_plugin_htmlrender") is not None
        """,
        ISSUE90_PLUGIN_DIR=str(tmp_path),
        ISSUE90_PLUGIN_NAME=module_name,
    )


def test_plain_import_is_not_mistaken_for_plugin_registration() -> None:
    _run_python(
        """
        import sys

        import nonebot
        import liteyuki.utils

        liteyuki.utils.IS_MAIN_PROCESS = False
        from src.liteyuki_plugins import liteyukibot_plugin_nonebot as starter

        nonebot.init()
        import nonebot_plugin_htmlrender

        assert "nonebot_plugin_htmlrender" in sys.modules
        assert nonebot.get_plugin("nonebot_plugin_htmlrender") is None

        try:
            starter._load_htmlrender_plugin()
        except RuntimeError as error:
            assert "was not registered with NoneBot PluginManager" in str(error)
        else:
            raise AssertionError("plain import unexpectedly passed registration check")
        """
    )
