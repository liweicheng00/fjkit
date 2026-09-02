"""The two events the search page broadcasts.

The response models live in `features/tasks/schemas.py` with the rest of the task
wire contracts. What belongs here is what is specific to this page: the names on
the wire between a route's `hx_trigger` and a fragment's `hx-trigger`.

They are separate events because their audiences are. Picking a row concerns the
panels that describe one task; changing its status concerns anything that counts.
A fragment subscribes to whichever it has a reason to hear — the facets hear
neither, because advancing a task changes no owner and no priority.
"""

from __future__ import annotations

#: Raised by `search_select`, heard by the detail and siblings panels.
SELECTED_EVENT = "task-selected"

#: Raised by `search_advance`, heard by everything that counts or shows a status.
CHANGED_EVENT = "task-changed"

#: The key both details carry the id under, and the query parameter every
#: fragment endpoint reads. `hx-vals` turns one into the other.
SELECTED_KEY = "task_id"
