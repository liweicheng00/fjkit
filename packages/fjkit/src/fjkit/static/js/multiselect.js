/*
  Multi-select, on the wire.

  Basecoat's `select` and `combobox` both do multiple selection — their JS keys
  off `aria-multiselectable="true"` on the listbox — and both serialise the
  answer the same way: one hidden input carrying `JSON.stringify(values)`.
  That is a *string* by the time it reaches a server. A route declaring
  `labels: list[str] = Form([])` would be handed `'["bug","ui"]'` and reject it,
  and the 422 would name a field the page looks like it filled in correctly.

  So this file re-emits the choice as the shape HTML has used for a repeated
  field since forms existed:

      labels=bug&labels=ui

  Nothing downstream then has to know a multi-select was involved. One
  declaration reads a checkbox group, a native `<select multiple>` and this —
  and `encoding="json"` keeps working too, because the vendored json-enc
  collects repeated keys into an array on its own.

  Two paths, because `form()` has two: a form with `target=` is submitted by
  htmx, a form without one is submitted by the browser. They are mutually
  exclusive and the guard below is what keeps them that way — a form handled by
  both would post every value twice.

  The marker is `data-fjkit-multi` on the hidden input, written by the macros.
  Not a class and not the JSON's own shape: a value that merely looks like an
  array is not a reason to rewrite somebody's field.

  Loaded per page by `multiselect_scripts()`, never from the shell (CHARTER §7).
*/
(() => {
  const HIDDEN = 'input[type="hidden"][data-fjkit-multi]'

  /* Forms htmx will submit itself. `hx-boost` is included even though `form()`
     never emits it, because an app is free to boost a region containing one. */
  const HTMX_FORM = "[hx-post],[hx-get],[hx-put],[hx-patch],[hx-delete],[hx-boost]," +
                    "[data-hx-post],[data-hx-get],[data-hx-put],[data-hx-patch]," +
                    "[data-hx-delete],[data-hx-boost]"

  /* An unparseable value posts nothing rather than posting the raw string.
     Basecoat writes this input on every change, so the only way to reach a
     malformed one is to hand-edit it — and a literal `["bug"` arriving at a
     route as a label is worse than the field being absent. */
  const values = (input) => {
    let parsed
    try {
      parsed = JSON.parse(input.value || "[]")
    } catch {
      return []
    }
    if (!Array.isArray(parsed)) return []
    return parsed.filter((value) => value !== null && typeof value !== "object").map(String)
  }

  /* The htmx path. `event.detail.parameters` is a FormData in htmx 2, so the
     rewrite is delete-then-append and htmx encodes the repeats for us.

     Keyed off the parameters rather than off a DOM subtree on purpose: htmx has
     already decided what this request carries — `hx-include`, `hx-vals` and a
     button outside its form all land here — and re-deriving that from `elt`
     would get a different answer than htmx did. */
  document.addEventListener("htmx:configRequest", (event) => {
    const params = event.detail.parameters
    if (!params || typeof params.getAll !== "function") return

    for (const name of [...new Set(params.keys())]) {
      const raw = params.get(name)
      if (typeof raw !== "string" || raw.charAt(0) !== "[") continue
      const input = document.querySelector(`${HIDDEN}[name="${CSS.escape(name)}"]`)
      /* Same name *and* same value: two selects can share a name across a swap,
         and a parameter htmx built from something else is not ours to touch. */
      if (!input || input.value !== raw) continue
      params.delete(name)
      for (const value of values(input)) params.append(name, value)
    }
  })

  /* The no-JavaScript-form path — which is to say, the form that needs this
     script and nothing else.

     Capture phase, so the expansion is in place before any submit handler an
     app added can call `preventDefault`. The original input is disabled rather
     than emptied, because a disabled control is omitted from the submission
     without losing the value the page has to keep showing.

     Everything is undone on the next tick. A submit the browser did not go
     through with — blocked by constraint validation, cancelled by a handler —
     otherwise leaves the form carrying both representations, and the next
     submit posts each value twice. */
  document.addEventListener(
    "submit",
    (event) => {
      const form = event.target
      if (!(form instanceof HTMLFormElement)) return
      if (form.matches(HTMX_FORM) || form.closest(HTMX_FORM)) return

      const injected = []
      const disabled = []
      for (const input of form.querySelectorAll(HIDDEN)) {
        /* `anchor` walks forward as fields are inserted. Inserting each one
           after the *original* input reverses the selection, because every
           insert pushes the previous one further down — and a form field's
           order is the order it is posted in. */
        let anchor = input
        for (const value of values(input)) {
          const field = document.createElement("input")
          field.type = "hidden"
          field.name = input.name
          field.value = value
          anchor.after(field)
          anchor = field
          injected.push(field)
        }
        input.disabled = true
        disabled.push(input)
      }
      if (!injected.length && !disabled.length) return

      setTimeout(() => {
        for (const field of injected) field.remove()
        for (const input of disabled) input.disabled = false
      })
    },
    true,
  )
})()
