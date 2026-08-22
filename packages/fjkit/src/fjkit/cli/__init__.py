"""The `fjkit` command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fjkit.config import TEMPLATE_DIR
from fjkit.vendored import STYLE_PACKS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fjkit", description="Server-rendered UI kit for FastAPI")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="fail if a template steps outside the fjkit vocabulary")
    check.add_argument(
        "template_dir",
        nargs="?",
        default="app/templates",
        type=Path,
        help="your app's template directory (default: app/templates)",
    )

    build = sub.add_parser("build-css", help="compile fjkit's stylesheets (fjkit development only)")
    build.add_argument("--watch", action="store_true", help="rebuild on change")
    build.add_argument(
        "--style",
        choices=STYLE_PACKS,
        help="build only this style pack (default: all eight)",
    )

    eject = sub.add_parser("eject", help="copy a component into your app so you can edit it")
    eject.add_argument("name", help="component name, e.g. button")
    eject.add_argument(
        "--into",
        default="app/templates",
        type=Path,
        help="your app's template directory (default: app/templates)",
    )

    args = parser.parse_args(argv)

    if args.command == "check":
        from fjkit.cli.check import main as check_main

        return check_main(args.template_dir)

    if args.command == "build-css":
        from fjkit.cli.build_css import main as build_main

        return build_main(watch=args.watch, style=args.style)

    if args.command == "eject":
        return _eject(args.name, args.into)

    return 2


def _eject(name: str, into: Path) -> int:
    """Copy one component template into the app, where it shadows the kit's.

    The loader searches the app's directory first (CHARTER.md A5), so the copy
    takes effect with no import changes at any call site. The trade is that the
    copy stops receiving upstream fixes — which is why this is an escape hatch
    and not the recommended path.

    The copy is stamped with where it came from, so `fjkit check` can say later
    that the kit's version has moved on. See `fjkit.cli.ejected`.
    """
    from fjkit.cli.ejected import stamp_line

    source = TEMPLATE_DIR / "ui" / f"{name}.html"
    if not source.exists():
        available = sorted(p.stem for p in (TEMPLATE_DIR / "ui").glob("*.html"))
        print(f"fjkit eject: no component named {name!r}.\nAvailable: {', '.join(available)}", file=sys.stderr)
        return 1

    target = into / "ui" / f"{name}.html"
    if target.exists():
        print(f"fjkit eject: {target} already exists — remove it first to re-eject", file=sys.stderr)
        return 1

    # Read and write rather than copyfile: the stamp has to go in front of the
    # source, and a copy-then-prepend would leave an unstamped file behind if
    # the second write failed.
    text = source.read_text(encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(stamp_line(name, _version(), text) + text, encoding="utf-8")
    print(
        f"copied to {target}\n"
        f"It now shadows fjkit's version — no import changes needed.\n"
        f"Note: this copy no longer receives upstream fixes. It is stamped with the\n"
        f"version it came from, and `fjkit check` will say so when the kit's changes."
    )
    return 0


def _version() -> str:
    """The installed fjkit version, for the eject stamp.

    Read from the installed distribution rather than a `__version__` constant,
    which is the single source hatchling already builds the wheel from. Running
    from a source tree with nothing installed is not an error worth failing an
    eject over — the digest is what detects staleness, the version is a
    human-readable note beside it.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("fjkit")
    except PackageNotFoundError:  # pragma: no cover - only outside an install
        return "unknown"
