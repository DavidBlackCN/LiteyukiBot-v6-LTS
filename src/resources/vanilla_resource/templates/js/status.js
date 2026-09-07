const data = JSON.parse(document.getElementById("data").innerText);
const botData = data["bot"] || { bots: [] };
const hardwareData = data["hardware"] || { cpu: {}, memory: {}, swap: {}, disk: [] };
const liteyukiData = data["liteyuki"] || {};
const localData = data["localization"] || {};
const motto = data["motto"] || {};
const background = data["background"] || {};
const acknowledgement = data["acknowledgement"] || "";
const units = localData["units"] || { GHz: "GHz", Byte: "B", Bin_Units: [""] };
const binaryUnits = units["Bin_Units"] || [""];

function clampPercent(value) {
    const number = Number(value);
    return Number.isFinite(number) ? Math.min(100, Math.max(0, number)) : 0;
}

function numeric(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
}

function convertSize(size, precision = 2, addUnit = true, suffix = ` X${units["Byte"]}`) {
    let value = Math.abs(numeric(size));
    const isNegative = numeric(size) < 0;
    let unit = binaryUnits[binaryUnits.length - 1] || "";
    for (let index = 0; index < binaryUnits.length; index += 1) {
        unit = binaryUnits[index];
        if (value < 1024 || index === binaryUnits.length - 1) break;
        value /= 1024;
    }
    if (isNegative) value = -value;
    return addUnit ? value.toFixed(precision) + suffix.replace("X", unit) : value;
}

