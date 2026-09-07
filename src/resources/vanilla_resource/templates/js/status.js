const data = JSON.parse(document.getElementById("data").innerText);
const botData = data["bot"];
const hardwareData = data["hardware"];
const liteyukiData = data["liteyuki"];
const localData = data["localization"];
const motto = data["motto"];
const acknowledgement = data["acknowledgement"];
const units = localData["units"];
const binaryUnits = units["Bin_Units"];

function clampPercent(value) {
    const number = Number(value);
    return Number.isFinite(number) ? Math.min(100, Math.max(0, number)) : 0;
}

function convertSize(
    size,
    precision = 2,
    addUnit = true,
    suffix = ` X${units["Byte"]}`
) {
    let value = Math.abs(Number(size) || 0);
    const isNegative = Number(size) < 0;
    let unit = binaryUnits[binaryUnits.length - 1] || "";

    for (let index = 0; index < binaryUnits.length; index += 1) {
        unit = binaryUnits[index];
        if (value < 1024 || index === binaryUnits.length - 1) {
            break;
        }
        value /= 1024;
    }

    if (isNegative) {
        value = -value;
    }
    return addUnit
        ? value.toFixed(precision) + suffix.replace("X", unit)
        : value;
}

function secondsToTextTime(seconds) {
    const value = Math.max(0, Number(seconds) || 0);
    const days = Math.floor(value / 86400);
    const hours = Math.floor((value % 86400) / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    const remainingSeconds = Math.floor(value % 60);
    return `${days}${localData["days"]} ${hours}${localData["hours"]} ` +
        `${minutes}${localData["minutes"]} ${remainingSeconds}${localData["seconds"]}`;
}

function appendTags(container, tags) {
    tags.filter((tag) => tag !== null && tag !== undefined && `${tag}`.trim())
        .forEach((tag) => {
            const tagElement = document.createElement("span");
            tagElement.className = "bot-tag";
            tagElement.innerText = tag;
            container.appendChild(tagElement);
        });
}

function createBotCard(name, icon, tags) {
    const fragment = document.importNode(
        document.getElementById("bot-template").content,
        true
    );
    const image = fragment.querySelector(".bot-icon-img");
    image.src = icon || "./img/liteyuki.png";
    image.onerror = () => {
        image.onerror = null;
        image.src = "./img/liteyuki.png";
    };
    fragment.querySelector(".bot-name").innerText = name;
    appendTags(fragment.querySelector(".bot-tags"), tags);
    return fragment;
}

function createUsageChart(element, label, percent) {
    const normalizedPercent = clampPercent(percent);
    element.style.setProperty("--usage", normalizedPercent);
    element.querySelector(".device-chart-value").innerText =
        `${normalizedPercent.toFixed(1)}%`;
    element.querySelector(".device-chart-label").innerText = label;
}

function createDeviceCard(id, label, percent, tags) {
    const fragment = document.importNode(
        document.getElementById("device-info").content,
        true
    );
    const card = fragment.querySelector(".device-info");
    const chart = fragment.querySelector(".device-chart");
    card.id = `${id}-info`;
    chart.id = `${id}-chart`;
    createUsageChart(chart, label, percent);

    const tagContainer = fragment.querySelector(".device-tags");
    tags.forEach((tag) => {
        const tagElement = document.createElement("div");
        tagElement.className = "device-tag";
        tagElement.innerText = tag;
        tagContainer.appendChild(tagElement);
    });
    return fragment;
}

function createDiskBar(title, percent, name) {
    const disk = document.createElement("div");
    disk.className = "disk-info";
    disk.innerHTML = `
        <div class="disk-name"></div>
        <div class="disk-details"></div>
        <div class="disk-usage"></div>
    `;
    disk.querySelector(".disk-name").innerText = name;
    disk.querySelector(".disk-details").innerText = title;
    disk.querySelector(".disk-usage").style.width = `${clampPercent(percent)}%`;
    return disk;
}

function main() {
    const hardwareSection = document.getElementById("hardware-info");

    botData["bots"].forEach((bot) => {
        const card = createBotCard(bot["name"], bot["icon"], [
            bot["protocol_name"],
            bot["app_name"],
            `${localData["groups"]}${bot["groups"]}`,
            `${localData["friends"]}${bot["friends"]}`,
            `${localData["message_sent"]}${bot["message_sent"]}`,
            `${localData["message_received"]}${bot["message_received"]}`,
        ]);
        document.body.insertBefore(card, hardwareSection);
    });

    const liteyukiCard = createBotCard(
        liteyukiData["name"] || "LiteyukiBot v6 LTS",
        "./img/liteyuki.png",
        [
            `LiteyukiBot v6 LTS · ${liteyukiData["version"]}`,
            `NoneBot ${liteyukiData["nonebot"]}`,
            liteyukiData["python"],
            liteyukiData["system"],
            `${localData["plugins"]}${liteyukiData["plugins"]}`,
            `${localData["resources"]}${liteyukiData["resources"]}`,
            `${localData["bots"]}${liteyukiData["bots"]}`,
            `${localData["runtime"]} ${secondsToTextTime(liteyukiData["runtime"])}`,
        ]
    );
    document.body.insertBefore(liteyukiCard, hardwareSection);

    const cpu = hardwareData["cpu"];
    const memory = hardwareData["memory"];
    const swap = hardwareData["swap"];

    hardwareSection.appendChild(createDeviceCard(
        "cpu",
        localData["cpu"],
        cpu["percent"],
        [
            cpu["name"],
            `${cpu["cores"]}${localData["cores"]} ${cpu["threads"]}${localData["threads"]}`,
            `${(cpu["freq"] / 1000).toFixed(2)}${units["GHz"]}`,
        ]
    ));
    hardwareSection.appendChild(createDeviceCard(
        "mem",
        localData["memory"],
        memory["percent"],
        [
            `${localData["process"]} ${convertSize(memory["usedProcess"])}`,
            `${localData["used"]} ${convertSize(memory["used"])}`,
            `${localData["free"]} ${convertSize(memory["free"])}`,
            `${localData["total"]} ${convertSize(memory["total"])}`,
        ]
    ));
    hardwareSection.appendChild(createDeviceCard(
        "swap",
        localData["swap"],
        swap["percent"],
        [
            `${localData["used"]} ${convertSize(swap["used"])}`,
            `${localData["free"]} ${convertSize(swap["free"])}`,
            `${localData["total"]} ${convertSize(swap["total"])}`,
        ]
    ));

    const diskSection = document.getElementById("disk-info");
    hardwareData["disk"].forEach((disk) => {
        const title = `${localData["free"]} ${convertSize(disk["free"])} ` +
            `${localData["total"]} ${convertSize(disk["total"])}`;
        diskSection.appendChild(createDiskBar(title, disk["percent"], disk["name"]));
    });
    if (hardwareData["disk"].length === 0) {
        diskSection.style.display = "none";
    }

    document.getElementById("motto-text").innerText = motto["text"] || "";
    document.getElementById("motto-from").innerText = motto["source"] || "";
    document.getElementById("addition-info").innerText = acknowledgement || "";
}

main();
