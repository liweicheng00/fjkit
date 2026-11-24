/*
  Themes a Plotly chart to the fjkit page it sits on.

  The series run on Plotly's own palette: the figure the server sends carries no
  colour, and nothing here paints one on. This file does the other half —
  everything around the data. Axis labels, grid lines, tick text, the gaps
  between pie slices, the hover card. Those belong to the card the chart sits in,
  not to the data, and Plotly's defaults for them are `#444` text on `#eee` grid:
  a chart drawn for a white page, on a page that might be dark.

  So the chrome is resolved from the live tokens on every draw, and a theme
  toggle is a redraw. The data colours are not resolved and do not change.

  The division of labour with the server: Python decides the shape, this file
  decides the chrome.

  *When* each chart draws is the other half of the file. Drawing one costs
  around 20 ms, and a page is not obliged to show them all at once, so a chart
  is drawn when it first comes into view rather than on load — see `observer`.

  Loaded only via chart_scripts(). Plotly is 1.4 MB — no other page pays for it.
*/
(() => {
  "use strict";

  /* How a token becomes something Plotly understands.

     The tokens are `oklch()`. Plotly parses colours with tinycolor2, which
     predates CSS Color 4: hand it `oklch(0.72 0.15 275)` and it reports no
     error, it draws its own default palette instead. That failure is invisible
     in a screenshot unless you know what fjkit's primary is meant to look like,
     which is what makes it worth this much comment. `var(--success)` fails the
     same way and is worse, because `plotly.py` accepts that string on the
     server: it validates, it serialises, and it is discarded here.

     So the conversion happens in the browser, using the browser's own parser.
     Any table written here would be a second definition of the colour, and the
     point is that there is one.

     Not enough: assigning to `fillStyle` and reading it back. That round-trip
     normalises the legacy formats to `#rrggbb` but preserves modern colour
     functions verbatim — `oklch` in, `oklch` out — so it looks like it works
     until you check what Plotly received.

     Painting one pixel and reading it does work. `getImageData` answers in sRGB
     bytes whatever the source notation was, which is also the right clamp: the
     SVG Plotly emits is sRGB regardless. One 1x1 canvas, read a handful of times
     per redraw.

     Assigning the fallback first matters: an unparseable value leaves
     `fillStyle` untouched, so without a known starting point a mistyped token
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
    /* Alpha is carried through rather than flattened: `--border` is defined as
       white at 11% in dark mode, and a grid line that ignores that is drawn on
       top of the data. */
    const [r, g, b, a] = probe.getImageData(0, 0, 1, 1).data;
    return `rgba(${r}, ${g}, ${b}, ${(a / 255).toFixed(3)})`;
  }

  /* Read once per draw, not once per load: the theme toggle changes all three,
     and a cached palette leaves the chart in the previous theme's colours. */
  function palette() {
    return {
      text: resolve("--foreground", "#333333"),
      grid: resolve("--border", "#cccccc"),
      surface: resolve("--popover", "#ffffff"),
    };
  }

  /* Trace types that draw a colour bar down the right-hand side. Its tick text
     inherits `layout.font`, but its frame is `#444` whatever the figure says —
     the same hard-coded default as the pie's label colour, in a different
     place. */
  const COLORBAR = new Set(["heatmap", "contour", "histogram2d", "histogram2dcontour"]);

  /* Trace types whose mark is a length measured from zero, and the only ones
     whose y axis is forced through it. `themed` says why. `pie` is here because
     it has no cartesian axes at all, so a pie beside a bar does not disqualify
     the pair. */
  const BASELINE = new Set(["bar", "scatter", "histogram", "pie"]);

  /* The per-trace half of the chrome.

     Two types need it, both for the same reason: a default Plotly resolves
     before `layout.font` reaches it.

     A pie ignores `layout.font` outright — its `textfont` defaults to #444
     whatever the rest of the figure says, so the labels come out dark grey on
     whatever colour the card is. The slice gaps get the card's colour too, which
     makes a donut read as cut rather than outlined.

     A colour-bar trace inherits the font but not the frame, so an unthemed
     `outlinecolor: "#444"` draws a dark box around the scale on a dark page.

     Nothing here touches `marker.color`, `marker.colors` or `colorscale`. The
     series palette is Plotly's, and so is the scale. */
  function chrome(data, colors) {
    return data.map((trace) => {
      if (trace.type === "pie") {
        return {
          ...trace,
          marker: { ...trace.marker, line: { color: colors.surface, width: 2 } },
          textfont: { color: colors.text },
        };
      }
      if (COLORBAR.has(trace.type)) {
        return { ...trace, colorbar: { outlinecolor: colors.grid, ...trace.colorbar } };
      }
      return trace;
    });
  }

  /* The layout half the theme owns. The figure's own layout is merged over the
     top, so anything the route decided wins.

     `baseline` is the one part of this that reads the data. `rangemode:
     "tozero"` is right where the mark's length is the quantity — a bar is a lie
     if its axis starts anywhere else — and harmless for a line of counts. It is
     wrong everywhere else. For a box or a violin the quantity is the spread:
     latencies between 180 and 260 ms get an axis from 0 to 260, and the shape
     they were drawn for is a flat smudge in the top fifth of the card. For a
     heatmap or an image the y axis is a position, not an amount.

     So it is opt-in by type rather than opt-out: see `BASELINE`. Still
     overridable either way — the figure's `yaxis` merges over this one.

     The ternary block is the counterpart of the pie's `textfont`. A ternary
     subplot does not read `plot_bgcolor` or the axis defaults above; its own
     are `bgcolor: "#fff"` with `#444` axes, so an unthemed one puts a white
     panel in the middle of a dark card. Costs nothing on a figure with no
     ternary trace, because Plotly ignores a subplot nothing is assigned to. */
  function themed(colors, height, baseline) {
    /* Inherits the page's font rather than naming one. Plotly's default is
       Open Sans, which nothing else on the card is set in. */
    const font = { color: colors.text, family: getComputedStyle(document.body).fontFamily, size: 12 };
    const axis = {
      gridcolor: colors.grid,
      zerolinecolor: colors.grid,
      linecolor: colors.grid,
      tickfont: font,
      /* The margins below are 8 px a side — room for the plot and nothing else
         — and `automargin` is what keeps an axis title or a rotated tick label
         from being clipped by them: Plotly measures the text it drew and grows
         the margin to fit.

         It costs a second layout pass per chart. Seventy charts took 1458 ms
         with it and 754 ms with `automargin: false` and explicit margins, so
         about half of the ~20 ms a chart takes to draw. It stays the default
         because the alternative default is labels quietly cut off, and because
         with drawing deferred to first sight the pass is paid per chart on
         screen. A page that knows its own margins can have it back: the
         figure's layout merges over this one, so `automargin=False` on both
         axes plus a `layout.margin` wide enough for the labels turns it off. */
      automargin: true,
    };
    const ternaryAxis = { gridcolor: colors.grid, linecolor: colors.grid, tickfont: font, color: colors.text };

    return {
      height: height,
      /* Transparent, so the card underneath is the background in both themes and
         there is no second surface colour to keep in agreement. */
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: font,
      margin: { l: 8, r: 8, t: 8, b: 8 },
      legend: { orientation: "h", y: -0.18, font: font },
      xaxis: { ...axis },
      yaxis: baseline ? { ...axis, rangemode: "tozero" } : { ...axis },
      ternary: {
        bgcolor: "rgba(0,0,0,0)",
        aaxis: { ...ternaryAxis },
        baxis: { ...ternaryAxis },
        caxis: { ...ternaryAxis },
      },
      hoverlabel: { bgcolor: colors.surface, bordercolor: colors.grid, font: font },
    };
  }

  /* Deep over plain objects, which is what the axes need: the figure carries
     `yaxis: {title, dtick}` and the theme carries `yaxis: {gridcolor,
     tickfont}`. A plain spread would drop one whole side of that.

     It recurses rather than stopping at one level because a ternary subplot
     nests one deeper — the theme sets `ternary.aaxis.gridcolor` and the figure
     sets `ternary.aaxis.title`, and a one-level merge replaces the theme's
     whole `aaxis` with the figure's, which is how the axes of a ternary plot
     end up back at Plotly's #444 on a dark card. Arrays replace rather than
     merge: a figure's `x` is the data, not an amendment to the theme's. */
  function merge(base, extra) {
    const out = { ...base };
    for (const [key, value] of Object.entries(extra || {})) {
      const mergeable =
        value && typeof value === "object" && !Array.isArray(value) && base[key] && typeof base[key] === "object";
      out[key] = mergeable ? merge(base[key], value) : value;
    }
    return out;
  }

  /* `react` rather than `newPlot`: `react` is idempotent. First draw, theme
     change and htmx swap all go through the same call, so no path has to ask
     whether this element has been drawn before in order to draw it. */
  const CONFIG = { displayModeBar: false, responsive: true, staticPlot: false };

  /* The height arrives as a number and is applied from here rather than as a
     `style=""` in the template. fjkit's vocabulary is closed and has no sizing
     utility, so the alternative was an inline style in markup — and the height
     is a property of the figure, which is already a model.

     Applied before the chart is drawn rather than as part of drawing it, which
     is what makes drawing on sight work at all: an undrawn `[data-chart]` is an
     empty div, so seventy unsized ones are a page several screens shorter than
     it will be, all seventy inside the viewport and all seventy drawing on
     load. It also means nothing below a chart moves when it draws. */
  function reserve(element) {
    const height = Number(element.dataset.height) || 288;
    element.style.height = height + "px";
    return height;
  }

  /* Which charts have been drawn: the set a theme change repaints.

     Not a guard against drawing twice — `react` already is one. It is the
     difference between a chart on screen and one still waiting to be scrolled
     to, and a theme change has to repaint the first without pulling the second
     forward, which is where the saving would go. The one still waiting loses
     nothing: `palette()` is read per draw, so it arrives in whatever theme is
     current when it finally draws.

     A `WeakSet` rather than a list, because this file must not be the reason a
     swapped-out chart is still in memory. It cannot be iterated, so the theme
     redraw walks the DOM and asks. */
  const drawn = new WeakSet();

  function draw(element) {
    const figure = JSON.parse(element.dataset.figure);
    const colors = palette();
    const baseline = figure.data.every((trace) => BASELINE.has(trace.type));
    drawn.add(element);
    Plotly.react(
      element,
      chrome(figure.data, colors),
      merge(themed(colors, reserve(element), baseline), figure.layout),
      CONFIG,
    );
  }

  /* Draw on first sight.

     The root is the viewport, and what the observer reports is clipped by every
     ancestor on the way up to it. That is the case worth having: a chart in an
     `overflow-x: auto` row, scrolled off the side of that row, is reported as
     not visible, where comparing the chart's own rectangle against the viewport
     would call it on screen and draw it.

     `rootMargin` starts the draw before the chart reaches the fold, so it is
     there by the time it is looked at. It expands the root only — an ancestor's
     clip is not grown with it — so a chart inside a scrolling row draws as it
     enters the row rather than ahead of it.

     Unobserved on the first intersection: a chart is drawn once, and after that
     the theme toggle is the only thing that repaints it. */
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        observer.unobserve(entry.target);
        draw(entry.target);
      }
    },
    { rootMargin: "200px" },
  );

  /* `data-chart="eager"` draws now instead of on sight — `chart(item,
     eager=true)` in the macro — for the one chart a page is about. Observation
     is asynchronous: the first entries arrive after the first layout, so even a
     chart at the top of the page draws a frame or two late. Below the fold that
     is invisible, and that is nearly every chart. */
  function schedule(element) {
    reserve(element);
    if (element.dataset.chart === "eager") draw(element);
    else observer.observe(element);
  }

  function scheduleAll(root) {
    const scope = root || document;
    /* `matches` first, because an htmx swap can hand back the chart element
       itself — `querySelectorAll` never returns its own root. */
    if (scope.matches && scope.matches("[data-chart]")) schedule(scope);
    if (scope.querySelectorAll) scope.querySelectorAll("[data-chart]").forEach((node) => schedule(node));
  }

  if (!window.Plotly) {
    console.warn("[charts] Plotly did not load; the figcaption under each chart is the fallback.");
    return;
  }

  addEventListener("DOMContentLoaded", () => scheduleAll(document));

  /* htmx swaps in charts that have never been drawn. `htmx:load` fires once per
     new node, which is the hook needed here — `htmx:afterSwap` fires once per
     request and hands back the target rather than the new content.

     Swapped in is not drawn: new cards are sized and observed like any other,
     so a swap into a region that is off screen costs the request and nothing
     more, and one into the part being looked at draws straight away. */
  document.body.addEventListener("htmx:load", (event) => scheduleAll(event.target));

  /* htmx also swaps charts out, and either half of a chart's state can be live
     when it goes. A drawn one holds Plotly's resize listeners and, on some
     trace types, a WebGL context; dropping the node without purging leaks both,
     and a chart inside a partial usually forgets this half. An undrawn one is
     still a target of the observer, which holds a reference to everything it
     watches — the leak drawing on sight introduces, in the other direction. */
  document.body.addEventListener("htmx:beforeCleanupElement", (event) => {
    const element = event.target;
    if (!element.matches || !element.matches("[data-chart]")) return;
    observer.unobserve(element);
    /* `delete` answers whether it was there, which is exactly the question:
       purge what Plotly drew into, and nothing else. */
    if (drawn.delete(element)) Plotly.purge(element);
  });

  /* The theme toggle flips `.dark` on <html> and nothing else fires. Watching
     the attribute keeps this file independent of how the toggle is implemented,
     and a `prefers-color-scheme` change lands here too, because the shell's
     flash-guard writes the same class.

     The redraw changes the chrome: text, grid, slice gaps, hover card. The data
     keeps its colours, which were never ours.

     Only what has been drawn. A chart still waiting for its first sight is left
     waiting — redrawing it here would be its first draw, and a theme toggle
     would cost what a page load no longer does.

     Not watched: the demo's style-pack picker. The eight packs define no colour
     tokens at all — they differ in geometry, radii and control heights — so a
     pack switch cannot change anything read here. */
  new MutationObserver(() => {
    document.querySelectorAll("[data-chart]").forEach((element) => {
      if (drawn.has(element)) draw(element);
    });
  }).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"],
  });
})();
