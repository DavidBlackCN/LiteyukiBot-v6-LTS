"""Normalize runtime metadata without importing plugin modules or altering them."""
import re
from difflib import SequenceMatcher

CATEGORIES = {
    "system": "系统插件", "basic": "基础插件",
    "builtin": "内置插件", "third_party": "第三方插件",
}
ALIASES = {**{v: k for k, v in CATEGORIES.items()}, "系统": "system",
           "基础": "basic", "内置": "builtin", "第三方": "third_party"}
SYSTEM_MODULES = {
    "nonebot_plugin_htmlrender", "nonebot_plugin_apscheduler",
    "nonebot_plugin_localstore", "nonebot_plugin_alconna",
}


def category_of(module_name, extra, kind=""):
    explicit = extra.get("help_category")
    if isinstance(explicit, str) and explicit in CATEGORIES:
        return explicit
    if extra.get("lts_builtin") is True:
        return "builtin"
    if kind in ("library", "internal") or extra.get("internal") is True or extra.get("category") in ("system", "library", "internal"):
        return "system"
    if any(module_name == name or module_name.startswith(name + ".") for name in SYSTEM_MODULES):
        return "system"
    if module_name.startswith(("src.nonebot_plugins.", "src.liteyuki_plugins.", "liteyuki.plugins.")) or extra.get("liteyuki") is True:
        return "basic"
    return "third_party"


def source_of(module_name, extra):
    if module_name.startswith("src.nonebot_plugins."):
        return "LTS 内置"
    if extra.get("liteyuki") or module_name.startswith(("liteyuki.plugins.", "src.liteyuki_plugins.")):
        return "Liteyuki 原生"
    return "第三方 NoneBot"


def text(value, maximum=12000):
    return str(value or "")[:maximum]


def collect_plugins(plugins, config):
    result = []
    hidden = set(config.help_menu_hidden_plugins)
    for plugin in plugins:
        name = text(plugin.name, 200)
        module = text(getattr(plugin, "module_name", name), 500)
        meta = getattr(plugin, "metadata", None)
        extra = getattr(meta, "extra", {}) or {}
        if not isinstance(extra, dict):
            extra = {}
        kind = text(getattr(meta, "type", "")) or "未声明"
        if name in hidden or module in hidden or extra.get("hidden") or kind == "library":
            continue
        source = source_of(module, extra)
        if source == "第三方 NoneBot" and not config.help_menu_show_third_party:
            continue
        category = category_of(module, extra, kind)
        commands = extra.get("help_commands", [])
        if not isinstance(commands, list):
            commands = []
        commands = [{"command": text(c.get("command"), 500),
                     "description": text(c.get("description"), 1000)}
                    for c in commands[:100] if isinstance(c, dict) and c.get("command")]
        result.append({
            "id": name, "module": module,
            "name": text(getattr(meta, "name", name), 200) or name,
            "description": text(getattr(meta, "description", "")),
            "usage": text(getattr(meta, "usage", "")).removeprefix("MARKDOWN"),
            "type": kind, "source": source, "category": category,
            "category_label": CATEGORIES[category], "commands": commands,
            "homepage": text(getattr(meta, "homepage", ""), 1000),
            "adapters": sorted(str(a) for a in (getattr(meta, "supported_adapters", None) or [])),
            "version": text(extra.get("version"), 100) or "未声明",
            "status": "已加载（使用权限由插件判定）",
            "toggleable": extra.get("toggleable"), "default_enable": extra.get("default_enable"),
        })
    return sorted(result, key=lambda item: (item["name"].casefold(), item["id"]))


def search_plugins(items, query, pinyin=True):
    query = query.strip().casefold()
    if not query:
        return []
    ranked = []
    for item in items:
        name = item["name"].casefold()
        fields = [name, item["id"].casefold(), item["module"].casefold(),
                  item["description"].casefold(), item["usage"].casefold()]
        score = 100 if query in (name, item["id"].casefold()) else 0
        score = max(score, 80 if any(query in s for s in fields[:3]) else 0,
                    50 if any(query in s for s in fields[3:]) else 0)
        if pinyin:
            try:
                from pypinyin import lazy_pinyin
                syllables = lazy_pinyin(name)
                if query in "".join(syllables) or query in "".join(s[0] for s in syllables if s):
                    score = max(score, 60)
            except ImportError:
                pass
        similarity = SequenceMatcher(None, query, name).ratio()
        if similarity >= 0.6:
            score = max(score, int(similarity * 45))
        if score:
            ranked.append((score, item))
    return [item for _, item in sorted(ranked, key=lambda pair: (-pair[0], pair[1]["id"]))]


def page_context(items, query, page_size=10, pinyin=True):
    query = query.strip()
    page = 1
    match = re.fullmatch(r"(.*?)\s+(\d+)", query)
    if match:
        query, number = match.groups()
        page = int(number)
    base = {"title": "帮助中心", "subtitle": "LiteyukiBot v6 LTS",
            "items": [], "categories": [], "detail": None, "page": page,
            "pages": 1, "count": len(items), "hint": "帮助 <分类或插件名> · 帮助 搜索 <关键词> · 帮助 <分类> <页码>"}
    if not query:
        base["categories"] = [{"name": label, "count": sum(i["category"] == key for i in items)}
                              for key, label in CATEGORIES.items()]
        base["subtitle"] = f"LiteyukiBot v6 LTS · 可展示插件 {len(items)}"
        return base
    exact = next((i for i in items if query.casefold() in
                  (i["id"].casefold(), i["module"].casefold(), i["name"].casefold())), None)
    category = ALIASES.get(query, query.lower())
    if category in CATEGORIES:
        chosen = [i for i in items if i["category"] == category]
        base["title"] = CATEGORIES[category]
    elif query in ("全部", "list"):
        chosen = items
        base["title"] = "插件列表"
    elif exact:
        # Paginate long usage too, retaining every normalized character.
        parts = [exact["usage"][n:n + 1800] for n in range(0, len(exact["usage"]), 1800)] or [""]
        command_pages = max(1, (len(exact["commands"]) + 7) // 8)
        base["pages"] = max(len(parts), command_pages)
        if not 1 <= page <= base["pages"]:
            raise ValueError(f"页码应为 1–{base['pages']}")
        base["detail"] = dict(exact, usage=parts[page - 1] if page <= len(parts) else "",
                              commands=exact["commands"][(page - 1) * 8:page * 8])
        base["title"] = exact["name"]
        return base
    else:
        keyword = re.sub(r"^(?:搜索|search)\s+", "", query, flags=re.I)
        chosen = search_plugins(items, keyword, pinyin)
        base["title"] = f"搜索：{keyword[:80]}"
    base["count"] = len(chosen)
    base["pages"] = max(1, (len(chosen) + page_size - 1) // page_size)
    if not 1 <= page <= base["pages"]:
        raise ValueError(f"页码应为 1–{base['pages']}")
    base["items"] = [dict(i, description=i["description"][:180])
                     for i in chosen[(page - 1) * page_size:page * page_size]]
    return base
