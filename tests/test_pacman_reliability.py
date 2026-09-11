from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_lts_constraints_match_requirements() -> None:
    def load_requirements(path: Path) -> dict[str, Requirement]:
        result = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            requirement = Requirement(line)
            result[canonicalize_name(requirement.name)] = requirement
        return result

    requirements = load_requirements(PROJECT_ROOT / "requirements.txt")
    constraints = load_requirements(PROJECT_ROOT / "constraints-lts.txt")
    for name, constraint in constraints.items():
        assert name in requirements
        assert constraint.specifier == requirements[name].specifier


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
    assert result.returncode == 0, result.stdout + result.stderr


BOOTSTRAP = """
import nonebot
import liteyuki.utils
from nonebot.adapters.onebot.v11 import Adapter

liteyuki.utils.IS_MAIN_PROCESS = False
from src.liteyuki_plugins import liteyukibot_plugin_nonebot as starter

nonebot.init()
nonebot.get_driver().register_adapter(Adapter)
starter._load_htmlrender_plugin()
starter._load_alconna_plugin()
plugin = nonebot.load_plugin("src.nonebot_plugins.liteyuki_pacman")
assert plugin is not None
from src.nonebot_plugins.liteyuki_pacman import npm
"""


def test_registry_resolution_pip_command_constraints_and_no_hot_load() -> None:
    _run_python(
        BOOTSTRAP
        + """
import asyncio
import sys
from types import SimpleNamespace

async def main():
    pip_calls = []

    async def pip_must_not_run(*args, **kwargs):
        raise AssertionError("pip ran for a missing Registry plugin")

    npm.get_store_plugin = lambda name: async_none()
    original_install = npm.npm_install
    npm.npm_install = pip_must_not_run
    store, package, success, output = await npm.install_registry_plugin("missing_plugin")
    assert store is None and package is None and not success

    store_plugin = npm.StorePlugin(
        name="Demo", desc="Demo", module_name="nonebot_plugin_demo",
        project_link="nonebot-plugin-demo"
    )

    async def get_demo(name):
        assert name == "nonebot_plugin_demo"
        return store_plugin

    async def fake_install(package_name, upgrade=False):
        assert package_name == "nonebot-plugin-demo"
        assert upgrade is False
        return True, "installed"

    npm.get_store_plugin = get_demo
    npm.npm_install = fake_install
    npm.nonebot.load_plugin = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("install attempted a hot load")
    )
    store, package, success, output = await npm.install_registry_plugin(
        "nonebot_plugin_demo"
    )
    assert store is store_plugin and package == "nonebot-plugin-demo"
    assert success and output == "installed"

    npm.npm_install = original_install
    original_run = npm.subprocess.run
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    def fake_run(command, **kwargs):
        pip_calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")
    npm.subprocess.run = fake_run
    success, output = await npm.npm_install("nonebot-plugin-demo")
    uninstall_success, uninstall_output = await npm.npm_uninstall(
        "nonebot-plugin-demo"
    )
    npm.subprocess.run = original_run
    assert success and output == "ok"
    assert uninstall_success and uninstall_output == "ok"
    assert sys.stdout is original_stdout and sys.stderr is original_stderr
    command, kwargs = pip_calls[0]
    assert command[:4] == [sys.executable, "-m", "pip", "install"]
    assert "--constraint" in command
    assert str(npm.LTS_CONSTRAINTS) in command
    assert command[command.index("--constraint") + 1] == str(npm.LTS_CONSTRAINTS)
    assert "nonebot-plugin-demo" in command
    assert kwargs["capture_output"] is True
    assert pip_calls[1][0][:5] == [
        sys.executable, "-m", "pip", "uninstall", "-y"
    ]

async def async_none():
    return None

asyncio.run(main())
"""
    )


def test_uninstall_managed_package_and_protect_builtin() -> None:
    _run_python(
        BOOTSTRAP
        + """
import asyncio
from types import SimpleNamespace

class FakeDB:
    def __init__(self):
        self.deleted = []
    def where_one(self, *args, **kwargs):
        return npm.InstalledPlugin(module_name="managed")
    def delete(self, *args):
        self.deleted.append(args)

async def main():
    fake_db = FakeDB()
    npm.plugin_db = fake_db
    npm.is_distribution_installed = lambda package: True

    async def registry_plugin(name):
        return npm.StorePlugin(
            name="Managed", desc="Managed", module_name=name,
            project_link="nonebot-plugin-managed"
        )

    uninstall_calls = []
    async def fake_uninstall(package):
        uninstall_calls.append(package)
        return True, "removed"

    npm.get_store_plugin = registry_plugin
    npm.npm_uninstall = fake_uninstall
    status, output = await npm.uninstall_pacman_plugin("external_managed")
    assert status == "success" and output == "removed"
    assert uninstall_calls == ["nonebot-plugin-managed"]
    assert len(fake_db.deleted) == 1

    uninstall_calls.clear()
    status, output = await npm.uninstall_pacman_plugin("liteyuki_pacman")
    assert status == "protected"
    assert uninstall_calls == []

asyncio.run(main())
"""
    )


def test_global_permissions_and_registry_failure_preserves_cache() -> None:
    _run_python(
        BOOTSTRAP
        + """
import asyncio
import tempfile
from pathlib import Path

async def main():
    for command in (npm.enable_global, npm.disable_global):
        subcommands = {command: object()}
        assert npm.is_global_toggle_request(subcommands)
        assert not npm.can_manage_global(subcommands, False)
        assert npm.can_manage_global(subcommands, True)

    with tempfile.TemporaryDirectory() as directory:
        cache = Path(directory) / "plugins.json"
        original = b'[{"module_name":"cached"}]'
        cache.write_bytes(original)
        npm.REGISTRY_CACHE_PATH = cache

        class FailingSession:
            def __init__(self, *args, **kwargs):
                raise npm.aiohttp.ClientError("offline")

        original_session = npm.aiohttp.ClientSession
        npm.aiohttp.ClientSession = FailingSession
        try:
            assert await npm.npm_update() is False
        finally:
            npm.aiohttp.ClientSession = original_session
        assert cache.read_bytes() == original

asyncio.run(main())
"""
    )


def test_npm_and_rpm_list_default_to_rendered_images() -> None:
    _run_python(
        BOOTSTRAP
        + """
import asyncio
import nonebot
from src.nonebot_plugins.liteyuki_pacman import rpm

npm_command = next(
    matcher.command()
    for matcher in nonebot.get_plugin("liteyuki_pacman").matcher
    if hasattr(matcher, "command") and str(matcher.command().command) == "npm"
)
result = npm_command.parse("npm list")
assert result.matched
assert result.subcommands["list"].options["markdown"].value is True

async def main():
    calls = []

    async def fake_md_to_pic(markdown):
        calls.append(("render", markdown))
        return b"image-bytes"

    class FakeUniMessage:
        @staticmethod
        def image(*, raw):
            calls.append(("image", raw))
            return ("image", raw)

        @staticmethod
        async def send(message):
            calls.append(("send", message))

    rpm.md_to_pic = fake_md_to_pic
    rpm.UniMessage = FakeUniMessage
    await rpm._send_list_image("# resources")
    assert calls == [
        ("render", "# resources"),
        ("image", b"image-bytes"),
        ("send", ("image", b"image-bytes")),
    ]

asyncio.run(main())
"""
    )
