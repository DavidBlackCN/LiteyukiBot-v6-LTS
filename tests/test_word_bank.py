from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.utils.base import resource
from src.utils.base.ly_function import loaded_functions
from src.utils.base.word_bank import (
    clear_word_bank,
    get_reply,
    load_from_dir,
    word_bank,
)


@pytest.fixture(autouse=True)
def preserve_word_bank():
    original = {key: set(values) for key, values in word_bank.items()}
    original_packs = list(resource.get_loaded_resource_packs())
    original_functions = dict(loaded_functions)
    clear_word_bank()
    yield
    clear_word_bank()
    word_bank.update(original)
    resource.get_loaded_resource_packs().clear()
    resource.get_loaded_resource_packs().extend(original_packs)
    loaded_functions.clear()
    loaded_functions.update(original_functions)


def _write_pack(path: Path, data: dict[str, list[str]]) -> None:
    (path / "word_bank").mkdir(parents=True)
    (path / "metadata.yml").write_text(
        "name: test\ndescription: test\nversion: 1.0.0\n", encoding="utf-8"
    )
    (path / "word_bank" / "data.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def _write_template_pack(path: Path, value: str) -> None:
    (path / "templates").mkdir(parents=True)
    (path / "metadata.yml").write_text(
        "name: test\ndescription: test\nversion: 1.0.0\n", encoding="utf-8"
    )
    (path / "templates" / "shared.txt").write_text(value, encoding="utf-8")


def test_word_bank_loads_json_and_returns_one_of_the_replies(tmp_path: Path) -> None:
    word_dir = tmp_path / "word_bank"
    word_dir.mkdir()
    (word_dir / "data.json").write_text(
        json.dumps({"hello": ["a", "b"]}), encoding="utf-8"
    )

    load_from_dir(str(word_dir))

    assert word_bank["hello"] == {"a", "b"}
    assert get_reply(["missing", "hello"]) in {"a", "b"}


def test_empty_word_bank_entry_has_no_reply() -> None:
    word_bank["empty"] = set()

    assert get_reply(["empty"]) is None


def test_word_bank_merges_same_keyword_from_multiple_resources(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_pack(first, {"hello": ["A"]})
    _write_pack(second, {"hello": ["B"]})

    load_from_dir(str(first / "word_bank"))
    load_from_dir(str(second / "word_bank"))

    assert word_bank["hello"] == {"A", "B"}


def test_full_resource_reload_removes_unloaded_pack_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built_in = tmp_path / "src" / "resources" / "base"
    external = tmp_path / "resources" / "pack_a"
    _write_pack(built_in, {"base": ["base reply"]})
    _write_pack(external, {"only-a": ["A"]})
    (tmp_path / "resources" / "index.json").write_text(
        json.dumps([]), encoding="utf-8"
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        resource, "temp_resource_root", tmp_path / "data" / "liteyuki" / "resources"
    )
    monkeypatch.setattr(
        resource, "temp_extract_root", tmp_path / "data" / "liteyuki" / "temp"
    )

    assert resource.add_resource_pack("pack_a") is True
    resource.load_resources()
    assert word_bank["only-a"] == {"A"}
    assert resource.remove_resource_pack("pack_a") is True

    resource.load_resources()

    assert "only-a" not in word_bank
    assert word_bank["base"] == {"base reply"}


def test_resource_priority_up_down_and_top(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources = tmp_path / "resources"
    _write_pack(resources / "pack_a", {"hello": ["A"]})
    _write_pack(resources / "pack_b", {"hello": ["B"]})
    (resources / "index.json").write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert resource.add_resource_pack("pack_a") is True
    assert resource.add_resource_pack("pack_b") is True

    assert resource.change_priority("pack_b", -1) is True
    assert json.loads((resources / "index.json").read_text(encoding="utf-8")) == [
        "pack_b",
        "pack_a",
    ]

    assert resource.change_priority("pack_b", 1) is True
    assert json.loads((resources / "index.json").read_text(encoding="utf-8")) == [
        "pack_a",
        "pack_b",
    ]

    assert resource.change_priority("pack_b", 0) is True
    assert json.loads((resources / "index.json").read_text(encoding="utf-8")) == [
        "pack_b",
        "pack_a",
    ]


def test_builtin_resources_use_explicit_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builtins = tmp_path / "src" / "resources"
    resources = tmp_path / "resources"
    resources.mkdir()
    (resources / "index.json").write_text("[]", encoding="utf-8")
    for name in ("liteyuki_words", "vanilla_resource", "vanilla_language"):
        _write_template_pack(builtins / name, name)

    original_listdir = resource.os.listdir

    def reversed_builtin_listdir(path: str | Path) -> list[str]:
        if Path(path) == Path("src/resources"):
            return ["liteyuki_words", "vanilla_resource", "vanilla_language"]
        return original_listdir(path)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(resource.os, "listdir", reversed_builtin_listdir)
    monkeypatch.setattr(
        resource, "temp_resource_root", tmp_path / "data" / "liteyuki" / "resources"
    )

    resource.load_resources()

    assert (resource.temp_resource_root / "templates" / "shared.txt").read_text(
        encoding="utf-8"
    ) == "liteyuki_words"
    assert [pack.folder for pack in resource.get_loaded_resource_packs()] == [
        "liteyuki_words",
        "vanilla_resource",
        "vanilla_language",
    ]


def test_external_resource_priority_still_overrides_builtins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_template_pack(
        tmp_path / "src" / "resources" / "vanilla_resource", "builtin"
    )
    _write_template_pack(tmp_path / "resources" / "external_high", "high")
    _write_template_pack(tmp_path / "resources" / "external_low", "low")
    (tmp_path / "resources" / "index.json").write_text(
        json.dumps(["external_high", "external_low"]), encoding="utf-8"
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        resource, "temp_resource_root", tmp_path / "data" / "liteyuki" / "resources"
    )

    resource.load_resources()

    assert (resource.temp_resource_root / "templates" / "shared.txt").read_text(
        encoding="utf-8"
    ) == "high"
    assert [pack.folder for pack in resource.get_loaded_resource_packs()] == [
        "external_high",
        "external_low",
        "vanilla_resource",
    ]
