/*
  What makes a Plotly chart look like it belongs on a fjkit page.

  The series run on Plotly's own palette — the figure the server sends carries
  no colour, and nothing here paints one on. What this file does is the other
  half: everything *around* the data. Axis labels, grid lines, tick text, the
  gaps between pie slices, the hover card. Those are properties of the card the
  chart sits in, not of the data, and Plotly's defaults for them are `#444`
  text on `#eee` grid — which is a chart drawn for a white page, on a page that
  might be dark.

  So the chrome is resolved from the live tokens on every draw, and a theme
  toggle is a redraw. The data colours are not, and do not change.

  The division of labour with the server:

      Python decides the shape.   This file decides the chrome.

  Loaded only by charts/page.html. Plotly is 1.1 MB — no other page pays for it.
*/
(() => {
  "use strict";

  /* How a token becomes something Plotly understands.

     The tokens are `oklch()`. Plotly parses colours with tinycolor2, which
     predates CSS Color 4 — hand it `oklch(0.72 0.15 275)` and it does not
     report an error, it quietly draws its own default palette instead. That
     failure is invisible in a screenshot unless you know what fjkit's primary
     is meant to look like, which is what makes it worth this much comment.
     `var(--success)` fails the same way and is worse, because `plotly.py`
     *accepts* that string on the server: it validates, it serialises, and it
     is discarded here.

     So the conversion has to happen in the browser, and it has to use the
     browser's own parser: any table we wrote would be a second definition of
     the colour, and the whole point is that there is one.

     *Not* enough: assigning to `fillStyle` and reading it back. That
     round-trip normalises the legacy formats to `#rrggbb`, but modern colour
     functions are preserved verbatim — `oklch` in, `oklch` out — so it looks
     like it works right up until you check what Plotly received.

     What does work is painting one pixel and reading it. `getImageData`
     answers in sRGB bytes whatever the source notation was, which is also the
     right clamp: the SVG Plotly emits is sRGB regardless. One 1x1 canvas,
     read a handful of times per redraw.

     Assigning the fallback first matters: an unparseable value leaves
     `fillStyle` untouched, and without a known starting point a typo'd token
     would inherit the previous colour instead of being visibly wrong. */
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 1;
  const probe = canvas.getContext("2d", { willReadFrequently: true });

  function resolve(token, fallback) {
    const raw = getComputedStyle(document.documentElement).getPropertyValue(token).trim();
    probe.clearRect(0, 0, 1, 1);
    probe.fillStyle = fallback;
    probe.fillStyle = raw || fallback;
    probe.fillRect(0, 0, 1, 1);
    /* Alpha carried through rather than flattened: `--border` is defined as
       white at 11% in dark mode, and a grid line that ignores that is a grid
       line drawn on top of the data. */
    const [r, g, b, a] = probe.getImageData(0, 0, 1, 1).data;
    return `rgba(${r}, ${g}, ${b}, ${(a / 255).toFixed(3)})`;
  }

  /* Read once per draw, not once per load: the theme toggle changes all three,
     and a cached palette is how a chart ends up in yesterday's colours. */
  function palette() {
    return {
      text: resolve("--foreground", "#333333"),
      grid: resolve("--border", "#cccccc"),
      surface: resolve("--popover", "#ffffff"),
    };
  }

  /* The per-trace half of the chrome.

     Only pies need it, and only because Plotly's pie ignores `layout.font`:
     its `textfont` defaults to #444 whatever the rest of the figure says, so
     the labels come out dark grey on whatever the card is. The slice gaps get
     the card's colour too, which is what makes a donut read as cut rather than
     outlined.

     Nothing here touches `marker.color` or `marker.colors`. The series
     palette is Plotly's. */
  function chrome(data, colors) {
    return data.map((trace) =>
      trace.type === "pie"
        ? {
            ...trace,
            marker: { ...trace.marker, line: { color: colors.surface, width: 2 } },
            textfont: { color: colors.text },
          }
        : trace,
    );
  }

  /* The layout half the theme owns. The figure's own layout is merged
     over the top, so anything the route decided wins. */
  function themed(colors, height) {
    /* Inherit the page's font rather than naming one. Plotly's default is
       Open Sans, which is not what anything else on the card is set in. */
    const font = { color: colors.text, family: getComputedStyle(document.body).fontFamily, size: 12 };
    const axis = {
      gridcolor: colors.grid,
      zerolinecolor: colors.grid,
      linecolor: colors.grid,
      tickfont: font,
      automargin: true,
    };

    return {
      height: height,
      /* Transparent, so the card underneath is the background in both themes
         and there is no second surface colour to keep in agreement. */
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: font,
      margin: { l: 8, r: 8, t: 8, b: 8 },
      legend: { orientation: "h", y: -0.18, font: font },
      xaxis: { ...axis },
      yaxis: { ...axis, rangemode: "tozero" },
      hoverlabel: { bgcolor: colors.surface, bordercolor: colors.grid, font: font },
    };
  }

  /* One level deep, which is exactly what the axes need: the figure carries
     `yaxis: {title, dtick}` and the theme carries `yaxis: {gridcolor,
     tickfont}`. A plain spread would drop one whole side of that. */
  function merge(base, extra) {
    const out = { ...base };
    for (const [key, value] of Object.entries(extra || {})) {
      const mergeable =
        value && typeof value === "object" && !Array.isArray(value) && base[key] && typeof base[key] === "object";
      out[key] = mergeable ? { ...base[key], ...value } : value;
    }
    return out;
  }

  /* `react` rather than `newPlot`: it is the idempotent one. First draw,
     theme change and htmx swap all go through the same call, so there is no
     "has this been drawn yet" flag to get wrong. */
  const CONFIG = { displayModeBar: false, responsive: true, staticPlot: false };

  function draw(element) {
    const figure = JSON.parse(element.dataset.figure);
    /* The height arrives as a number and is applied here rather than as a
       `style=""` in the template. fjkit's vocabulary is closed and has no
       sizing utility, so the alternative was an inline style in markup — and
       the height is a property of the figure, which is already a model. */
    const height = Number(element.dataset.height) || 288;
    element.style.height = height + "px";

    const colors = palette();
    Plotly.react(element, chrome(figure.data, colors), merge(themed(colors, height), figure.layout), CONFIG);
  }

  function drawAll(root) {
    const scope = root || document;
    /* `matches` first, because an htmx swap can hand us the chart element
       itself — `querySelectorAll` never returns its own root. */
    if (scope.matches && scope.matches("[data-chart]")) draw(scope);
    if (scope.querySelectorAll) scope.querySelectorAll("[data-chart]").forEach(draw);
  }

  if (!window.Plotly) {
    console.warn("[charts] Plotly did not load; the figcaption under each chart is the fallback.");
    return;
  }

  addEventListener("DOMContentLoaded", () => drawAll(document));

  /* htmx swaps in charts that have never been drawn. `htmx:load` fires once
     per new node, which is exactly the hook — `htmx:afterSwap` would fire once
     per *request* and hand back the target rather than the new content. */
  document.body.addEventListener("htmx:load", (event) => drawAll(event.target));

  /* And it swaps them *out*. Plotly attaches resize listeners and, on some
     trace types, a WebGL context; dropping the node without saying so leaks
     both. This is the half that a chart-in-a-partial usually forgets. */
  document.body.addEventListener("htmx:beforeCleanupElement", (event) => {
    if (event.target.matches && event.target.matches("[data-chart]")) Plotly.purge(event.target);
  });

  /* The theme toggle flips `.dark` on <html> and nothing else fires. Watching
     the attribute keeps this file independent of how the toggle is
     implemented — a `prefers-color-scheme` change ends up here too, because
     the shell's flash-guard writes the same class.

     What the redraw changes is the chrome: text, grid, slice gaps, hover card.
     The data keeps its colours, because they were never ours.

     Not watched: the demo's style-pack picker. The eight packs define no
     colour tokens at all — they differ in geometry, radii and control
     heights — so a pack switch cannot change anything read here. */
  new MutationObserver(() => drawAll(document)).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"],
  });
})();
