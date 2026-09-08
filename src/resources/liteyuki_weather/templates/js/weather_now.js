window.weatherCardReady = false;
let data = JSON.parse(document.getElementById("data").innerText);
let localData = data.localization || {};
let current = data.current || {};
let daily = data.daily || [];
let hourly = data.hourly || [];
let params = data.params || {};
let locationData = data.location || {};
let astronomy = data.astronomy || {};
let aqi = data.aqi || {};

function setText(id, value) {
    let node = document.getElementById(id);
    if (node) node.innerText = value == null ? "" : value;
}

function displayTime(value) {
    if (!value) return "";
    let date = new Date(value);
    if (!Number.isNaN(date.getTime())) return date.toLocaleString();
    return value;
}

let firstDay = daily.length ? daily[0] : {};
setText("time", displayTime(current.observed_at || data.generated_at));
setText("city", locationData.name || "");
setText(
    "adm",
    [locationData.country, locationData.adm1, locationData.adm2]
        .filter(Boolean)
        .join(" ")
);
setText("temperature-now", `${current.temperature || "-"}°`);
setText(
    "temperature-range",
    firstDay.temp_min == null
        ? ""
        : `${firstDay.temp_min}°/${firstDay.temp_max}°`
);
setText("description", current.text || "");
document.querySelector(".main-icon").src = `./img/qw_icon/${current.icon || "999"}.png`;

let aqiDot = document.getElementById("aqi-dot");
if (aqi.available) {
    setText("aqi-data", `AQI ${aqi.value || "-"} ${aqi.category || ""}`);
    let color = aqi.color || {};
    if (color.css) {
        aqiDot.style.backgroundColor = color.css;
    } else if (color.red != null) {
        aqiDot.style.backgroundColor = `rgba(${color.red},${color.green},${color.blue},${color.alpha == null ? 1 : color.alpha})`;
    }
} else {
    aqiDot.style.backgroundColor = "#fff";
    setText("aqi-data", localData.no_aqi || "No AQI data");
}

let subtemplates = {
    "now-windDirect": `${current.wind_compass || "-"} ${current.wind_degree || "-"}°`,
    "now-windVelocity": `${localData["now-windVelocity"] || "Wind"} ${current.wind_scale || "-"} ${current.wind_speed || "-"}${params.wind_unit || ""}`,
    "now-humidity": `${localData["now-humidity"] || "Humidity"} ${current.humidity || "-"}%`,
    "now-feelsLike": `${localData["now-feelsLike"] || "Feels like"} ${current.feels_like || "-"}${params.temperature_unit || ""}`,
    "now-precip": `${localData["now-precip"] || "Precip"} ${current.precipitation || "-"}${params.precipitation_unit || ""}`,
    "now-pressure": `${localData["now-pressure"] || "Pressure"} ${current.pressure || "-"}${params.pressure_unit || ""}`,
    "now-vis": `${localData["now-vis"] || "Visibility"} ${current.visibility || "-"}${params.visibility_unit || ""}`,
    "now-cloud": `${localData["now-cloud"] || "Cloud"} ${current.cloud_cover || "-"}%`,
    "astronomy-sunrise": `${localData["astronomy-sunrise"] || "Sunrise"} ${astronomy.sunrise || "-"}`,
    "astronomy-sunset": `${localData["astronomy-sunset"] || "Sunset"} ${astronomy.sunset || "-"}`,
};

let subiconMap = {
    "now-windDirect": "windDirect",
    "now-windVelocity": "windVelocity",
    "now-humidity": "humidity",
    "now-feelsLike": "feelsLike",
    "now-precip": "precip",
    "now-pressure": "pressure",
    "now-vis": "vis",
    "now-cloud": "cloud",
    "astronomy-sunrise": "sunrise",
    "astronomy-sunset": "sunset",
};

let subtemplate = document.getElementById("sub-info-template").content;
let subcontainer = document.getElementById("sub-info");
Object.keys(subtemplates).forEach((id) => {
    let subItem = document.importNode(subtemplate, true).querySelector(".sub-item");
    subItem.querySelector("div").innerText = subtemplates[id];
    subItem.querySelector("img").src = `./img/svg/${subiconMap[id]}.svg`;
    subcontainer.appendChild(subItem);
});

let hourlyTemplate = document.getElementById("hourly-item-template").content;
let hourlyCount = 0;
hourly.forEach((item, index) => {
    if (index % 2 !== 0 || hourlyCount >= 8) return;
    let fragment = document.importNode(hourlyTemplate, true);
    fragment.querySelector(".hourly-icon").src = `./img/qw_icon/${item.icon || "999"}.png`;
    fragment.querySelector(".hourly-time").innerText = item.time || "";
    fragment.querySelector(".hourly-temperature").innerText = `${item.temperature || "-"}°`;
    document.getElementById("hours-info").appendChild(fragment);
    hourlyCount++;
});

let dayNames = [
    localData.sunday,
    localData.monday,
    localData.tuesday,
    localData.wednesday,
    localData.thursday,
    localData.friday,
    localData.saturday,
];
let dailyTemplate = document.getElementById("daily-item-template").content;
daily.slice(0, 7).forEach((item, index) => {
    let fragment = document.importNode(dailyTemplate, true);
    let date = item.date ? new Date(`${item.date}T00:00:00`) : null;
    let label = index === 0 ? localData.today : index === 1 ? localData.tomorrow : dayNames[date ? date.getDay() : 0];
    if (index >= 2 && item.date) label += `(${item.date.slice(5).replace("-", ".")})`;
    fragment.querySelector(".daily-day").innerText = label || item.date || "";
    fragment.querySelector(".daily-weather").innerText = item.text_day || "";
    fragment.querySelector(".icon-day").src = `./img/qw_icon/${item.icon_day || "999"}.png`;
    fragment.querySelector(".icon-night").src = `./img/qw_icon/${item.icon_night || "999"}.png`;
    fragment.querySelector(".daily-temperature").innerText = `${item.temp_min || "-"}°~${item.temp_max || "-"}°`;
    document.getElementById("days-info").appendChild(fragment);
});

setText("attribution-info", (data.attributions || []).join(" · "));

(async () => {
    try {
        await Promise.all([
            document.fonts.ready,
            window.applyCardBackground(data.background || {}),
        ]);
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    } finally {
        window.weatherCardReady = true;
    }
})();
