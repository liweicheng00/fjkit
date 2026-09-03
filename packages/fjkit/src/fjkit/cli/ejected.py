"""The stamp `fjkit eject` writes, and how a stale copy is found again later.

An ejected component is a copy: the loader finds the app's file first, so the
copy shadows the kit's and no call site changes (CHARTER.md A5). The cost is
that the copy stops receiving upstream fixes, silently. A year later nobody
remembers which version a file was ejected from, or whether the kit has changed
it since.

So the copy carries its provenance in a Jinja comment on the first line, in one
of two shapes:

    {# fjkit:eject button 0.2.1 sha256:6b1f0c9a2d34 #}
    {# fjkit:eject data 0.2.1 macros:badge=1f0c9a2d3456 #}

The first is a copy of the whole file; the second owns the macros it names and
re-exports the rest from the kit (see `fjkit.cli.eject`). `name` is the
component, the version records when, and each digest is the kit's source at that
moment. The digest makes staleness detectable: compare it against the installed
kit, and a difference means upstream moved. Comparing versions instead would
report a false positive on every release, since most releases touch no component
the app has ejected.

Per macro, not per file, which is the point of the second shape. A file-wide
digest marks a copy of `badge` stale because the kit changed `avatar` — noise
that trains the reader to ignore the alert. The report can instead name `badge`,
a macro the app owns.

A macro's digest covers its `{% macro %}` block and not the signature comment
above it: rewording a paragraph should not report the copy as behind.

Never an error. Ejecting is a supported escape hatch and diverging is its
purpose. `fjkit check` reports these as a note beside the violation list and
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
    r"\{#[^\S\n]*fjkit:eject[^\S\n]+(?P<name>[\w-]+)[^\S\n]+(?P<version>\S+)[^\S\n]+"
    r"(?:sha256:(?P<digest>[0-9a-f]+)"
    r"|macros:(?P<macros>[\w-]+=[0-9a-f]+(?:,[\w-]+=[0-9a-f]+)*))"
)

#: Long enough to identify a revision, short enough to read in a diff.
#: Collisions need 2^24 component revisions before they matter.
DIGEST_LENGTH = 12


def digest(source: str) -> str:
    """Fingerprint a component's source for the stamp.

    Newlines are normalised because the stamp travels through git: without it, a
    checkout with `core.autocrlf` on reports every component as changed.
    """
    return hashlib.sha256(source.replace("\r\n", "\n").encode("utf-8")).hexdigest()[:DIGEST_LENGTH]


def kit_source(name: str) -> str | None:
    """Read the kit's own version of a component, or None if it ships no such
    name."""
    path = TEMPLATE_DIR / "ui" / f"{name}.html"
    return path.read_text(encoding="utf-8") if path.exists() else None


def stamp_line(name: str, version: str, source: str) -> str:
    """Build the stamp for a copy of the whole file."""
    return f"{{# fjkit:eject {name} {version} sha256:{digest(source)} #}}\n"


def macro_stamp(name: str, version: str, digests: dict[str, str]) -> str:
    """Build the stamp for an override that owns some of a component's macros."""
    listing = ",".join(f"{macro}={value}" for macro, value in digests.items())
    return f"{{# fjkit:eject {name} {version} macros:{listing} #}}\n"


@dataclass(frozen=True, slots=True)
class Ejected:
    """One ejected component found in an app's template directory."""

    path: Path
    name: str
    version: str
    #: What this copy owns: macro name → the kit's digest when it was taken. A
    #: whole-file copy holds one pseudo-entry named after the component, because
    #: it took the imports and the lookup tables as well as the macros.
    owned: tuple[tuple[str, str], ...]
    #: The same names' digests in the installed kit now. A name missing here is
    #: one the kit no longer ships.
    current: tuple[tuple[str, str], ...]
    #: False when the copy owns named macros rather than the file.
    whole_file: bool

    @property
    def digest(self) -> str:
        """The stamped digest of a whole-file copy."""
        return self.owned[0][1]

    @property
    def moved(self) -> tuple[str, ...]:
        """The owned macros the kit has changed since the eject."""
        now = dict(self.current)
        return tuple(name for name, was in self.owned if name in now and now[name] != was)

    @property
    def missing(self) -> tuple[str, ...]:
        """The owned macros the kit no longer ships."""
        now = dict(self.current)
        return tuple(name for name, _ in self.owned if name not in now)

    @property
    def is_stale(self) -> bool:
        return bool(self.moved)

    @property
    def is_orphaned(self) -> bool:
        return bool(self.missing)

    def render(self, root: Path) -> str:
        rel = self.path.relative_to(root).as_posix()
        if self.whole_file:
            if self.is_orphaned:
                return (
                    f"  {rel}\n      ejected from fjkit {self.version}, which no longer ships "
                    f"a {self.name!r} component"
                )
            return (
                f"  {rel}\n"
                f"      ejected from fjkit {self.version}; the kit's {self.name!r} has changed since\n"
                f"      re-eject into a scratch file and diff, or delete this copy to go back to the kit's"
            )
        lines = [f"  {rel}"]
        if self.missing:
            lines.append(
                f"      ejected from fjkit {self.version}, which no longer ships "
                f"{_names(self.missing)} in {self.name!r}"
            )
        if self.moved:
            lines.append(
                f"      ejected from fjkit {self.version}; the kit has since changed "
                f"{_names(self.moved)}, and you own a copy\n"
                f"      re-eject into a scratch directory and diff that macro, or delete your copy of it"
            )
        return "\n".join(lines)


def _names(names: tuple[str, ...]) -> str:
    return ", ".join(repr(n) for n in names)


def find_ejected(template_dir: Path) -> list[Ejected]:
    """Collect every stamped copy under `template_dir`, in file order.

    Only the first line is read. A stamp anywhere else is not a stamp: `eject`
    writes it at the top, and scanning the whole file would match a stamp quoted
    inside documentation about this feature.
    """
    from fjkit.cli.eject import kit_macro_digests

    found: list[Ejected] = []
    for path in sorted(template_dir.rglob("*.html")):
        with path.open(encoding="utf-8") as handle:
            first = handle.readline()
        match = STAMP.match(first.strip())
        if match is None:
            continue
        name = match["name"]

        if match["macros"]:
            owned = tuple(tuple(entry.split("=", 1)) for entry in match["macros"].split(","))
            current = tuple(sorted(kit_macro_digests(name, [m for m, _ in owned]).items()))
            whole_file = False
        else:
            source = kit_source(name)
            owned = ((name, match["digest"]),)
            current = () if source is None else ((name, digest(source)),)
            whole_file = True

        found.append(
            Ejected(
                path=path,
                name=name,
                version=match["version"],
                owned=owned,  # type: ignore[arg-type]
                current=current,
                whole_file=whole_file,
            )
        )
    return found


def stale_ejects(template_dir: Path) -> list[Ejected]:
    """The ejects worth telling the app author about."""
    return [e for e in find_ejected(template_dir) if e.is_stale or e.is_orphaned]
