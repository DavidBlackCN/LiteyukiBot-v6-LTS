const data = JSON.parse(document.getElementById("data").textContent);
function text(id, value) {
  const element = document.getElementById(id);
  element.textContent = value || "";
  element.hidden = !value;
}
for (const key of ["label", "author", "timestamp", "title", "body", "url", "state"]) text(key, data[key]);
text("live-url", data.live_url ? `直播间：${data.live_url}` : "");
const avatar = document.getElementById("avatar");
if (data.avatar) avatar.src = data.avatar; else avatar.hidden = true;
const coverTemplate = document.getElementById("cover-template");
async function gallery(id, sources, mediaType) {
  const section = document.getElementById(id);
  const images = sources.map(source => {
    // Template fragments belong to an inert document; import before decoding.
    const item = document.importNode(coverTemplate.content, true).querySelector("img");
    item.src = source;
    return item;
  });
  const decoded = await Promise.all(images.map(async image => {
    try { await image.decode(); return image; } catch { return null; }
  }));
  const valid = decoded.filter(Boolean);
  const columns = valid.length === 4 ? 2 : valid.length >= 3 ? 3 : valid.length;
  let row = [];
  function flush() {
    if (!row.length) return;
    const container = document.createElement("div");
    container.className = "cover-row";
    container.append(...row);
    section.append(container);
    row = [];
  }
  for (const image of valid) {
    if (mediaType === "live" || mediaType === "video" || image.naturalHeight > image.naturalWidth * 1.6) {
      flush(); section.append(image);
    } else {
      row.push(image);
      if (row.length === columns) flush();
    }
  }
  flush();
}
const tasks = [gallery("covers", data.covers || [], data.display_type)];
if (data.original) {
  const original = data.original;
  document.getElementById("original").hidden = false;
  text("original-author", original.author_name);
  text("original-title", original.unavailable ? "原动态已失效或不可见" : original.title);
  text("original-body", original.unavailable ? "" : original.body);
  text("original-url", original.url);
  text("original-live-url", original.live ? `${original.live.state} · ${original.live.area_name || ""} ${original.live.url}` : "");
  tasks.push(gallery("original-covers", original.unavailable ? [] : original.covers || [], original.live ? "live" : "dynamic"));
}
const metrics = document.getElementById("metrics");
const metricTemplate = document.getElementById("metric-template");
for (const metric of data.metrics || []) {
  const item = metricTemplate.content.cloneNode(true);
  item.querySelector("span").textContent = metric.label;
  item.querySelector("strong").textContent = metric.value;
  metrics.append(item);
}
metrics.hidden = !metrics.children.length;
tasks.push(data.avatar ? avatar.decode().catch(() => { avatar.hidden = true; }) : Promise.resolve());
Promise.all(tasks).then(() => document.fonts.ready).then(() => { window.bilibiliCardReady = true; });
