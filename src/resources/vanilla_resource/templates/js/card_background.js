// Opt-in helper. Public templates call and await this before screenshotting.
window.applyCardBackground = async function (background) {
    const image = document.getElementById("card-background-image");
    const mask = Number(background.mask);
    document.body.style.setProperty("--status-mask-opacity", Number.isFinite(mask) ? Math.min(1, Math.max(0, mask)) : 0.35);
    if (!image || !background.image) {
        console.debug("[card/background] fallback: no image");
        return;
    }
    let timer;
    try {
        const loaded = new Promise((resolve, reject) => {
            image.onload = resolve;
            image.onerror = () => reject(new Error("image load failed"));
        });
        image.src = background.image;
        await Promise.race([
            loaded.then(() => typeof image.decode === "function" ? image.decode() : undefined),
            new Promise((_, reject) => { timer = setTimeout(() => reject(new Error("decode timeout")), 1000); }),
        ]);
        document.body.classList.add("has-remote-background");
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        console.debug(`[card/background] decoded: ${image.naturalWidth}x${image.naturalHeight}`);
    } catch (error) {
        document.body.classList.remove("has-remote-background");
        image.removeAttribute("src");
        console.debug(`[card/background] fallback: ${error}`);
    } finally {
        clearTimeout(timer);
        image.onload = null;
        image.onerror = null;
    }
};
