"""The stamp `fjkit eject` writes, and how a stale copy is found again later.

An ejected component is a copy: the loader finds the app's file first, so the
copy shadows the kit's own and no call site changes (CHARTER.md A5). The cost
is that the copy stops receiving upstream fixes — silently, which is the part
worth solving. A year later nobody remembers which version a file was ejected
from, or whether the kit has changed it since.

So the copy carries its provenance in a Jinja comment on the first line:

    {# fjkit:eject button 0.2.1 sha256:6b1f0c9a2d34 #}

`name` is what to re-eject, the version is when, and the digest is *the kit's
source at that moment*. The digest is what makes staleness detectable: compare
it against the installed kit's copy of the same component and an inequality
means upstream moved. Comparing versions instead would false-positive on every
release, since most releases touch no component the app happens to have ejected.

Not an error, ever. Ejecting is a supported escape hatch and diverging is what
it is for. `fjkit check` reports these as a note beside the violation list and
leaves the exit code alone.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from fjkit.config import TEMPLATE_DIR

#: The first line of an ejected file. `[^\S\n]` rather than `\s` so the line
#: cannot swallow the newline and match into the template body.
STAMP = re.compile(
    r"\{#[^\S\n]*fjkit:eject[^\S\n]+(?P<name>[\w-]+)[^\S\n]+"
    r"(?P<version>\S+)[^\S\n]+sha256:(?P<digest>[0-9a-f]+)"
)

#: Enough to identify a revision, short enough to read in a diff. Collisions
#: need 2^24 component revisions before they are worth thinking about.
DIGEST_LENGTH = 12


def digest(source: str) -> str:
    """The stamped fingerprint of a component's source.

    Newlines are normalised because the stamp travels through git, and a
    checkout with `core.autocrlf` on would otherwise report every component as
    changed.
    """
    return hashlib.sha256(source.replace("\r\n", "\n").encode("utf-8")).hexdigest()[:DIGEST_LENGTH]


def kit_source(name: str) -> str | None:
    """The kit's own version of a component, or None if it ships no such name."""
    path = TEMPLATE_DIR / "ui" / f"{name}.html"
    return path.read_text(encoding="utf-8") if path.exists() else None


def stamp_line(name: str, version: str, source: str) -> str:
    return f"{{# fjkit:eject {name} {version} sha256:{digest(source)} #}}\n"


@dataclass(frozen=True, slots=True)
class Ejected:
    """One ejected component found in an app's template directory."""

    path: Path
    name: str
    version: str
    digest: str
    #: The kit's digest for the same component now. None when the kit no longer
    #: ships that component at all — a rename or a removal.
    current: str | None

    @property
    def is_stale(self) -> bool:
        return self.current is not None and self.current != self.digest

    @property
    def is_orphaned(self) -> bool:
        return self.current is None

    def render(self, root: Path) -> str:
        rel = self.path.relative_to(root).as_posix()
        if self.is_orphaned:
            return f"  {rel}\n      ejected from fjkit {self.version}, which no longer ships a {self.name!r} component"
        return (
            f"  {rel}\n"
            f"      ejected from fjkit {self.version}; the kit's {self.name!r} has changed since\n"
            f"      re-eject into a scratch file and diff, or delete this copy to go back to the kit's"
        )


def find_ejected(template_dir: Path) -> list[Ejected]:
    """Every stamped copy under `template_dir`, in file order.

    Only the first line is read. A stamp anywhere else is not a stamp: `eject`
    writes it at the top, and scanning the whole file would match a stamp
    quoted inside documentation about this very feature.
    """
    found: list[Ejected] = []
    for path in sorted(template_dir.rglob("*.html")):
        with path.open(encoding="utf-8") as handle:
            first = handle.readline()
        match = STAMP.match(first.strip())
        if match is None:
            continue
        name = match["name"]
        source = kit_source(name)
        found.append(
            Ejected(
                path=path,
                name=name,
                version=match["version"],
                digest=match["digest"],
                current=digest(source) if source is not None else None,
            )
        )
    return found


def stale_ejects(template_dir: Path) -> list[Ejected]:
    """The ones worth telling the app author about."""
    return [e for e in find_ejected(template_dir) if e.is_stale or e.is_orphaned]
