/*
  Keeps a table's batch selection consistent: the header box, the row boxes,
  the tint on a picked row, and the count a toolbar shows.

  The checkboxes need nothing from here — they are checkboxes, and a form posts
  them. What needs watching is everything that has to agree with them, none of
  it expressible in HTML:

    - a header box that ticks and clears its column
    - the third state that box has to show, `indeterminate`, which is a DOM
      property with no attribute and therefore cannot be rendered at all
    - `data-state="selected"` on each picked row, which is how Basecoat tints it
    - a live "3 selected" readout, so the person can see what a bulk action is
      about to reach

  Selections are keyed by NAME, not by table. The name is the form field the
  boxes post under — `data-fjkit-select="selected"` on the rows,
  `data-fjkit-select-all="selected"` on the header — and it is the right key
  because it already decides what lands in one request. Two tables sharing a
  name are one selection to the server, so they are one selection here too. A
  page wanting two independent ones gives them two names.

  Everything is delegated from `document`, and every state is read out of the
  DOM on each pass. Sorting and paging replace the table, so a listener bound to
  a header box — or a count cached in a variable — would describe the table that
  used to be there. Nothing below reconciles against a swap for the same reason:
  the fresh markup is already correct.

  Loaded per page by `select_scripts()`, never from the shell (CHARTER §7).
*/
;(() => {
  const ALL = "data-fjkit-select-all"
  const ROW = "data-fjkit-select"
  const COUNT = "data-fjkit-select-count"

  /* `CSS.escape` produces backslash escapes, which are valid inside a CSS
     string as well as in an identifier, so this is safe for a name with a
     bracket or a dot in it — `items[0]` is a legal form field name. */
  const all = (attribute, name) =>
    [...document.querySelectorAll(`[${attribute}="${CSS.escape(name)}"]`)]

  const boxes = (name) => all(ROW, name).filter((el) => el instanceof HTMLInputElement)

  /* Bring everything that describes the selection called `name` back into line
     with the boxes, which are the only state there is. */
  const sync = (name) => {
    const rows = boxes(name)
    const picked = rows.filter((box) => box.checked)

    for (const box of rows) {
      /* `closest`, not `parentElement.parentElement`: the cell is the macro's,
         but the row is the caller's and may wrap the cell in anything. A box
         outside a table simply has no row to tint. */
      const row = box.closest("tr")
      if (!row) continue
      if (box.checked) row.setAttribute("data-state", "selected")
      else row.removeAttribute("data-state")
    }

    for (const header of all(ALL, name)) {
      if (!(header instanceof HTMLInputElement)) continue
      /* An empty column leaves the header unticked rather than ticked: `every`
         is vacuously true over no rows, and a header that ticks itself on an
         empty table claims a selection nobody made. */
      header.checked = rows.length > 0 && picked.length === rows.length
      header.indeterminate = picked.length > 0 && picked.length < rows.length
    }

    for (const readout of all(COUNT, name)) {
      /* Both strings come from the macro, so a translated page translates them
         and nothing here has an English word in it. A readout with no zero
         text is one that hides while the selection is empty. */
      const zero = readout.getAttribute("data-fjkit-select-zero")
      const template = readout.getAttribute("data-fjkit-select-label") || "{n}"
      readout.textContent = picked.length ? template.replace("{n}", String(picked.length)) : (zero ?? "")
      readout.hidden = picked.length === 0 && zero === null
    }
  }

  document.addEventListener("change", (event) => {
    const target = event.target
    if (!(target instanceof HTMLInputElement)) return

    const header = target.getAttribute(ALL)
    if (header !== null) {
      for (const box of boxes(header)) box.checked = target.checked
      sync(header)
      return
    }

    const row = target.getAttribute(ROW)
    if (row !== null) sync(row)
  })

  /* One pass over whatever is on the page, so a selection the server rendered
     as already ticked arrives with its rows tinted and its header showing the
     dash. htmx fires `htmx:load` for the initial document as well as for every
     swap, so this covers both without a `DOMContentLoaded` of its own — and
     `htmx:load` on a swap gives us the fresh markup, which is the only time
     any of this needs recomputing.

     `names` is derived from the header boxes, not from the row boxes: a table
     with no header box has nothing here to correct. */
  const syncAll = () => {
    for (const name of new Set([...document.querySelectorAll(`[${ALL}]`)].map((el) => el.getAttribute(ALL)))) {
      sync(name)
    }
  }

  document.addEventListener("htmx:load", syncAll)
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", syncAll)
  else syncAll()
})()
