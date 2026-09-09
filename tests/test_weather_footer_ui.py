from pathlib import Path


def test_weather_footer_has_readable_remote_background_style() -> None:
    css = Path("src/resources/liteyuki_weather/templates/css/weather_now.css").read_text(
        encoding="utf-8"
    )
    assert ".card-background-page.has-remote-background .attribution-box" in css
    assert "background: rgba(255, 255, 255, 0.92)" in css
    assert ".attribution-box:has(#attribution-info:empty)" in css
