const data = JSON.parse(document.getElementById("data").innerText);
const rowTemplate = document.getElementById("row-template").content;
const rankList = document.getElementById("rank-list");

function hidePrivateIdentifier(value) {
    const text = `${value ?? ""}`;
    if (text.length <= 6) return text;
    const start = Math.floor(text.length / 2) - 2;
    return text.slice(0, start) + "(¬‿¬)" + text.slice(start + 5);
}

document.getElementById("rank-title").innerText = data["name"] || "";

const ranking = data["ranking"] || [];
ranking.forEach((item, index) => {
    const fragment = document.importNode(rowTemplate, true);
    const row = fragment.querySelector(".rank-row");
    const image = fragment.querySelector(".row-icon");
    const rank = index + 1;

    row.dataset.rank = rank;
    fragment.querySelector(".row-position").innerText = `#${rank}`;
    fragment.querySelector(".row-name").innerText = hidePrivateIdentifier(item["name"]);
    fragment.querySelector(".row-count").innerText = item["count"] ?? 0;
    image.src = item["icon"] || "./img/liteyuki.png";
    image.onerror = () => {
        image.onerror = null;
        image.src = "./img/liteyuki.png";
    };
    rankList.appendChild(fragment);
});

if (!ranking.length) {
    const empty = document.createElement("div");
    empty.className = "rank-empty";
    empty.innerText = "—";
    rankList.appendChild(empty);
}
