"""One question, one document — enforced on the files that route a reader.

An agent arriving in this repository reads whichever entry file its own harness
looks for, and there is more than one convention: `AGENTS.md`, `CLAUDE.md`, a
skill. When each one carries its own routing table, the tables drift and the
agent follows whichever it happened to open. `AGENTS.md` and `CLAUDE.md` are now
one file under two names, and the routing table lives there alone.

`.claude/skills/fjkit/SKILL.md` keeps a table of its own on purpose. It answers
a different question — which *source file* decides a thing, not which
*document* — so these tests look for the document map's header row, not for
tables in general.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

#: The header row of the authority map in `AGENTS.md`. Matching the header
#: rather than the rows is deliberate: a second copy is always pasted whole.
MAP_HEADER = "| Question | Authority |"

#: `docs/` is a build artefact (`AGENTS.md`), and the two Markdown files still
#: published from it are evaluations rather than routing documents. `.venv` and
#: `goal/` are not part of the repository.
SKIPPED = {".git", ".venv", "docs", "goal", "node_modules", "__pycache__"}


def _markdown_files() -> list[Path]:
    """Every Markdown file in the repository, symlinks excluded.

    `CLAUDE.md` is a symlink to `AGENTS.md`; following it would report the one
    table twice and the test would fail on the fix rather than on the problem.
    """
    return sorted(
        path
        for path in REPO.rglob("*.md")
        if not path.is_symlink() and not SKIPPED & set(path.relative_to(REPO).parts)
    )


def test_claude_md_is_agents_md():
    """Two names for one file, so no diff can separate them.

    A Windows checkout without symlink support materialises the link as a text
    file holding the target's name, so identical content counts as well: what
    this forbids is two files with two different contents.
    """
    agents = REPO / "AGENTS.md"
    claude = REPO / "CLAUDE.md"

    assert agents.exists(), "AGENTS.md is the agent entry point and belongs at the repository root"
    assert claude.exists(), "CLAUDE.md should stay, as a symlink: Claude Code looks for that name"

    same_file = claude.is_symlink() and claude.resolve() == agents.resolve()
    assert same_file or claude.read_text(encoding="utf-8") == agents.read_text(encoding="utf-8"), (
        "CLAUDE.md and AGENTS.md have diverged. Make CLAUDE.md a symlink: ln -sf AGENTS.md CLAUDE.md"
    )


def test_the_authority_map_has_one_home():
    """`## Which document decides what` exists once.

    It was two tables — one in `CLAUDE.md`, one in the skill — that overlapped,
    disagreed, and were both reachable only by an agent that opened the right
    file. A new question gets a row in `AGENTS.md`, not a new table.
    """
    homes = [path for path in _markdown_files() if MAP_HEADER in path.read_text(encoding="utf-8")]

    assert [p.relative_to(REPO).as_posix() for p in homes] == ["AGENTS.md"], (
        "the authority map should exist only in AGENTS.md, and was found in: "
        + ", ".join(p.relative_to(REPO).as_posix() for p in homes)
    )
