# LiteyukiBot v6 LTS maintenance guide

## Project scope

This repository is a self-maintained LTS fork of LiteyukiBot v6. Preserve the
existing Liteyuki v6 process, plugin, configuration, resource, and database
architecture. Maintenance priorities are, in order:

1. Runtime stability
2. OneBot V11/V12 compatibility
3. Existing Liteyuki v6 behavior
4. Third-party NoneBot plugin compatibility
5. Small, reviewable changes
6. New versions or refactors

Do not migrate to Liteyuki v7 or turn a compatibility fix into an architectural
rewrite.

## Repository map and startup

- `main.py` is the application entry point. It loads the default configuration
  and starts `LiteyukiBot`.
- `liteyuki/` is the v6 framework/package and process-management layer.
- `src/liteyuki_plugins/` contains plugins running in the Liteyuki main process.
- `src/liteyuki_plugins/liteyukibot_plugin_nonebot/` starts NoneBot in its own
  managed process.
- `src/liteyuki_main/` is the NoneBot-side Liteyuki core. Its loader scans
  `src/nonebot_plugins`, then database-recorded third-party plugins and the local
  `plugins/` directory when safe mode is off.
- `src/nonebot_plugins/` contains built-in NoneBot plugins; `src/resources/`
  contains their built-in resource packs.
- `tests/` is the current pytest regression suite. `BUILTIN_PLUGINS.md` is useful
  for feature discovery, but source and tests are authoritative.

Keep the NoneBot initialization order intact unless the task requires changing
it: initialize NoneBot and drivers, register OneBot V11/V12 (and an enabled
optional adapter), register `nonebot_plugin_htmlrender`, register
`nonebot_plugin_alconna`, load `src.liteyuki_main`, then load built-in and
third-party plugins. Loading htmlrender through NoneBot's PluginManager before
other plugins is required by the Liteyuki v6 Issue #90 compatibility fix.
Changes to this order require startup tests plus built-in and dynamic-plugin
loading tests. Do not hide new critical loading failures with broad exception
handling.

## Dependency policy

- `requirements.txt` is the application runtime dependency source.
- `constraints-lts.txt` is the constraint set passed by Pacman/pip while
  installing third-party plugins. It protects the LTS core stack.
- `pyproject.toml` is only for building the Liteyuki framework/package. It is not
  the application's dependency source, and this repository must not be treated
  as a conventional nb-cli project.

The current protected baseline is:

- `nonebot2[fastapi,httpx,websockets]>=2.5.0,<2.6`
- `nonebot-adapter-onebot~=2.4.3`
- `nonebot-plugin-alconna>=0.62.1,<0.63`
- `nonebot-plugin-uninfo>=0.11.2,<0.12`
- `arclet-alconna>=1.8.44,<1.9`
- `arclet-alconna-tools>=0.7.12,<0.8`
- `tarina>=0.7.5,<0.8`
- `pydantic==2.8.2`
- `nonebot-plugin-htmlrender[playwright]>=0.8.0,<0.9` (the constraints file
  intentionally omits the extra while constraining the same distribution)

When changing a core dependency, inspect and synchronize the corresponding
entries in both dependency files. Also decide whether Pacman's
`PROTECTED_DISTRIBUTIONS` must change. Third-party installation must not silently
upgrade, downgrade, uninstall, or replace a protected distribution. Prefer
versions/ranges proven by an actual runtime test; do not broaden ranges or batch
upgrade unrelated packages without evidence.

## htmlrender compatibility

This LTS uses `nonebot-plugin-htmlrender` 0.8.x with the Playwright provider.
`src/utils/message/html_tool.py` is the single v6 compatibility boundary:

- Adapt htmlrender API changes there before editing many callers.
- Preserve the local `md_to_pic`, `template2html`, `template2image`, and
  `template2image_element` contracts where possible.
- Return `bytes` for rendered images and `str` for rendered HTML.
- Do not reintroduce removed pre-0.8 APIs such as `template_to_pic`,
  `template_to_html`, htmlrender `init`, or `browser.get_new_page`.