function secondsToTextTime(seconds) {
    const value = Math.max(0, numeric(seconds));
    const days = Math.floor(value / 86400);
    const hours = Math.floor((value % 86400) / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    const remainingSeconds = Math.floor(value % 60);
    return `${days}${localData["days"] || "d"} ${hours}${localData["hours"] || "h"} ${minutes}${localData["minutes"] || "m"} ${remainingSeconds}${localData["seconds"] || "s"}`;
}

function secondsToCompactTime(seconds) {
    const value = Math.max(0, numeric(seconds));
    const days = Math.floor(value / 86400);
    const hours = Math.floor((value % 86400) / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    return `${days}${localData["days"] || "d"} ${hours}${localData["hours"] || "h"} ${minutes}${localData["minutes"] || "m"}`;
}

function appendTags(container, tags) {
    tags.filter((tag) => tag !== null && tag !== undefined && `${tag}`.trim()).forEach((tag) => {
        const element = document.createElement("span");
        element.className = "bot-tag";
        element.innerText = tag;
        container.appendChild(element);
    });
}

function appendStats(container, stats) {
    stats.forEach(([label, value]) => {
        const element = document.createElement("div");
        element.className = "bot-stat";
        element.innerHTML = '<div class="bot-stat-value"></div><div class="bot-stat-label"></div>';
        element.querySelector(".bot-stat-value").innerText = value;
        element.querySelector(".bot-stat-label").innerText = label;
        container.appendChild(element);
    });
}

function createBotCard(bot) {
    const fragment = document.importNode(document.getElementById("bot-template").content, true);
    const image = fragment.querySelector(".bot-icon-img");
    image.src = bot["icon"] || "./img/liteyuki.png";
    image.onerror = () => { image.onerror = null; image.src = "./img/liteyuki.png"; };
    fragment.querySelector(".bot-name").innerText = bot["name"] || `${bot["id"]}`;
    fragment.querySelector(".bot-identity").innerText = `QQ ${bot["id"]}`;
    appendTags(fragment.querySelector(".bot-tags"), [bot["app_name"], bot["protocol_name"]]);
    appendStats(fragment.querySelector(".bot-stat-grid"), [
        [localData["groups"] || "群", numeric(bot["groups"])],
        [localData["friends"] || "好友", numeric(bot["friends"])],
        [localData["message_sent"] || "发送", numeric(bot["message_sent"])],
        [localData["message_received"] || "接收", numeric(bot["message_received"])],
    ]);
    return fragment;
}

function createSummary(label, value) {
    const card = document.createElement("article");
    card.className = "summary-card";
    card.innerHTML = '<div class="summary-value"></div><div class="summary-label"></div>';
    card.querySelector(".summary-value").innerText = value;
    card.querySelector(".summary-label").innerText = label;
    return card;
}

function createDeviceCard(id, label, percent, tags) {
    const fragment = document.importNode(document.getElementById("device-info").content, true);
    const card = fragment.querySelector(".device-info");
    const chart = fragment.querySelector(".device-chart");
    const normalizedPercent = clampPercent(percent);
    card.id = `${id}-info`;
    chart.id = `${id}-chart`;
    chart.style.setProperty("--usage", normalizedPercent);
    chart.querySelector(".device-chart-value").innerText = `${normalizedPercent.toFixed(1)}%`;
    chart.querySelector(".device-chart-label").innerText = label;
    const tagContainer = fragment.querySelector(".device-tags");
    tags.forEach((tag) => {
        const element = document.createElement("div");
        element.className = "device-tag";
        element.innerText = tag;
        tagContainer.appendChild(element);
    });
    return fragment;
}

function createDiskBar(title, percent, name) {
    const disk = document.createElement("div");
    disk.className = "disk-info";
    disk.innerHTML = '<div class="disk-name"></div><div class="disk-details"></div><div class="disk-usage"></div>';
    disk.querySelector(".disk-name").innerText = name;
    disk.querySelector(".disk-details").innerText = title;
    disk.querySelector(".disk-usage").style.width = `${clampPercent(percent)}%`;
    return disk;
}

function applyBackground() {
    document.body.style.setProperty("--status-mask-opacity", clampPercent(numeric(background["mask"]) * 100) / 100);
    if (background["image"]) {
        document.body.style.setProperty("--status-background-image", `url("${background["image"]}")`);
        document.body.classList.add("has-remote-background");
    }
}

function main() {
    applyBackground();
    const bots = botData["bots"] || [];
    const total = (key) => bots.reduce((sum, bot) => sum + numeric(bot[key]), 0);
    document.getElementById("status-title").innerText = liteyukiData["name"] || "LiteyukiBot v6 LTS";
    document.getElementById("status-subtitle").innerText = localData["description"] || "LiteyukiBot v6 LTS Status Dashboard";
    appendTags(document.getElementById("hero-meta"), [
        `Liteyuki ${liteyukiData["version"] || "v6 LTS"}`,
        `NoneBot ${liteyukiData["nonebot"] || "-"}`,
        liteyukiData["python"],
        liteyukiData["system"],
    ]);

    const summary = document.getElementById("summary-info");
    [
        [localData["bots"] || "Bot", numeric(liteyukiData["bots"])],
        [localData["plugins"] || "插件", numeric(liteyukiData["plugins"])],
        [localData["resources"] || "资源包", numeric(liteyukiData["resources"])],
        [localData["runtime"] || "运行时间", secondsToCompactTime(liteyukiData["runtime"])],
        [localData["groups"] || "群", total("groups")],
        [localData["friends"] || "好友", total("friends")],
        [localData["message_sent"] || "发送消息", total("message_sent")],
        [localData["message_received"] || "接收消息", total("message_received")],
    ].forEach(([label, value]) => summary.appendChild(createSummary(label, value)));

    const botsSection = document.getElementById("bots-info");
    bots.forEach((bot) => botsSection.appendChild(createBotCard(bot)));
    document.getElementById("bot-count").innerText = `${bots.length} ONLINE`;
    if (!bots.length) document.getElementById("bot-section").style.display = "none";

    const cpu = hardwareData["cpu"] || {};
    const memory = hardwareData["memory"] || {};
    const swap = hardwareData["swap"] || {};
    const hardwareSection = document.getElementById("hardware-info");
    hardwareSection.appendChild(createDeviceCard("cpu", localData["cpu"] || "CPU", cpu["percent"], [
        cpu["name"] || "-",
        `${numeric(cpu["cores"])}${localData["cores"] || " cores"} ${numeric(cpu["threads"])}${localData["threads"] || " threads"}`,
        `${(numeric(cpu["freq"]) / 1000).toFixed(2)}${units["GHz"] || "GHz"}`,
    ]));
    hardwareSection.appendChild(createDeviceCard("mem", localData["memory"] || "Memory", memory["percent"], [
        `${localData["process"] || "Process"} ${convertSize(memory["usedProcess"])}`,
        `${localData["used"] || "Used"} ${convertSize(memory["used"])}`,
        `${localData["total"] || "Total"} ${convertSize(memory["total"])}`,
    ]));
    hardwareSection.appendChild(createDeviceCard("swap", localData["swap"] || "Swap", swap["percent"], [
        `${localData["used"] || "Used"} ${convertSize(swap["used"])}`,
        `${localData["free"] || "Free"} ${convertSize(swap["free"])}`,
        `${localData["total"] || "Total"} ${convertSize(swap["total"])}`,
    ]));

    document.getElementById("disk-title").innerText = localData["disk"] || "磁盘";
    const disks = hardwareData["disk"] || [];
    const diskSection = document.getElementById("disk-info");
    disks.forEach((disk) => {
        const title = `${localData["free"] || "Free"} ${convertSize(disk["free"])} · ${localData["total"] || "Total"} ${convertSize(disk["total"])}`;
        diskSection.appendChild(createDiskBar(title, disk["percent"], disk["name"]));
    });
    if (!disks.length) document.getElementById("disk-section").style.display = "none";

    document.getElementById("motto-text").innerText = motto["text"] || "";
    document.getElementById("motto-from").innerText = motto["source"] ? `— ${motto["source"]}` : "";
    if (!motto["text"]) document.getElementById("motto-info").style.display = "none";
    document.getElementById("addition-info").innerText = acknowledgement;
}

main();
