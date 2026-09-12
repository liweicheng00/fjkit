"""Wire contracts for the Records page, and the two maps the table needs.

`columns()` is the interesting one. A sortable header is a link, and the link
is a URL — which parameter carries the order, which direction clicking asks
for, what happens to the page number. None of that is a template's business and
none of it is the kit's: `ui/table.html` takes a `sort_url` it did not build,
so the answer lives here, once, where a test can read it.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, computed_field


class Stage(StrEnum):
    """Where a dataset is in its life."""

    DRAFT = "draft"
    INDEXED = "indexed"
    ARCHIVED = "archived"


#: Domain value -> badge variant. Not a hue: a rebrand must not make "archived"
#: read as "healthy".
STAGE_VARIANT: dict[Stage, str] = {
    Stage.DRAFT: "outline",
    Stage.INDEXED: "success",
    Stage.ARCHIVED: "secondary",
}


class Record(BaseModel):
    id: int
    name: str
    owner: str
    stage: Stage
    rows: int
    updated: date

    @computed_field  # type: ignore[prop-decorator]
    @property
    def stage_variant(self) -> str:
        return STAGE_VARIANT[self.stage]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def rows_label(self) -> str:
        """`1234567` as `1,234,567`. Formatting is not a template's job."""
        return f"{self.rows:,}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def updated_label(self) -> str:
        return self.updated.isoformat()


#: Sort key -> header label. The keys are also the whitelist: an `o=` naming
#: anything else is not a 422, it is a stranger's bookmark, and the service
#: falls back to the default order rather than refusing to draw the page.
SORT_LABELS: dict[str, str] = {
    "name": "Dataset",
    "owner": "Owner",
    "stage": "Stage",
    "rows": "Rows",
    "updated": "Updated",
}

#: The columns that read as numbers, so the cell can align and tabularise them.
NUMERIC_SORTS = frozenset({"rows"})

#: The order the page opens on: newest first.
DEFAULT_SORT = "-updated"

#: The page sizes the control offers, and the whitelist behind it. Same
#: treatment as an unknown sort key: a `per_page=` outside this list is a stale
#: link, not an attack and not a 422, so it falls back rather than refusing.
#: Whitelisting it also caps it — `?per_page=100000` is one query that renders
#: every row, and nothing about a bookmark should be able to ask for that.
PAGE_SIZES: tuple[int, ...] = (12, 25, 50, 100)

DEFAULT_PAGE_SIZE = PAGE_SIZES[0]


def parse_page_size(value: int | None) -> int:
    """Return the page size actually used for `value`."""
    return value if value in PAGE_SIZES else DEFAULT_PAGE_SIZE


def parse_sort(value: str | None) -> tuple[str, bool]:
    """Split `-updated` into `("updated", True)` — the key and whether it descends.

    An unknown key falls back to the default rather than raising: `o=` is part
    of a URL people share, and a 422 for a stale one loses the whole page over
    a detail nobody chose.
    """
    raw = value or DEFAULT_SORT
    key, descending = (raw[1:], True) if raw.startswith("-") else (raw, False)
    if key not in SORT_LABELS:
        fallback = DEFAULT_SORT
        return fallback.lstrip("-"), fallback.startswith("-")
    return key, descending


def _query(sort: str | None, per_page: int | None) -> str:
    """The two view settings as a query string, both spelled out.

    Every link on the page starts here. A view setting carried by only some of
    the links is lost as soon as somebody uses the others: sorting must not
    reset the page size, and paging must not reset the order.

    The page number is deliberately absent: `pagination()` appends it, and a
    sort link must not carry one at all.
    """
    key, descending = parse_sort(sort)
    return f"?o={'-' if descending else ''}{key}&per_page={parse_page_size(per_page)}"


def columns(base_url: str, sort: str | None, per_page: int | None = None) -> list[dict[str, object]]:
    """Build the table's column spec for the view currently shown.

    Clicking the sorted column reverses it; clicking any other one sorts by it
    ascending. That rule is the whole reason this function exists rather than a
    constant — the link a header carries depends on the order the page is in.

    No `page` in the URL: changing the order re-ranks every row, so the page
    number that was showing describes nothing afterwards. The page size stays,
    because it describes the view rather than a position in it.
    """
    key, descending = parse_sort(sort)
    size = parse_page_size(per_page)
    # The row number is not a sortable column and not the record's id. It
    # numbers the listing — position in the order currently shown — so sorting
    # by owner renumbers every row, which is what a reader of a numbered list
    # expects and what an id would get wrong. `select_cell` carries the id.
    spec: list[dict[str, object]] = [{"select": True}, {"label": "#", "width": "min", "align": "end"}]
    for name, label in SORT_LABELS.items():
        active = name == key
        spec.append(
            {
                "label": label,
                "align": "end" if name in NUMERIC_SORTS else None,
                "sort": ("desc" if descending else "asc") if active else None,
                "sort_url": f"{base_url}?o={'-' if active and not descending else ''}{name}&per_page={size}",
            }
        )
    return spec


def page_url(base_url: str, sort: str | None, per_page: int | None = None) -> str:
    """The list's address carrying the view but no page number.

    `pagination()` appends the page number itself, and appending it to a URL
    that already has one produces a link with two.
    """
    return base_url + _query(sort, per_page)


class RecordsResponse(BaseModel):
    """One page of the table, and everything the strip under it needs."""

    records: list[Record]
    columns: list[dict]
    page: int
    pages: int
    total: int
    per_page: int
    #: Rows before this page. The row numbers continue across pages from here,
    #: so page 3 of twelve-row pages starts at 25 rather than at 1.
    offset: int
    #: The page sizes the control offers.
    page_sizes: tuple[int, ...]
    #: The bare list address, with no query string at all — what `page_size()`
    #: needs, because a native GET submit throws the action's query away.
    base_url: str
    #: What `page_size(keep=…)` re-sends as hidden fields: the view settings
    #: that survive the change. Never the page number.
    keep: dict[str, str]
    #: The list's address with the order and size on it, for `pagination(url=…)`.
    page_url: str
    #: The same address with the page number back on it, so a bulk action
    #: returns the person to the rows they were looking at.
    action_url: str
