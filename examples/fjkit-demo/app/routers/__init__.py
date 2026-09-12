"""Routes, one module per resource, all included by `main`.

A router declares paths, reads `Depends`, picks a template and maps a failure to
a status code. It computes nothing: the rows come from `app.services`, and the
shape it answers in comes from `app.schemas`.

No prefix is declared here or in `main`. These are pages, and a page's address is
part of what people keep — `/tasks`, not `/api/v1/tasks`.
"""
