const data = JSON.parse(document.getElementById("data").innerText);
const svgNamespace = "http://www.w3.org/2000/svg";

function svgElement(name, attributes = {}) {
    const element = document.createElementNS(svgNamespace, name);
    Object.entries(attributes).forEach(([key, value]) => {
        element.setAttribute(key, value);
    });
    return element;
}

function timestampToTime(timestamp) {
    const date = new Date(Number(timestamp) * 1000);
    if (Number.isNaN(date.getTime())) return "";
    const pad = (value) => `${value}`.padStart(2, "0");
    return `${pad(date.getMonth() + 1)}/${pad(date.getDate())} ` +
        `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function appendText(svg, value, x, y, anchor = "start") {
    const text = svgElement("text", {
        x,
        y,
        class: "chart-axis-label",
        "text-anchor": anchor,
    });
    text.textContent = value;
    svg.appendChild(text);
}

function drawLineChart(container, times, rawCounts) {
    const counts = rawCounts.map((value) => Number(value) || 0);
    if (!counts.length) {
        const empty = document.createElement("div");
        empty.className = "chart-empty";
        empty.innerText = "—";
        container.appendChild(empty);
        return;
    }

    const width = 920;
    const height = 330;
    const plot = {left: 62, right: 22, top: 18, bottom: 52};
    const plotWidth = width - plot.left - plot.right;
    const plotHeight = height - plot.top - plot.bottom;
    const maximum = Math.max(1, ...counts);
    const svg = svgElement("svg", {
        class: "line-chart",
        viewBox: `0 0 ${width} ${height}`,
        role: "img",
        "aria-label": "Message statistics line chart",
    });

    const definitions = svgElement("defs");
    const gradient = svgElement("linearGradient", {
        id: "chart-area-gradient",
        x1: "0",
        y1: "0",
        x2: "0",
        y2: "1",
    });
    gradient.appendChild(svgElement("stop", {
        offset: "0%", "stop-color": "#2679c9", "stop-opacity": "0.25",
    }));
    gradient.appendChild(svgElement("stop", {
        offset: "100%", "stop-color": "#2679c9", "stop-opacity": "0.02",
    }));
    definitions.appendChild(gradient);
    svg.appendChild(definitions);

    for (let index = 0; index <= 4; index += 1) {
        const y = plot.top + plotHeight * index / 4;
        svg.appendChild(svgElement("line", {
            x1: plot.left,
            y1: y,
            x2: width - plot.right,
            y2: y,
            class: "chart-grid-line",
        }));
        appendText(svg, Math.round(maximum * (4 - index) / 4), plot.left - 12, y + 6, "end");
    }

    const points = counts.map((count, index) => {
        const x = plot.left + (counts.length === 1 ? plotWidth / 2 : plotWidth * index / (counts.length - 1));
        const y = plot.top + plotHeight * (1 - count / maximum);
        return {x, y};
    });
    const pointString = points.map(({x, y}) => `${x},${y}`).join(" ");
    const areaPoints = `${plot.left},${plot.top + plotHeight} ${pointString} ` +
        `${width - plot.right},${plot.top + plotHeight}`;
    svg.appendChild(svgElement("polygon", {points: areaPoints, class: "chart-area"}));
    svg.appendChild(svgElement("polyline", {points: pointString, class: "chart-line"}));

    if (points.length <= 32) {
        points.forEach(({x, y}) => {
            svg.appendChild(svgElement("circle", {cx: x, cy: y, r: 5, class: "chart-point"}));
        });
    }

    const labelIndexes = [...new Set([0, Math.floor((times.length - 1) / 2), times.length - 1])];
    labelIndexes.forEach((index) => {
        if (index < 0 || index >= times.length) return;
        const point = points[Math.min(index, points.length - 1)];
        const anchor = index === 0 ? "start" : index === times.length - 1 ? "end" : "middle";
        appendText(svg, timestampToTime(times[index]), point.x, height - 18, anchor);
    });
    container.appendChild(svg);
}

const chartTemplate = document.getElementById("sign-chart-template").content;
const charts = document.getElementById("charts");
data.forEach((item) => {
    const fragment = document.importNode(chartTemplate, true);
    fragment.querySelector(".chart-title").innerText = item["name"] || "";
    const total = (item["counts"] || []).reduce(
        (sum, value) => sum + (Number(value) || 0),
        0
    );
    fragment.querySelector(".chart-total").innerText = `Σ ${total}`;
    drawLineChart(
        fragment.querySelector(".chart-stage"),
        item["times"] || [],
        item["counts"] || []
    );
    charts.appendChild(fragment);
});
