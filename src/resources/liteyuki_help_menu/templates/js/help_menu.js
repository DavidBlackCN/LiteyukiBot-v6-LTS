window.helpMenuReady = false;
const data = JSON.parse(document.getElementById("data").textContent);
const content = document.getElementById("content");
const put = (id, value) => { document.getElementById(id).textContent = value; };
put("title", data.title);
put("subtitle", data.subtitle);
put("pagination", `第 ${data.page} / ${data.pages} 页 · ${data.count} 个可展示插件`);
put("hint", data.hint);
function paragraph(parent, value, cls = "") {
    const node = document.createElement("p");
    node.className = cls;
    node.textContent = value;
    parent.appendChild(node);
}
if (data.detail) {
    const detail = data.detail;
    const box = document.createElement("article");
    box.className = "info-box";
    paragraph(box, `${detail.source} · ${detail.type} · 版本 ${detail.version}`, "label");
    paragraph(box, detail.status, "label");
    paragraph(box, detail.module, "label");
    paragraph(box, detail.description || "暂无功能描述");
    for (const command of detail.commands) {
        paragraph(box, command.command, "command");
        paragraph(box, command.description);
    }
    paragraph(box, detail.usage || "本页暂无使用说明", "usage");
    if (detail.homepage) paragraph(box, detail.homepage, "label");
    if (detail.adapters.length) paragraph(box, `适配器：${detail.adapters.join(" / ")}`, "label");
    content.appendChild(box);
} else {
    const grid = document.createElement("section");
    grid.className = "grid";
    const entries = data.categories.length ? data.categories : data.items;
    for (const item of entries) {
        const node = document.getElementById("entry").content.cloneNode(true);
        node.querySelector("h2").textContent = item.name;
        node.querySelector(".label").textContent = item.id ? `${item.source} · ${item.id}` : `帮助 ${item.name}`;
        const desc = node.querySelector(".description");
        desc.textContent = item.id ? (item.description || "暂无描述，输入插件名查看详情") : `${item.count} 个插件`;
        if (!item.id) desc.classList.add("count");
        grid.appendChild(node);
    }
    if (!entries.length) paragraph(grid, "没有匹配的可见插件");
    content.appendChild(grid);
}
document.fonts.ready.then(() => {
    requestAnimationFrame(() => requestAnimationFrame(() => { window.helpMenuReady = true; }));
});
