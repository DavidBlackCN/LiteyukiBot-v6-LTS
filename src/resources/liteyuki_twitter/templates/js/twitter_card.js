(() => {
    const data = JSON.parse(document.getElementById("data").textContent);
    const set = (id, value) => { const node = document.getElementById(id); node.textContent = value || ""; node.hidden = !value; };
    set("kind", data.kind); set("author", data.author); set("account", data.account); set("time", data.time);
    set("body", data.body); set("source", data.url);
    function translation(prefix, part) {
        const box = document.getElementById(`${prefix}translation-box`);
        box.hidden = !part.translation && !part.translation_note;
        set(`${prefix}translation`, part.translation); set(`${prefix}translation-note`, part.translation_note);
    }
    const loading = [];
    function avatar(id, source) {
        const img = document.getElementById(id);
        if (source && source.startsWith("data:image/")) {
            img.hidden = false;
            img.src = source;
            loading.push(img.decode().catch(() => { img.hidden = true; }));
        }
    }
    avatar("avatar", data.avatar);
    function media(id, items) {
        const parent = document.getElementById(id);
        const columns = items.length === 1 ? 1 : items.length === 2 || items.length === 4 ? 2 : 3;
        let pending = [];
        function row() {
            if (!pending.length) return;
            const grid = document.createElement("div"); grid.className = "media-row";
            grid.style.setProperty("--columns", String(pending.length));
            parent.appendChild(grid);
            for (const item of pending) {
                const figure = document.getElementById("image-template").content.firstElementChild.cloneNode(true);
                const img = figure.querySelector("img"), caption = figure.querySelector("figcaption");
                if (item.portrait) figure.classList.add("portrait");
                caption.textContent = item.kind === "video" ? "视频封面 · 原链接观看" : item.kind === "gif" ? "GIF 预览 · 原链接查看" : "";
                caption.hidden = !caption.textContent;
                const failed = () => { figure.classList.add("failed"); caption.hidden = false; caption.textContent = "媒体加载失败 · 请查看原链接"; };
                grid.appendChild(figure);
                if (item.src && item.src.startsWith("data:image/")) {
                    img.src = item.src;
                    loading.push(img.decode().catch(failed));
                } else failed();
            }
            pending = [];
        }
        for (const item of items) {
            if (item.portrait) { row(); pending = [item]; row(); }
            else { pending.push(item); if (pending.length === columns) row(); }
        }
        row();
    }
    translation("", data); media("media", data.media || []);
    if (data.quote) {
        document.getElementById("quote").hidden = false;
        avatar("quote-avatar", data.quote.avatar);
        set("quote-author", `${data.quote.author} · ${data.quote.account}`);
        set("quote-body", data.quote.body); translation("quote-", data.quote); media("quote-media", data.quote.media || []);
    }
    loading.push(document.fonts.ready);
    Promise.allSettled(loading).then(() => { window.twitterCardReady = true; });
})();
