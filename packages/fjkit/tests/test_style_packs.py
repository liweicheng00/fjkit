"""The style packs: eight builds, one selected, zero template changes.

Swapping a pack is a config value, not a rebuild and not an edit. These tests
pin both halves of that: the wheel carries all eight packs, and the shell links
the one asked for.
"""

from __future__ import annotations

import gzip

import pytest
from fastapi import FastAPI
from fjkit import FjkitConfig, build_environment, mount_fjkit
from fjkit.cli.build_css import GZIP_BUDGET, RAW_BUDGET, output_for
from fjkit.config import STATIC_DIR
from fjkit.vendored import DEFAULT_STYLE, STYLE_PACKS

SHELL_LINK = '{% extends "ui/shell.html" %}'


def test_every_pack_is_vendored():
    """A pack named in `StylePack` that upstream does not ship builds into an
    empty stylesheet rather than failing, so check the source is present."""
    vendored = STATIC_DIR / "vendor" / "basecoat" / "styles"
    for pack in STYLE_PACKS:
        assert (vendored / f"{pack}.css").exists(), pack
        assert (STATIC_DIR / "vendor" / "basecoat" / f"basecoat-{pack}.css").exists(), pack


@pytest.mark.parametrize("pack", STYLE_PACKS)
def test_every_pack_is_built_and_within_budget(pack: str):
    """CHARTER.md §7 is a per-page budget, and a page loads exactly one pack —
    so every pack has to clear it on its own, not on average."""
    built = output_for(pack)
    assert built.exists(), f"{built.name} missing — run: uv run fjkit build-css"

    raw = built.stat().st_size
    compressed = len(gzip.compress(built.read_bytes(), 9))
    assert compressed <= GZIP_BUDGET, f"{built.name}: {compressed / 1024:.1f} KB gzip"
    assert raw <= RAW_BUDGET, f"{built.name}: {raw:,} bytes raw"


@pytest.mark.parametrize("pack", STYLE_PACKS)
def test_shell_links_the_configured_pack(pack: str):
    env = build_environment(FjkitConfig(style=pack, auto_reload=False))
    html = env.get_template("ui/shell.html").render(request=None)

    # `?v=<mtime>` follows the path: `fjkit_static` stamps every asset so a
    # browser cannot pair a cached stylesheet with newer markup.
    assert f'href="/_fjkit/dist/fjkit-{pack}.css?v=' in html
    # Exactly one stylesheet from the kit. Two would mean two full downloads and
    # one of them silently losing the cascade.
    assert html.count("/_fjkit/dist/") == 1


def test_default_is_upstreams_default():
    """`"auto"` lands where fjkit has always landed. An app that never heard of
    style packs must not change appearance because this feature exists."""
    assert FjkitConfig().style == "auto"
    assert build_environment(FjkitConfig()).globals["fjkit_style"] == DEFAULT_STYLE


def test_packs_differ_only_in_declarations():
    """Why a swap needs no template edit: two packs emit the same class names,
    so a template written against one is written against all eight. A failure
    here implicates `fjkit check` and every template, and the swap has stopped
    being free."""
    from fjkit.cli.vocabulary import _CLASS_SELECTOR

    def classes(pack: str) -> set[str]:
        text = output_for(pack).read_text(encoding="utf-8").replace("\\", "")
        return set(_CLASS_SELECTOR.findall(text))

    baseline = classes(DEFAULT_STYLE)
    for pack in STYLE_PACKS:
        if pack == DEFAULT_STYLE:
            continue
        assert classes(pack) == baseline, f"{pack} emits a different class set than {DEFAULT_STYLE}"


def test_mount_rejects_a_pack_it_cannot_serve():
    with pytest.raises(RuntimeError, match="style='nope'"):
        mount_fjkit(FastAPI(), FjkitConfig(style="nope"))  # type: ignore[arg-type]
