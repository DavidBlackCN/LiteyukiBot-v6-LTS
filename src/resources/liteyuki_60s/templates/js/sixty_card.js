window.sixtyCardReady = false;
const data = JSON.parse(document.getElementById("data").textContent);
document.body.classList.add(`sixty-variant-${data.variant || "news"}`);
const setText = (id, value) => { const node = document.getElementById(id); if (node) node.textContent = value || ""; };
setText("title", data.title);
setText("date", data.date);
setText("headline", data.headline);
setText("quote", data.quote);
setText("calendar-lunar", data.calendar && data.calendar.lunar);
setText("calendar-today", data.calendar && data.calendar.today);
const quoteBox = document.getElementById("quote-box");
quoteBox.hidden = !data.quote;
const facts = document.getElementById("facts");
const factTemplate = document.getElementById("fact-template").content;
(data.variant === "moyu" ? data.countdowns || [] : data.facts || []).filter(item => item.value).forEach(item => {
    const node = document.importNode(factTemplate, true);
    node.querySelector(".fact-label").textContent = item.label || "";
    node.querySelector(".fact-value").textContent = item.value || "";
    const unit = node.querySelector(".fact-unit");
    const detail = node.querySelector(".fact-detail");
    if (unit) unit.textContent = item.unit || "";
    if (detail) detail.textContent = item.detail || "";
    facts.appendChild(node);
});
facts.hidden = !facts.children.length;
const progressBox = document.getElementById("progress-box");
const progressTemplate = document.getElementById("progress-template").content;
(data.progress || []).forEach(item => {
    const node = document.importNode(progressTemplate, true);
    node.querySelector(".progress-label").textContent = item.label || "";
    node.querySelector(".progress-value").textContent = item.value || "";
    node.querySelector(".progress-detail").textContent = item.detail || "";
    node.querySelector(".progress-track i").style.width = `${item.percentage || 0}%`;
    progressBox.appendChild(node);
});
progressBox.hidden = !progressBox.children.length;
const items = document.getElementById("items");
const itemTemplate = document.getElementById("item-template").content;
(data.items || []).forEach((item, index) => {
    const node = document.importNode(itemTemplate, true);
    node.querySelector(".item-index").textContent = String(index + 1);
    node.querySelector("h2").textContent = item.title || "";
    node.querySelector(".item-detail").textContent = item.detail || "";
    node.querySelector(".item-meta").textContent = item.meta || "";
    items.appendChild(node);
});
items.hidden = !items.children.length;
(async () => {
    try {
        await Promise.all([document.fonts.ready, data.variant === "moyu" ? Promise.resolve() : window.applyCardBackground(data.background || {})]);
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    } finally { window.sixtyCardReady = true; }
})();