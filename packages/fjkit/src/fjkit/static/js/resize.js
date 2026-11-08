/*
  Lets a visitor resize the columns of a `table(resizable=true)`, by pointer or
  by keyboard, and keeps the widths per table in `localStorage`.

  Why a script at all: CSS `resize` applies only to a block box whose overflow
  is not visible, and a table cell is neither, so no stylesheet can put a drag
  handle on a column edge. Following a pointer has no HTML equivalent either.

  The contract with the markup is three attributes:

    data-fjkit-resize          on the <table>; its id is the storage key
    data-fjkit-resize-handle   on each handle, inside the <th> it resizes;
                               its aria-label, the column's label, names it
    data-fjkit-resized         written here once a column has a set width

  A width is stored under its column's label, not its position. An app that
  adds, removes or reorders a column would otherwise hand a stored width to
  whichever column now sits where the old one was.

  Events are delegated from `document`, so a table htmx swaps in needs nothing
  bound to it. Stored widths go back on in `htmx:load`, which htmx fires for the
  first document and for every swap. A morph keeps the nodes but syncs their
  attributes to the reply, which carries no widths, so a morphed table needs
  them put back as much as a replaced one does.

  Loaded per page by `resize_scripts()`, never from the shell (CHARTER §4.2).
*/
;(() => {
  const TABLE = "data-fjkit-resize"
  const HANDLE = "data-fjkit-resize-handle"
  const RESIZED = "data-fjkit-resized"
  const DRAGGING = "data-dragging"
  const MIN = 48
  const MAX = 1600
  const STEP = 16

  const key = (table) => `fjkit:column-widths-by-label:${table.id}`
  /* Where widths were stored by position, before #52. Not migrated: which
     column a position meant is exactly what an app may have changed since. */
  const legacy = (table) => `fjkit:column-widths:${table.id}`

  /* Storage throws in a private window, on a blocked site or a full quota. A
     width that cannot be saved is still worth applying, so both sides fail to
     "nothing stored" rather than to an error. */
  const load = (table) => {
    try {
      localStorage.removeItem(legacy(table))
      /* No prototype: a column labelled "constructor" must find nothing. */
      const widths = Object.create(null)
      for (const [name, width] of Object.entries(JSON.parse(localStorage.getItem(key(table)) || "{}"))) {
        if (Number.isFinite(width)) widths[name] = width
      }
      return widths
    } catch {
      return Object.create(null)
    }
  }

  const save = (table, widths) => {
    try {
      if (Object.keys(widths).length) localStorage.setItem(key(table), JSON.stringify(widths))
      else localStorage.removeItem(key(table))
    } catch {}
  }

  const headers = (table) => [...(table.tHead?.rows[0]?.cells ?? [])]

  /* One name per header cell, in order: the handle's label, or null for a
     cell without a handle, which never has a stored width. A label repeated in
     one table is told apart by its count, "n", "n#2", so two columns do not
     share a width. */
  const columns = (table) => {
    const seen = Object.create(null)
    return headers(table).map((cell) => {
      const label = cell.querySelector(`[${HANDLE}]`)?.getAttribute("aria-label")
      if (label == null) return null
      seen[label] = (seen[label] ?? 0) + 1
      return seen[label] > 1 ? `${label}#${seen[label]}` : label
    })
  }
  const column = (header) => columns(header.closest("table"))[header.cellIndex]
  const clamp = (width) => Math.round(Math.min(MAX, Math.max(MIN, width)))
  const direction = (table) => (getComputedStyle(table).direction === "rtl" ? -1 : 1)
  const parts = (handle) => {
    const header = handle.closest("th")
    return { header, table: header.closest("table") }
  }

  /* Every column gets a width, not only the ones set by hand: a fixed layout
     shares any width left unclaimed among the rest, and the column beside the
     one being dragged would move with it. All reads come before all writes, so
     the browser lays the table out once. */
  const freeze = (table, widths) => {
    const cells = headers(table)
    const names = columns(table)
    const px = cells.map((cell, i) => (names[i] != null && widths[names[i]]) || cell.getBoundingClientRect().width)
    cells.forEach((cell, i) => {
      cell.style.width = `${px[i]}px`
    })
    table.style.width = `${px.reduce((sum, width) => sum + width, 0)}px`
    table.setAttribute(RESIZED, "")
  }

  /* A focusable separator is a widget, and ARIA gives it a value: the column's
     width in pixels, between the bounds the handle can reach. */
  const describe = (table) => {
    for (const handle of table.querySelectorAll(`[${HANDLE}]`)) {
      handle.setAttribute("aria-valuemin", String(MIN))
      handle.setAttribute("aria-valuemax", String(MAX))
      handle.setAttribute("aria-valuenow", String(Math.round(handle.closest("th").getBoundingClientRect().width)))
    }
  }

  /* The natural layout, then the stored widths over it. Safe to run on a
     table in any state, which is what lets a reset, a swap and a morph share
     it. */
  const restore = (table) => {
    table.removeAttribute(RESIZED)
    table.style.width = ""
    for (const cell of headers(table)) cell.style.width = ""
    const widths = load(table)
    if (Object.keys(widths).length) freeze(table, widths)
    describe(table)
  }

  const set = (handle, width) => {
    const { header, table } = parts(handle)
    const widths = load(table)
    widths[column(header)] = clamp(width)
    freeze(table, widths)
    describe(table)
    save(table, widths)
  }

  const reset = (handle) => {
    const { header, table } = parts(handle)
    const widths = load(table)
    delete widths[column(header)]
    save(table, widths)
    restore(table)
  }

  const handleOf = (event) =>
    event.target instanceof Element && event.target.hasAttribute(HANDLE) ? event.target : null

  let drag = null

  document.addEventListener("pointerdown", (event) => {
    const handle = handleOf(event)
    if (!handle || event.button !== 0) return
    /* No text selection while dragging, and no focus lost to the cell. */
    event.preventDefault()
    handle.focus()
    const { header, table } = parts(handle)
    drag = {
      handle,
      table,
      column: column(header),
      widths: load(table),
      pointer: event.pointerId,
      startX: event.clientX,
      start: header.getBoundingClientRect().width,
      sign: direction(table),
      moved: false,
    }
    handle.setPointerCapture(event.pointerId)
    handle.setAttribute(DRAGGING, "")
  })

  document.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.pointer || event.clientX === drag.startX) return
    drag.moved = true
    drag.widths[drag.column] = clamp(drag.start + drag.sign * (event.clientX - drag.startX))
    freeze(drag.table, drag.widths)
    describe(drag.table)
  })

  /* Saved once, at the end. A click that never moved saves nothing, so the
     first half of a double-click does not freeze a table it is about to
     reset. */
  const end = (event) => {
    if (!drag || event.pointerId !== drag.pointer) return
    drag.handle.removeAttribute(DRAGGING)
    if (drag.moved) save(drag.table, drag.widths)
    drag = null
  }
  document.addEventListener("pointerup", end)
  document.addEventListener("pointercancel", end)
  document.addEventListener("lostpointercapture", end)

  document.addEventListener("keydown", (event) => {
    const handle = handleOf(event)
    if (!handle) return
    const { header, table } = parts(handle)
    const step = { ArrowLeft: -STEP, ArrowRight: STEP }[event.key]
    if (step) set(handle, header.getBoundingClientRect().width + direction(table) * step)
    else if (event.key === "Home") reset(handle)
    else return
    event.preventDefault()
  })

  document.addEventListener("dblclick", (event) => {
    const handle = handleOf(event)
    if (handle) reset(handle)
  })

  /* A table written into the page by something other than htmx has had no
     `restore`, so its handles get their value when they are first reached. */
  document.addEventListener("focusin", (event) => {
    const handle = handleOf(event)
    if (handle) describe(parts(handle).table)
  })

  /* A table that already carries its widths is skipped, so the many
     `htmx:load`s of one morph do not lay the same table out many times. */
  const restoreAll = () => {
    for (const table of document.querySelectorAll(`table[${TABLE}]:not([${RESIZED}])`)) restore(table)
  }

  document.documentElement.setAttribute("data-fjkit-resize-ready", "")
  document.addEventListener("htmx:load", restoreAll)
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", restoreAll)
  else restoreAll()
})()
