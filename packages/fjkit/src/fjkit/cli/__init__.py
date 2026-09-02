"""The `fjkit` command."""

from __future__ import annotations

import argparse
from pathlib import Path

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

    eject = sub.add_parser(
        "eject",
        help="take one macro (or a whole component) into your app so you can edit it",
        description=(
            "Write an override into your template directory. Name a macro (`badge`) to own just "
            "that one — the rest of its file is re-exported from the kit and keeps receiving "
            "upstream fixes. Name a component file (`data`) to take all of it. Where two "
            "components define the same macro, say which: `data.badge`."
        ),
    )
    eject.add_argument("name", help="a macro (badge), a component file (data), or both (data.badge)")
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
        from fjkit.cli.eject import main as eject_main

        return eject_main(args.name, args.into)

    return 2
