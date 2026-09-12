"""Wire contracts the search page has and the panels page does not.

The five fragment envelopes both pages share are in `schemas/fragments.py`. What
is left here is the shape of a whole-page answer, and the listbox behind the
jump combobox — neither of which the panels page has, because a tab body is
fetched on its own and there is no combobox on it.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.fragments import FacetsResponse, MatchesResponse, RelatedResponse, StatsResponse


class OptionsResponse(BaseModel):
    """The combobox's listbox: option rows and nothing else.

    Not a `Fragment`. Every other partial on the search page carries a render
    stamp because the page's whole point is showing which regions an action
    reached; a listbox is inside one region and reached by its own request, so
    there is nothing to disambiguate.
    """

    #: `(value, label)` — the same shape `combobox(options=…)` takes, so the
    #: first paint and the swapped reply are built by the same macro call.
    options: list[tuple[str, str]]


class SearchResponse(MatchesResponse, StatsResponse, FacetsResponse, RelatedResponse):
    """One query's answer: the matches in band, and four regions out of band.

    The fields are the union of what the five partials read, because one handler
    renders all five. That is what `hx-swap-oob` is for, and what the
    event-driven half of this page is not.
    """
