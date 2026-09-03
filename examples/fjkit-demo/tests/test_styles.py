"""Tests for the style picker in the header."""

from __future__ import annotations

import re

import pytest
from app.main import STYLE_SHEETS

FULL_PAGES = ["/", "/tasks", "/jobs"]

#: Matches the picker's `<select>` and captures its options.
PICKER = re.compile(r"<select[^>]*data-style-picker[^>]*>(.*?)</select>", re.DOTALL)


@pytest.mark.parametrize("path", FULL_PAGES)
def test_every_full_page_offers_every_pack(client, path):
    match = PICKER.search(client.get(path).text)
    assert match, f"{path} has no style picker"
    assert re.findall(r'value="([^"]*)"', match.group(1)) == list(STYLE_SHEETS)


def test_the_pack_the_server_chose_is_the_one_preselected(client):
    """The `selected` option names the stylesheet the shell links."""
    html = client.get("/").text
    picked = re.search(r'<option value="([^"]*)" selected>', PICKER.search(html).group(1)).group(1)
    # The shell's link carries a `?v=` stamp; the picker's URLs do not.
    assert f'href="{STYLE_SHEETS[picked]}?v=' in html


@pytest.mark.parametrize("pack", list(STYLE_SHEETS), ids=list(STYLE_SHEETS))
def test_every_offered_pack_is_actually_served(client, pack):
    """An option pointing at a 404 loses every style on the page, and the browser reports nothing."""
    response = client.get(STYLE_SHEETS[pack])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")


def test_the_kit_stylesheet_is_the_first_link_on_the_page(client):
    first = re.search(r'<link rel="stylesheet" href="([^"]*)"', client.get("/").text).group(1)
    assert first.split("?")[0] in STYLE_SHEETS.values()


@pytest.mark.parametrize("path", ["/tasks/board", "/jobs"])
def test_swaps_do_not_carry_the_picker(htmx, path):
    """The picker belongs to the shell; a swap that carried it would put a second one on the page."""
    assert not PICKER.search(htmx.get(path).text)
