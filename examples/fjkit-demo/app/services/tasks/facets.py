"""Counting the board: the three summaries a page shows above a list.

Each takes the rows it is to count. That is not ceremony — the board's counters
summarise every task while the table below them shows a filter, and the search
page's counters summarise the matches. A function that decided for itself which
rows it meant could only be right on one of those pages.
"""

from __future__ import annotations

from collections import Counter

from app.schemas.tasks import PRIORITY_VARIANT, BoardStats, Facet, Priority, Status, Task


def stats(tasks: list[Task]) -> BoardStats:
    """Count statuses over `tasks`."""
    return BoardStats(
        total=len(tasks),
        todo=sum(t.status is Status.TODO for t in tasks),
        doing=sum(t.status is Status.DOING for t in tasks),
        done=sum(t.status is Status.DONE for t in tasks),
    )


def owner_facets(tasks: list[Task]) -> list[Facet]:
    """Count matches per owner, alphabetical."""
    counts = Counter(t.owner for t in tasks)
    return [Facet(label=owner, count=n) for owner, n in sorted(counts.items())]


def priority_facets(tasks: list[Task]) -> list[Facet]:
    """Count matches per priority, highest first, omitting empty levels."""
    counts = Counter(t.priority for t in tasks)
    return [
        Facet(label=p.value.capitalize(), count=counts[p], variant=PRIORITY_VARIANT[p])
        for p in reversed(list(Priority))
        if counts[p]
    ]
