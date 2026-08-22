"""The style picker in the header.

It is the demo's own affordance — fjkit resolves one pack per process and the
server keeps linking that one. What these tests guard is the two things that
break silently in the browser: an option pointing at a stylesheet the package
does not serve, and the picker's script losing the `<link>` it rewrites.
"""

from __future__ import annotations

import re

import pytest
from app.main import STYLE_SHEETS

FULL_PAGES = ["/", "/tasks", "/jobs"]

#: What the picker's script reaches for. The map is emitted server-side, so a
#: pack that is not in it is a pack the browser will never be asked to load.
PICKER = re.compile(r"<select[^>]*data-style-picker[^>]*>(.*?)</select>", re.DOTALL)


@pytest.mark.parametrize("path", FULL_PAGES)
def test_every_full_page_offers_every_pack(client, path):
    match = PICKER.search(client.get(path).text)
    assert match, f"{path} has no style picker"
    assert re.findall(r'value="([^"]*)"', match.group(1)) == list(STYLE_SHEETS)


def test_the_pack_the_server_chose_is_the_one_preselected(client):
    """`selected` is what a browser with nothing in localStorage shows, so it
    has to name the pack the shell actually linked — otherwise the picker opens
    reporting a style the page is not wearing."""
    html = client.get("/").text
    picked = re.search(r'<option value="([^"]*)" selected>', PICKER.search(html).group(1)).group(1)
    # The shell's link carries `?v=<mtime>` (see `fjkit_static`), so the pack is
    # matched on the path. The picker's own map has no stamp — those URLs are
    # built by this app, not by the kit.
    assert f'href="{STYLE_SHEETS[picked]}?v=' in html


@pytest.mark.parametrize("pack", list(STYLE_SHEETS), ids=list(STYLE_SHEETS))
def test_every_offered_pack_is_actually_served(client, pack):
    """The picker swaps the page's only stylesheet. An option whose URL 404s
    does not degrade — it leaves the app unstyled."""
    response = client.get(STYLE_SHEETS[pack])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")


def test_the_kit_stylesheet_is_the_first_link_on_the_page(client):
    """The script rewrites `document.querySelector('link[rel="stylesheet"]')`.
    A page that grows a stylesheet of its own *above* the kit's would send the
    swap to that one instead, and nothing would look wrong until you switched."""
    first = re.search(r'<link rel="stylesheet" href="([^"]*)"', client.get("/").text).group(1)
    assert first.split("?")[0] in STYLE_SHEETS.values()


@pytest.mark.parametrize("path", ["/tasks/board", "/jobs"])
def test_swaps_do_not_carry_the_picker(htmx, path):
    """A partial that shipped the header would put a second picker on the page,
    and the script only ever wires the first."""
    assert not PICKER.search(htmx.get(path).text)
