import os
import subprocess
import sys
import textwrap
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


WEATHER_ROOT = Path("src/resources/liteyuki_weather/templates")
STATISTICS_ROOT = Path("src/resources/liteyuki_statistics/templates")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _render(root: Path, name: str, data: object) -> str:
    environment = Environment(
        loader=FileSystemLoader(root),
        autoescape=select_autoescape(("html",)),
    )
    return environment.get_template(name).render(data=data)


def _run_python(source: str) -> None:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    )
    assert result.returncode == 0, (
        f"subprocess failed with code {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_weather_card_keeps_data_contract_and_attribution() -> None:
    html = _render(
        WEATHER_ROOT,
        "weather_now.html",
        {
            "location": {"name": "深圳"},
            "current": {"temperature": "30"},
            "hourly": [],
            "daily": [],
            "attributions": ["QWeather"],
        },
    )

    for element_id in (
        "data",
        "weather-info",
        "sub-info",
        "hours-info",
        "days-info",
        "attribution-info",
    ):
        assert f'id="{element_id}"' in html
    assert 'id="hourly-item-template"' in html
    assert 'id="daily-item-template"' in html
    assert "QWeather" in html


def test_statistics_cards_keep_message_and_ranking_contracts() -> None:
    message_html = _render(
        STATISTICS_ROOT,
        "stat_msg.html",
        [{"name": "统计消息", "times": [1, 2], "counts": [3, 4]}],
    )
    rank_html = _render(
        STATISTICS_ROOT,
        "stat_rank.html",
        {"name": "发言排名", "ranking": [{"name": "10001", "count": 5}]},
    )

    assert 'id="sign-chart-template"' in message_html
    assert 'id="charts"' in message_html
    assert 'id="row-template"' in rank_html
    assert 'id="rank-title"' in rank_html
    assert 'id="rank-list"' in rank_html
    assert '"counts"' in message_html
    assert '"ranking"' in rank_html


def test_plugin_cards_reuse_base_ui_without_external_components() -> None:
    templates = (
        WEATHER_ROOT / "weather_now.html",
        STATISTICS_ROOT / "stat_msg.html",
        STATISTICS_ROOT / "stat_rank.html",
    )
    for path in templates:
        html = path.read_text(encoding="utf-8")
        assert "./css/card.css" in html
        assert "./css/fonts.css" in html
        assert "./js/card.js" in html
        assert "cdnjs.cloudflare.com" not in html
        assert "echarts" not in html.lower()

    scripts = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            STATISTICS_ROOT / "js" / "stat_msg.js",
            STATISTICS_ROOT / "js" / "stat_rank.js",
        )
    )
    assert "echarts" not in scripts.lower()
    assert "锅炉" not in scripts
    assert "云裳工作室" not in scripts


def test_plugin_card_styles_use_base_ui_tokens() -> None:
    styles = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            WEATHER_ROOT / "css" / "weather_now.css",
            STATISTICS_ROOT / "css" / "stat_msg.css",
            STATISTICS_ROOT / "css" / "stat_rank.css",
        )
    )

    for token in (
        "--card-bg",
        "--card-radius",
        "--color-primary",
        "--color-primary-soft",
        "--main-text-color",
        "--sub-text-color",
        "--tip-text-color",
    ):
        assert token in styles


def test_statistics_plugin_commands_still_load_and_parse() -> None:
    _run_python(
        """
        import nonebot
        import liteyuki.utils

        liteyuki.utils.IS_MAIN_PROCESS = False
        from src.liteyuki_plugins import liteyukibot_plugin_nonebot as starter

        nonebot.init()
        starter._load_htmlrender_plugin()
        starter._load_alconna_plugin()
        plugin = nonebot.load_plugin("src.nonebot_plugins.liteyuki_statistics")
        assert plugin is not None

        from src.nonebot_plugins.liteyuki_statistics.stat_matchers import stat_msg

        assert nonebot.get_plugin("liteyuki_statistics") is plugin
        assert stat_msg.command.parse("statistic message").matched
        assert stat_msg.command.parse("statistic rank").matched
        assert stat_msg.command.parse("stat message").matched
        assert "/" in nonebot.get_driver().config.command_start
        """
    )
