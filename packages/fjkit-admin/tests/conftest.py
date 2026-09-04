"""Fixtures live in `admin_fixture.py`, a module the tests import by name.

A module called `conftest` exists in every test directory of this workspace,
so a test that imported `conftest` would get whichever loaded first.
"""

from admin_fixture import client, db, stack  # noqa: F401
