"""What the mapper yields, and the form model built from it."""

from __future__ import annotations

import datetime as dt

import pytest
from admin_fixture import Project, Status, Task, TaskAdmin
from fjkit_admin.introspect import inspect_model
from fjkit_admin.schema import build_form_model
from pydantic import ValidationError


def test_columns_carry_type_nullability_default_and_foreign_key():
    info = inspect_model(Task)
    assert info.pk.key == "id"
    assert info.columns["title"].kind == "text" and info.columns["title"].length == 120
    assert info.columns["notes"].kind == "textarea" and info.columns["notes"].nullable
    assert info.columns["status"].kind == "enum" and info.columns["status"].enum_class is Status
    assert info.columns["status"].has_default
    assert info.columns["due"].kind == "date" and info.columns["due"].nullable
    assert info.columns["created"].kind == "datetime" and info.columns["created"].has_default
    assert info.columns["done"].kind == "boolean"
    assert info.columns["project_id"].foreign_key and not info.columns["project_id"].nullable


def test_relationships_name_direction_and_local_key():
    info = inspect_model(Task)
    rel = info.relations["project"]
    assert rel.direction == "MANYTOONE" and rel.target is Project and rel.local_columns == ("project_id",)
    assert info.relation_for_column("project_id") is rel

    back = inspect_model(Project).relations["tasks"]
    assert back.direction == "ONETOMANY" and back.uselist


def test_column_info_reads_admin_hints():
    info = inspect_model(Project)
    assert info.columns["name"].label == "Project name"
    assert info.columns["name"].admin_info["help"] == "Shown in every task list."


def test_a_non_mapped_class_is_refused():
    with pytest.raises(TypeError, match="not a SQLAlchemy mapped class"):
        inspect_model(dict)


def test_form_model_follows_the_column_rules():
    from fjkit_admin import AdminPlugin

    view = AdminPlugin(lambda: None, views=(TaskAdmin,)).views["task"]
    fields = view.form_fields()
    model = build_form_model(view.info, fields, {k: view.widget_for(k) for k in fields}, "TaskForm")
    assert model.model_fields.keys() == view.form_model.model_fields.keys()

    assert set(model.model_fields) == {"title", "notes", "status", "due", "done", "project_id"}
    parsed = model.model_validate(
        {"title": " Trim me ", "notes": "", "status": "done", "due": "2026-09-04", "project_id": "2"}
    )
    assert parsed.title == "Trim me"
    assert parsed.notes is None
    assert parsed.status is Status.DONE
    assert parsed.due == dt.date(2026, 9, 4)
    assert parsed.done is False
    assert parsed.project_id == 2

    with pytest.raises(ValidationError) as failure:
        model.model_validate({"title": "x" * 121, "project_id": ""})
    fields_failed = {error["loc"][0] for error in failure.value.errors()}
    assert fields_failed == {"title", "project_id"}


def test_options_are_validated_at_class_creation():
    with pytest.raises(TypeError, match="not a column"):

        class Bad(TaskAdmin):
            key = "bad"
            list_display = ("title", "nope")

    with pytest.raises(TypeError, match="@action"):

        class BadAction(TaskAdmin):
            key = "bad2"
            actions = ("not_an_action",)

    with pytest.raises(TypeError, match="needs `model=`"):

        class NoModel(__import__("fjkit_admin").ModelAdmin):
            pass


def test_display_names_a_method_column():
    from admin_fixture import ProjectAdmin, make_app
    from fastapi.testclient import TestClient
    from fjkit_admin import display

    class Projects(ProjectAdmin):
        key = "project"
        list_display = ("name", "task_count", "plain")

        @display("Tasks")
        def task_count(self, project: Project) -> int:
            return len(project.tasks)

        def plain(self, project: Project) -> str:
            return "x"

    app, _, admin = make_app(Projects)
    view = admin.views["project"]
    assert view.field_label("task_count") == "Tasks"
    assert view.field_label("plain") == "Plain"
    html = TestClient(app).get("/admin/project").text
    assert ">Tasks<" in html and ">Plain<" in html
