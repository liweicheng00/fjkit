/*
  Re-emits a multi-select as repeated form fields.

  Basecoat's `select` and `combobox` both support multiple selection — their JS
  keys off `aria-multiselectable="true"` on the listbox — and both serialise the
  answer the same way: one hidden input carrying `JSON.stringify(values)`. The
  server therefore receives a string. A route declaring
  `labels: list[str] = Form([])` is handed `'["bug","ui"]'` and rejects it, and
  the 422 names a field the page looks like it filled in correctly.

  So this file re-emits the choice in the shape HTML has used for a repeated
  field since forms existed:

      labels=bug&labels=ui

  Nothing downstream has to know a multi-select was involved. One declaration
  reads a checkbox group, a native `<select multiple>` and this. `encoding="json"`
  keeps working too, because the vendored json-enc collects repeated keys into an
  array on its own.

  Two paths, because `form()` has two: htmx submits a form with `target=`, the
  browser submits a form without one. They are mutually exclusive, and the guard
  below keeps them that way — a form handled by both posts every value twice.

  The marker is `data-fjkit-multi` on the hidden input, written by the macros.
  Not a class and not the JSON's own shape: a value that merely looks like an
  array is not a reason to rewrite somebody's field.

  Loaded per page by `multiselect_scripts()`, never from the shell (CHARTER §7).
*/
(() => {
  const HIDDEN = 'input[type="hidden"][data-fjkit-multi]'

  /* Forms htmx submits itself. `hx-boost` is listed even though `form()` never
     emits it, because an app can boost a region containing one. */
  const HTMX_FORM = "[hx-post],[hx-get],[hx-put],[hx-patch],[hx-delete],[hx-boost]," +
                    "[data-hx-post],[data-hx-get],[data-hx-put],[data-hx-patch]," +
                    "[data-hx-delete],[data-hx-boost]"

  /* An unparseable value posts nothing rather than the raw string. Basecoat
     rewrites this input on every change, so only a hand edit produces a
     malformed one — and a literal `["bug"` arriving at a route as a label is
     worse than an absent field. */
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

  /* The htmx path. `event.detail.parameters` is a `FormData` in htmx 2, so the
     rewrite is delete-then-append and htmx encodes the repeats.

     Keyed off the parameters rather than a DOM subtree: htmx has already decided
     what this request carries — `hx-include`, `hx-vals` and a button outside its
     form all land here — and re-deriving that from `elt` gives a different
     answer than htmx did. */
  document.addEventListener("htmx:configRequest", (event) => {
    const params = event.detail.parameters
    if (!params || typeof params.getAll !== "function") return

    for (const name of [...new Set(params.keys())]) {
      const raw = params.get(name)
      if (typeof raw !== "string" || raw.charAt(0) !== "[") continue
      const input = document.querySelector(`${HIDDEN}[name="${CSS.escape(name)}"]`)
      /* Matches on name and value: two selects can share a name across a swap,
         and a parameter htmx built from something else is not ours to touch. */
      if (!input || input.value !== raw) continue
      params.delete(name)
      for (const value of values(input)) params.append(name, value)
    }
  })

  /* The browser-submitted path: the form that needs this script and nothing
     else.

     Capture phase, so the expansion is in place before any submit handler an app
     added can call `preventDefault`. The original input is disabled rather than
     emptied, because a disabled control is omitted from the submission and still
     holds the value the page has to keep showing.

     Everything is undone on the next tick. A submit the browser did not complete
     — blocked by constraint validation, cancelled by a handler — otherwise
     leaves the form carrying both representations, and the next submit posts
     each value twice. */
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
           after the original input reverses the selection, because every insert
           pushes the previous one further down — and a form field's document
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
