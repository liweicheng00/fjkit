from __future__ import annotations

import pytest
from fjkit import FjkitConfig, build_environment
from jinja2 import Environment


@pytest.fixture(scope="session")
def env() -> Environment:
    """The kit's Environment with no app templates layered on top."""
    return build_environment(FjkitConfig(auto_reload=False))


@pytest.fixture
def render(env: Environment):
    """Render a snippet against the kit's macros.

    Most component tests are 'call the macro, assert on the markup', so the
    fixture takes the source rather than a file:

        html = render('{% from "ui/button.html" import button %}{{ button("Go") }}')
    """

    def _render(source: str, **context) -> str:
        return env.from_string(source).render(**context)

    return _render
