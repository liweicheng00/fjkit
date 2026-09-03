/* Shared by every page. Loaded by base.html, after Basecoat's own script.
 *
 * Small on purpose. Everything this file used to do that a component can do is
 * now done by one: the tab strips are Basecoat's `.tabs` (its JS owns selection
 * and the arrow keys), the navigation is `sidebar_link`, and Jinja renders the
 * in-page rail from each page's `sections` list. What is left is a highlighter,
 * a scroll-spy, and three helpers. */

/* ------------------------------------------------------------------ utils */
const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fill = (html, map) => html.replace(/__[A-Z0-9]+__/g, (key) => (key in map ? map[key] : ""));

/* Highlighter for the source panes. Escape first, then colour in a single pass:
   one alternation per language, so a later rule can never rescan a span this
   function inserted. (`class` is a Python keyword, which is how a multi-pass
   version eats its own markup.)

   Tokens are marked with `data-t`, not a class. Nothing this file injects should
   be mistakable for a class an app may write: the page that teaches the closed
   vocabulary should not sprinkle `.k` through itself. */
const RULES = {
  jinja: [
    /(\{#[\s\S]*?#\})|(\{%[\s\S]*?%\}|\{\{[\s\S]*?\}\})|(&quot;[^&\n]*?&quot;)/g,
    ["c", "k", "s"],
  ],
  python: [
    /(#[^\n]*)|(&quot;[^&\n]*?&quot;)|\b(from|import|def|return|class|async|await|with|yield|if|not|None|for|in)\b/g,
    ["c", "s", "k"],
  ],
  html: [
    /(&lt;\/?[a-zA-Z][\w-]*)|([a-zA-Z-]+)(?==&quot;)|(&quot;[^&]*?&quot;)/g,
    ["k", "a", "s"],
  ],
  css: [
    /(\/\*[\s\S]*?\*\/)|(--[\w-]+)|(oklch\([^)]*\))/g,
    ["c", "k", "s"],
  ],
};

function highlight(source, lang) {
  const escaped = esc(source);
  const rule = RULES[lang];
  if (!rule) return escaped;
  const [pattern, kinds] = rule;
  return escaped.replace(pattern, (match, ...groups) => {
    const index = groups.findIndex((group, i) => i < kinds.length && group !== undefined);
    return index === -1 ? match : `<span data-t="${kinds[index]}">${match}</span>`;
  });
}

const setCode = (el, source, lang) => { el.innerHTML = highlight(source, lang); };

/* --------------------------------------------------------- static code panes
 * Any <pre data-lang> printed by a template is highlighted here, reading the
 * source back out of textContent. Two reasons for doing it here rather than at
 * build time: the code stays legible with scripting off, and there is one
 * highlighter instead of a server-side copy that has to agree with it. */
document.querySelectorAll("pre[data-lang]").forEach((el) => {
  if (el.textContent.trim()) setCode(el, el.textContent, el.dataset.lang);
});

/* ------------------------------------------------------------- scroll-spy
 * The rail itself is server-rendered: base.html loops over the page's `sections`
 * and calls `sidebar_link` for each, so the navigation and the headings are one
 * list. All that is left for the browser is which section you are looking at,
 * which a static file cannot know. `aria-current` is what Basecoat's sidebar
 * styles and what a screen reader announces, so marking the active link is the
 * whole job — no class toggle beside it. */
(function scrollSpy() {
  const links = new Map();
  document.querySelectorAll(".sidebar a[href*='#']").forEach((a) => {
    const id = a.getAttribute("href").split("#")[1];
    const section = id && document.getElementById(id);
    if (section) links.set(section, a);
  });
  if (!links.size) return;

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      links.forEach((link, section) => {
        if (section === entry.target) link.setAttribute("aria-current", "true");
        else link.removeAttribute("aria-current");
      });
    });
  }, { rootMargin: "-15% 0px -75% 0px" });

  links.forEach((_, section) => observer.observe(section));
})();
