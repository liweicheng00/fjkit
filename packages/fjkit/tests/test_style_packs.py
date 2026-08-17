"""The style packs: eight builds, one selected, zero template changes.

The promise this file guards is narrow and load-bearing — swapping a pack is a
config value, not a rebuild and not an edit. Each test pins one half of that:
the wheel really carries all eight, and the shell really links the one asked
for.
"""

from __future__ import annotations

import gzip
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fjkit import FjkitConfig, build_environment, mount_ui, styles
from fjkit.cli.build_css import GZIP_BUDGET, RAW_BUDGET, output_for
from fjkit.config import STATIC_DIR
from fjkit.vendored import DEFAULT_STYLE, STYLE_PACKS

REPO = Path(__file__).resolve().parents[3]

SHELL_LINK = '{% extends "ui/shell.html" %}'


def test_every_pack_is_vendored():
    """A pack named in `StylePack` that upstream does not ship would build into
    an empty stylesheet rather than fail, so check the source is there."""
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

    assert f'href="/_fjkit/dist/fjkit-{pack}.css"' in html
    # Exactly one stylesheet from the kit. Two would mean two full downloads
    # and one of them silently losing the cascade.
    assert html.count("/_fjkit/dist/") == 1


def test_default_is_upstreams_default():
    """`"auto"` with no marker installed has to land where fjkit has always
    landed. An app that never heard of style packs must not change appearance
    because this feature exists."""
    assert FjkitConfig().style == "auto"
    assert build_environment(FjkitConfig()).globals["fjkit_style"] == DEFAULT_STYLE


# --- install-time selection: uv add "fjkit[nova]" ---------------------------


def _markers(monkeypatch, *names: str) -> None:
    """Stand in for installed marker distributions.

    Patched at the seam rather than by installing packages, so the test is
    honest about what it covers: the resolution rule, not uv. That the marker
    distributions themselves are well-formed is what
    `test_marker_packages_declare_their_entry_point` checks.
    """
    eps = [SimpleNamespace(name=name) for name in names]
    monkeypatch.setattr(styles, "entry_points", lambda group: eps if group == styles.ENTRY_POINT_GROUP else [])


@pytest.mark.parametrize("pack", STYLE_PACKS)
def test_an_installed_marker_selects_its_pack(monkeypatch, pack: str):
    _markers(monkeypatch, pack)
    assert styles.resolve_style("auto") == pack
    assert build_environment(FjkitConfig()).globals["fjkit_style"] == pack


def test_config_beats_the_marker(monkeypatch):
    """Saying it in code is someone saying it on purpose; a marker is what the
    environment happened to be installed with."""
    _markers(monkeypatch, "nova")
    assert styles.resolve_style("sera") == "sera"


def test_two_markers_is_an_error_not_a_guess(monkeypatch):
    _markers(monkeypatch, "nova", "sera")
    with pytest.raises(RuntimeError, match="cannot choose between them"):
        styles.resolve_style("auto")


def test_a_stale_marker_does_not_stop_the_app(monkeypatch):
    """An uninstall can leave metadata behind. A name fjkit does not know is
    not a pack it could serve anyway, so it is ignored rather than fatal."""
    _markers(monkeypatch, "nova", "some-removed-pack")
    assert styles.resolve_style("auto") == "nova"


@pytest.mark.parametrize("pack", STYLE_PACKS)
def test_marker_packages_declare_their_entry_point(pack: str):
    """Every pack has a marker, and it announces the name fjkit looks up.

    A typo here would only show up as `uv add "fjkit[nova]"` silently doing
    nothing, which is the failure mode hardest to notice.
    """
    root = REPO / "packages" / f"fjkit-style-{pack}"
    manifest = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert manifest["project"]["name"] == f"fjkit-style-{pack}"
    assert manifest["project"]["entry-points"][styles.ENTRY_POINT_GROUP] == {pack: f"fjkit_style_{pack}"}
    # No CSS, and no dependency back on fjkit — the wheel already has the
    # stylesheets, and fjkit's own extra depends on this package.
    assert manifest["project"]["dependencies"] == []
    assert not list(root.rglob("*.css"))


def test_fjkit_offers_an_extra_per_pack():
    manifest = tomllib.loads((REPO / "packages" / "fjkit" / "pyproject.toml").read_text(encoding="utf-8"))
    extras = manifest["project"]["optional-dependencies"]

    assert set(extras) == set(STYLE_PACKS)
    for pack in STYLE_PACKS:
        assert extras[pack] == [f"fjkit-style-{pack}>=0.1"]


def test_packs_differ_only_in_declarations():
    """The reason a swap needs no template edit: two packs emit the same class
    names, so a template written against one is already written against all
    eight. If this ever fails, `fjkit check` and every template are implicated
    and the swap has stopped being free."""
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
        mount_ui(FastAPI(), FjkitConfig(style="nope"))  # type: ignore[arg-type]