- Do not spread direct `render_markdown`/`render_template` calls through business
  plugins unless the compatibility layer cannot represent the required behavior.
- Playwright browser binaries are deployment artifacts and must not be committed.

## Adapter policy

OneBot V11 and V12 are the primary deployment and acceptance targets. Do not
change their registration behavior as part of unrelated work.

Satori is optional, disabled by default, and is not an LTS runtime dependency.
Never add a module-level hard import of `nonebot.adapters.satori`. Import and
register it only after configuration explicitly enables Satori; a missing
optional package must produce a clear error without preventing a OneBot-only
startup. Alconna/Uniseg support for Satori is not a reason to make it mandatory.

## Pacman and third-party plugins

`src/nonebot_plugins/liteyuki_pacman/` is a compatibility and trust boundary:

- Resolve a plugin through the NoneBot Registry before invoking pip.
- Invoke pip through the current interpreter and always apply
  `constraints-lts.txt` to installs/upgrades.
- Respect `PROTECTED_DISTRIBUTIONS` and built-in plugin protection for install,
  update, and uninstall paths.
- If a new package becomes part of the LTS core, review both constraints and the
  protection set.
- Do not hot-load a freshly installed distribution into a process whose imports
  may already be resident; persist installation state and require a restart.
- Treat "distribution installed in Python" and "plugin registered/loaded by
  NoneBot" as different states. Test both when relevant.

## Configuration and secrets

`config.example.yml` is the public, maintained template. Add ordinary user-facing
settings there with short Chinese comments and safe defaults. Keep existing YAML
style and configuration-key semantics; prefer backward-compatible reads when a
key must evolve.

Never commit real API keys, tokens, passwords, QQ identifiers, private hosts, or
deployment details. `config.yml`, `.env`, and `config/` are deployment-local and
may be absent from a checkout. Do not introduce env-only configuration without a
specific compatibility or secret-handling need. Dynamic user/group/plugin state
belongs in the existing database mechanisms rather than static YAML.

## Change discipline

- Make the smallest change that solves the stated problem.
- Do not reformat the repository, reorder unrelated imports, rename unrelated
  files, or clean up adjacent legacy code opportunistically.
- Do not remove existing Liteyuki features unless the task explicitly requires
  it and references have been audited.
- Prefer an existing compatibility layer over editing every consumer.
- Preserve existing Chinese logs and user-facing interaction style. English
  comments are acceptable when concise and useful; do not narrate obvious code.
- Preserve plugin metadata, Liteyuki v6 APIs, NoneBot loading conventions,
  resource paths, and database formats unless migration is explicitly in scope.
- Do not edit packages in `site-packages` or vendor/fork third-party plugins to
  conceal a compatibility problem.

## Minimum verification

Use the repository's existing environment when available; do not create or
repair deployment environments unless requested. Run the smallest relevant test
set first, then broader checks proportional to risk:

```text
python -m compileall -q liteyuki src
python -m pip check
python -m pytest -q <relevant tests>
python -m pytest -q
python main.py
```

For a startup smoke test, confirm NoneBot initialization completes, the
htmlrender Playwright provider starts, OneBot V11/V12 register, and key built-in
plugins have no import traceback. A real adapter connection can only be claimed
when a client actually connects.

Additional acceptance depends on the change:

- Rendering: exercise Markdown, full-template, and selector/element screenshots;
  do not require browser downloads during ordinary unit tests.
- Startup/plugin loading: test built-ins and a dynamic plugin using `require()`.
- Pacman: mock network/PyPI calls and prove constraints/protected packages cannot
  be bypassed.
- Dependency changes: include a dependency diff and run `pip check` plus a real
  startup smoke test.
- Configuration: test template/default loading without relying on a local
  `config.yml`.

Report skipped or environment-dependent checks and distinguish new failures from
known unrelated failures; never claim a live network/adapter test that was not
performed.
