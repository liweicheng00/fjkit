/*
  Draws a 422 under the fields of the form that sent it.

  Reads FastAPI's `{"detail": [{"loc": ["body", "title"], "msg": …}]}`, finds
  each control by `name`, and writes the message into the `<p>` its
  `aria-describedby` names (creating one if the field had no hint). Anything
  with no control to land on is raised as a `fjkit:toast`. The next request
  from the same form clears it all and restores the hints.

  Loaded by the shell on every page.
*/
(() => {
  const PAINTED = "data-fjkit-error"
  const TOAST = "fjkit:toast"

  const form = (elt) => (elt instanceof Element ? elt.closest("form") : null)

  /* `("body", "items", 0, "title")` -> `items.0.title`; same rule as
     `field_name` in `fjkit.forms`. Anything not under `body` is not a field. */
  const fieldName = (loc) =>
    Array.isArray(loc) && loc.length > 1 && loc[0] === "body" ? loc.slice(1).map(String).join(".") : null

  /* The element carrying `aria-describedby`: the radiogroup wrapper for a
     radio, the control itself otherwise. */
  const holder = (control) => control.closest('[role="radiogroup"]') || control

  /* The `<p>` under the control, or one shaped like `_message()` writes. */
  const message = (control) => {
    const owner = holder(control)
    let p = document.getElementById(owner.getAttribute("aria-describedby") || "")
    if (p) return p
    const id = `${owner.id || control.id || control.name}-hint`
    p = document.createElement("p")
    p.id = id
    p.className = "text-muted-foreground text-xs"
    p.hidden = true
    owner.after(p)
    owner.setAttribute("aria-describedby", id)
    return p
  }

  const paint = (control, text) => {
    const p = message(control)
    if (!p.hasAttribute(PAINTED)) {
      p.setAttribute(PAINTED, p.hidden ? "" : p.textContent)
      p.classList.replace("text-muted-foreground", "text-destructive")
    }
    p.textContent = text
    p.hidden = false
    holder(control).setAttribute("aria-invalid", "true")
  }

  const clear = (scope) => {
    for (const p of scope.querySelectorAll(`[${PAINTED}]`)) {
      const hint = p.getAttribute(PAINTED)
      p.removeAttribute(PAINTED)
      p.classList.replace("text-destructive", "text-muted-foreground")
      p.textContent = hint
      p.hidden = !hint
    }
    for (const el of scope.querySelectorAll('[aria-invalid="true"]')) el.removeAttribute("aria-invalid")
  }

  const toast = (titles) => {
    if (!titles.length) return
    const messages = titles.map((title) => ({ category: "error", title }))
    document.body.dispatchEvent(new CustomEvent(TOAST, { detail: { messages } }))
  }

  /* Only a 422 carrying JSON is handled; anything else swaps as usual.
     `isError` is left alone: `reset_on_success` reads `detail.successful`,
     which derives from it. */
  document.addEventListener("htmx:beforeSwap", (event) => {
    const { xhr, requestConfig } = event.detail
    if (!xhr || xhr.status !== 422) return
    if (!(xhr.getResponseHeader("content-type") || "").includes("application/json")) return

    let detail
    try {
      detail = JSON.parse(xhr.responseText).detail
    } catch {
      return
    }
    if (!Array.isArray(detail)) return

    event.detail.shouldSwap = false

    const scope = form(requestConfig && requestConfig.elt) || document
    clear(scope)

    const loose = []
    const seen = new Set()
    for (const entry of detail) {
      const name = fieldName(entry.loc)
      const control = name && scope.querySelector(`[name="${CSS.escape(name)}"]`)
      if (!control) {
        loose.push(name ? `${name}: ${entry.msg}` : String(entry.msg))
        continue
      }
      /* First message per field only. */
      if (seen.has(name)) continue
      seen.add(name)
      paint(control, String(entry.msg))
    }
    toast(loose)

    const first = scope.querySelector('[aria-invalid="true"]')
    if (first && typeof first.focus === "function") first.focus({ preventScroll: false })
  })

  /* A new request from the form clears the last rejection. */
  document.addEventListener("htmx:beforeRequest", (event) => {
    const scope = form(event.detail && event.detail.elt)
    if (scope) clear(scope)
  })
})()
