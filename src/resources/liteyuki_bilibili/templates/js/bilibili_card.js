const data = JSON.parse(document.getElementById("data").textContent);
for (const key of ["label", "author", "timestamp", "title", "body", "url", "state"]) {
  const element = document.getElementById(key);
  if (element) element.textContent = data[key] || "";
}
const avatar = document.getElementById("avatar");
if (data.avatar) avatar.src = data.avatar; else avatar.style.display = "none";
const covers = document.getElementById("covers");
const coverTemplate = document.getElementById("cover-template");
for (const source of data.covers || []) { const item = coverTemplate.content.cloneNode(true); item.querySelector("img").src = source; covers.append(item); }
const metrics = document.getElementById("metrics");
const metricTemplate = document.getElementById("metric-template");
for (const metric of data.metrics || []) { const item = metricTemplate.content.cloneNode(true); const nodes = item.querySelectorAll("span, strong"); nodes[0].textContent = metric.label; nodes[1].textContent = metric.value; metrics.append(item); }
Promise.all([...document.images].map(image => image.decode().catch(() => undefined))).then(() => document.fonts.ready).then(() => { window.bilibiliCardReady = true; });
