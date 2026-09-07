---
name: liteyuki-lts-card-ui
description: Create or update user-facing rendered image cards for LiteyukiBot v6 LTS while preserving this repository's shared visual language, resource paths, and htmlrender conventions. Use for new custom plugin cards or changes to existing status, weather, statistics, list, and dashboard images; not for plain-text command replies.
---

# LiteyukiBot v6 LTS Card UI

Build image output as an extension of the repository's existing UI, not as a separate design system.

## Start from the shared resources

Inspect these files before editing a card:

- `src/resources/vanilla_resource/templates/css/card.css`: layout width, card tokens, spacing, radius, shadows, and colors.
- `src/resources/vanilla_resource/templates/css/fonts.css`: local MiSans font faces.
- `src/resources/vanilla_resource/templates/js/card.js`: shared card-page marker.
- The closest existing card under `src/resources/liteyuki_weather`, `src/resources/liteyuki_statistics`, or `src/resources/vanilla_resource/templates`.

Link shared assets with the established template-relative paths:

```html
<link rel="stylesheet" href="./css/card.css">
<link rel="stylesheet" href="./css/fonts.css">
<script src="./js/card.js"></script>
```

Resource packs merge into `data/liteyuki/resources`; keep calls such as `get_path("templates/...")` and do not introduce plugin-specific copies of shared CSS, fonts, or JavaScript.

## Visual language

- Design for an approximately 1080 px wide QQ image. Keep the body spacing and width owned by `card.css` unless the output has a proven special requirement.
- Use a light blue-white canvas, white or translucent information cards, restrained blue accents, rounded corners, soft blue-gray shadows, and clear large values.
- Reuse the CSS variables from `card.css`: `--card-bg`, `--card-border`, `--card-radius`, `--card-shadow`, `--color-primary`, `--color-primary-soft`, `--main-text-color`, `--sub-text-color`, and `--tip-text-color`.
- Preserve the hierarchy: primary values and titles first, labels and metadata second, low-priority notes last. Prefer compact grids and consistent gaps over dense prose.
- Use MiSans from the bundled resources. Do not fetch web fonts or UI assets at render time.
- Keep controls and decoration modest. Cards must remain readable after QQ compression and on a phone screen.

The current baseline uses roughly 28 px page padding, 28 px main-card radii, 20 px vertical gaps, and a `#2679c9` primary accent. Treat these as defaults, not reasons to duplicate tokens in every plugin stylesheet.

## Card types

- Ordinary user cards: use the clean Base UI with no remote background unless the feature explicitly calls for one.
- Public showcase/status cards: a scoped image background and translucent glass cards are acceptable. Always provide a local gradient or solid fallback, preserve text contrast, and wait for image decode before capture.
- Administrator and diagnostic cards such as `npm`/`rpm`: keep a background-free, high-contrast information layout.
- Short success, failure, install, uninstall, enable, disable, and reload feedback remains plain text unless the request explicitly requires an image.

Do not spread status-only background rules into `card.css`; scope them to the status template and stylesheet.

## Template and data contract

- Keep API response data out of templates. Normalize it in Python into a small view model first.
- Pass data through the existing Jinja JSON container:

```html
<div class="data-storage" id="data">{{ data | tojson }}</div>
```

- Build repeated UI with inert `<template>` elements and populate it in local JavaScript. Assign untrusted text with `textContent`; do not concatenate it into HTML.
- Keep HTML semantic enough to inspect: a page title/header, grouped sections, repeated `article` cards, and a restrained footer or attribution when required.
- Preserve required attribution from external data providers.

## Rendering and delivery

- Reuse `src.utils.message.html_tool.template2image()` for standard templates and `template2image_element()` only when a card must be cropped to a specific content bounding box.
- Keep the standard viewport near 1080 px and make screenshot height follow actual content. Avoid `min-height: 100vh`, fixed-height page shells, or off-flow elements that create blank output.
- When an image or font affects the screenshot, expose a deterministic JavaScript ready flag and wait for decode/load success or fallback before capture.
- Return image bytes through the plugin's existing NoneBot/Alconna message abstraction so OneBot V11 and supported adapters retain their established behavior.
- Do not add Vue, React, Tailwind, ECharts, CDNs, or another front-end framework. Prefer HTML, CSS, SVG, and small local JavaScript.

## Verification

After a change:

1. Confirm all referenced shared paths resolve through the resource loader.
2. Render representative normal, empty, long-text, and large-number data where relevant.
3. Check that the image is approximately 1080 px wide, tightly cropped, readable, and free of unwanted overflow or blank space.
4. Run the targeted UI/template tests and the relevant plugin loading test without requiring external APIs or a browser download.
5. Ensure status-only backgrounds did not affect weather, statistics, `npm`, or `rpm` cards.

Keep plugin command behavior, permissions, API contracts, and data structures unchanged unless the user explicitly includes them in scope.
