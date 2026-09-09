from pathlib import Path


def test_detail_card_and_footer_use_explicit_flex_gap() -> None:
    css = Path("src/resources/liteyuki_help_menu/templates/css/help_menu.css").read_text(
        encoding="utf-8"
    )
    assert ".help-menu .card-content" in css
    assert "flex-direction: column" in css
    assert "gap: 20px" in css
    assert ".help-menu #content > .info-box" in css
    assert ".help-menu footer p + p" in css
    assert ".has-remote-background footer.info-box" in css
