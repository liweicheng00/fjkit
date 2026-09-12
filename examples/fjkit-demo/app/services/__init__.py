"""Business logic, one package per feature.

Nothing here imports `Request` or `Response`, names a template, or knows a status
code. A service is handed what it needs — the rows, the settings, the session —
and hands back a value the router turns into a reply.

Each package's `__init__` is its public face. Other layers import from there, not
from the modules inside it.
"""
