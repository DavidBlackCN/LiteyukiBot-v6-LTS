from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


TEMPLATE_ROOT = Path("src/resources/vanilla_resource/templates")


def test_status_template_keeps_shared_contract_and_renders_data() -> None:
    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_ROOT),
        autoescape=select_autoescape(("html",)),
    )
    rendered = environment.get_template("status.html").render(
        data={"liteyuki": {"name": "Test Bot"}}
    )

    assert 'id="data"' in rendered
    assert 'id="bot-template"' in rendered
    assert 'id="device-info"' in rendered
    assert 'id="hardware-info"' in rendered
    assert 'id="disk-info"' in rendered
    assert "Test Bot" in rendered
    assert "cdnjs.cloudflare.com" not in rendered


def test_vanilla_resource_has_no_trim_branding_or_hardcoded_qq_credits() -> None:
    forbidden = (
        "trimo",
        "睿乐",
        "灵温",
        "2647547478",
        "2751454815",
    )
    text_suffixes = {".css", ".html", ".js", ".md", ".txt", ".yml"}
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in TEMPLATE_ROOT.parent.rglob("*")
        if path.is_file() and path.suffix.lower() in text_suffixes
    ).lower()

    for value in forbidden:
        assert value.lower() not in text


def test_vanilla_resource_keeps_shared_assets_and_removes_legacy_visuals() -> None:
    for relative_path in (
        "css/card.css",
        "css/fonts.css",
        "js/card.js",
        "img/liteyuki.png",
        "fonts/MiSans/MiSans-Normal.woff2",
    ):
        assert (TEMPLATE_ROOT / relative_path).is_file()

    for legacy_name in (
        "trimo.png",
        "litetrimo.png",
        "litetrimo.pdn",
        "bg1.jpg",
        "bg2.jpg",
        "bg3.jpg",
        "bg4.jpg",
        "bg5.jpg",
        "bg6.jpg",
        "bg7.jpg",
        "2023-08-05_20.06.51.png",
    ):
        assert not (TEMPLATE_ROOT / "img" / legacy_name).exists()


def test_status_ui_uses_lts_brand_and_native_charts() -> None:
    status_html = (TEMPLATE_ROOT / "status.html").read_text(encoding="utf-8")
    status_js = (TEMPLATE_ROOT / "js" / "status.js").read_text(encoding="utf-8")
    card_css = (TEMPLATE_ROOT / "css" / "card.css").read_text(encoding="utf-8")
    status_css = (TEMPLATE_ROOT / "css" / "status.css").read_text(encoding="utf-8")

    assert "LiteyukiBot v6 LTS" in status_html
    assert "liteyukiData[\"name\"]" in status_js
    assert "conic-gradient" in status_css
    assert "border-radius" in card_css
    assert "box-shadow" in card_css
    assert "echarts" not in status_html.lower()
    assert "echarts" not in status_js.lower()


def test_status_ui_has_scoped_background_and_real_bot_avatar_contract() -> None:
    status_html = (TEMPLATE_ROOT / "status.html").read_text(encoding="utf-8")
    status_js = (TEMPLATE_ROOT / "js" / "status.js").read_text(encoding="utf-8")
    status_css = (TEMPLATE_ROOT / "css" / "status.css").read_text(encoding="utf-8")

    assert 'class="brand-logo" src="./img/liteyuki.png"' in status_html
    assert 'id="summary-info"' in status_html
    assert 'id="bots-info"' in status_html
    assert 'id="status-background-image"' in status_html
    assert 'image.src = background["image"]' in status_js
    assert "[status/background] image loaded" in status_js
    assert "[status/background] image load failed" in status_js
    assert "--status-background-image" not in status_js
    assert "--status-background-image" not in status_css
    assert "has-remote-background" in status_js
    assert 'image.src = bot["icon"]' in status_js
    assert ".status-page.has-remote-background" in status_css
    assert "object-fit: cover" in status_css
    assert "position: fixed" not in status_css
    assert "position: absolute" in status_css
    assert "backdrop-filter" in status_css
    assert "blur(8px)" in status_css
    assert "rgba(255, 255, 255, 0.84)" in status_css
    assert "rgba(255, 255, 255, 0.78)" in status_css


def test_status_background_config_is_safe_by_default() -> None:
    config = Path("config.example.yml").read_text(encoding="utf-8")

    assert "status_background_enabled: false" in config
    assert 'status_background_url: ""' in config
    assert "status_background_timeout: 6" in config
    assert "status_background_mask: 0.35" in config
