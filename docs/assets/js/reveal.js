/*
  Switches a password field between hidden and readable.

  The control itself is markup: `input_group_field(revealable=true)` writes the
  button, its `aria-pressed` and the `aria-controls` that names the input. This
  file is only the four lines that flip `input.type`. It lives in the kit rather
  than in every app because the two things that make it correct are not things a
  caller can be expected to derive.

  It is delegated from `document`, not bound to the button. The form holding a
  password field is the form most likely to be replaced: a rejected sign-in swaps
  the panel out, and a fresh button arrives with no listener on it. A page that
  bound one at DOMContentLoaded gets a reveal that works exactly once and then
  fails silently — no console error, and the button still looks like a button.

  The input is found through `aria-controls`, never by a convention. The macro
  decides the field's id (`f-<name>`, or whatever `id=` overrode it), so the
  attribute a screen reader already needs is also the only honest way to find the
  input. Nothing here knows the `f-` prefix.

  State is read from the DOM — `input.type` — and never cached. After a swap the
  markup is authoritative, and a remembered boolean would describe the element
  that used to be there.

  Loaded per page by `reveal_scripts()`, never from the shell (CHARTER §7).
*/
(() => {
  const BUTTON = "[data-fjkit-reveal]"

  document.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest(BUTTON) : null
    if (!button) return

    /* `aria-controls` may name an element a swap has taken away, or one an app
       pointed somewhere else. Doing nothing is right in both cases: this is a
       progressive enhancement on a field that works without it. */
    const input = document.getElementById(button.getAttribute("aria-controls") || "")
    if (!(input instanceof HTMLInputElement)) return

    const revealed = input.type === "text"
    input.type = revealed ? "password" : "text"
    button.setAttribute("aria-pressed", String(!revealed))

    /* The label changes along with `aria-pressed`, because the two say the same
       thing to different readers and a button reading "Show" over a visible
       password is wrong for everyone. Both strings come from the macro, so a
       translated page translates them. */
    const next = revealed ? button.dataset.show : button.dataset.hide
    if (next) button.textContent = next
  })
})()
