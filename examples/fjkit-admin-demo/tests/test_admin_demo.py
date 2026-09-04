"""The admin demo starts, seeds itself and serves every page inside its own shell."""

from __future__ import annotations

from pathlib import Path

import pytest
from admin_demo import main
from fastapi.testclient import TestClient
from fjkit.cli.check import assert_templates_clean


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'demo.sqlite'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(engine, expire_on_commit=False))
    with TestClient(main.create_app()) as client:
        yield client


def test_home_redirects_into_the_admin(client: TestClient):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/admin"


def test_the_index_and_both_lists_render_inside_the_demo_shell(client: TestClient):
    index = client.get("/admin")
    assert index.status_code == 200
    assert "14 tasks" in index.text and "2 projects" in index.text
    assert "fjkit-admin demo" in index.text  # the app's base.html, through base_template

    tasks = client.get("/admin/task?f_status=done")
    assert tasks.status_code == 200
    assert "Back to the board" in tasks.text

    projects = client.get("/admin/project")
    assert projects.status_code == 200
    assert ">Tasks<" in projects.text  # the method column, labelled by short_description


def test_the_change_form_opens_for_a_seeded_row(client: TestClient):
    response = client.get("/admin/task/1")
    assert response.status_code == 200
    assert 'value="Ship the sortable table"' in response.text


def test_the_demo_templates_stay_inside_the_vocabulary():
    assert_templates_clean(Path(main.__file__).parent / "templates")
