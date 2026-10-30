"""`FjkitConfig.color_scheme`: who decides whether a page is dark.

`"system"` leaves it to the visitor, through the shell's pre-paint script and
the header's toggle. `"light"` and `"dark"` take the choice away, so neither the
script nor the toggle may reach the page, and a `theme` key a visitor saved
under `"system"` must have nothing left to read it.
"""

from __future__ import annotations

import pytest
from fjkit import FjkitConfig, build_environment

PAGE = """
{% extends "ui/shell.html" %}
{% block content %}<main-content/>{% endblock %}
"""

OWN_ACTIONS = """
{% extends "ui/shell.html" %}
{% block header_actions %}<own-actions/>{% endblock %}
"""

PREPAINT = """  <script>
    (() => {
      const saved = localStorage.getItem("theme");
      const dark = saved ? saved === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      document.documentElement.classList.toggle("dark", dark);
    })();
  </script>
"""

TOGGLE = 'aria-label="Toggle theme"'


def render(source: str, **config) -> str:
    env = build_environment(FjkitConfig(auto_reload=False, **config))
    return env.from_string(source).render(request=None)


def test_system_is_the_default():
    assert FjkitConfig().color_scheme == "system"


def test_system_renders_what_the_shell_always_rendered():
    html = render(PAGE, color_scheme="system")

    assert html == render(PAGE)
    assert '<html lang="en" class="h-full scroll-pt-16">' in html
    assert PREPAINT in html
    assert html.count(TOGGLE) == 1


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a_fixed_scheme_ships_nothing_that_reads_the_visitor(scheme: str):
    html = render(PAGE, color_scheme=scheme)

    assert "localStorage" not in html
    assert "prefers-color-scheme" not in html
    assert TOGGLE not in html


def test_light_never_marks_the_document_dark():
    html = render(PAGE, color_scheme="light")

    assert '<html lang="en" class="h-full scroll-pt-16">' in html
    assert "dark" not in html.split("<head>")[0]


def test_dark_is_rendered_on_the_document():
    html = render(PAGE, color_scheme="dark")

    assert '<html lang="en" class="h-full scroll-pt-16 dark">' in html


@pytest.mark.parametrize("scheme", ["system", "light", "dark"])
def test_header_actions_stays_the_apps_to_fill(scheme: str):
    html = render(OWN_ACTIONS, color_scheme=scheme)

    assert "<own-actions/>" in html
    assert TOGGLE not in html


@pytest.mark.parametrize(("scheme", "shown"), [("system", True), ("light", False), ("dark", False)])
def test_theme_toggle_renders_nothing_under_a_fixed_scheme(scheme: str, shown: bool):
    """An app that fills `header_actions` calls the macro bare; a fixed scheme
    must still leave no toggle that writes `html.dark` and `localStorage`."""
    source = """
    {% extends "ui/shell.html" %}
    {% from "ui/nav.html" import theme_toggle %}
    {% block header_actions %}<own-actions/>{{ theme_toggle() }}{% endblock %}
    """
    html = render(source, color_scheme=scheme)

    assert "<own-actions/>" in html
    assert (TOGGLE in html) is shown


@pytest.mark.parametrize("bad", ["auto", "Dark", "", None])
def test_an_unknown_scheme_fails_when_the_config_is_built(bad):
    with pytest.raises(ValueError, match="color_scheme"):
        FjkitConfig(color_scheme=bad)
