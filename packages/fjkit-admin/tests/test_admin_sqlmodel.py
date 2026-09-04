"""A SQLModel table class registers like any mapped class, and its validators run on submit."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fjkit import FjkitConfig, mount_fjkit
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sqlmodel = pytest.importorskip("sqlmodel")

from fjkit_admin import AdminPlugin, ModelAdmin  # noqa: E402
from fjkit_admin.schema import is_sqlmodel_table  # noqa: E402
from pydantic import field_validator  # noqa: E402
from sqlmodel import Field, SQLModel  # noqa: E402

HX = {"HX-Request": "true"}


class Hero(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=50)
    age: int | None = None

    @field_validator("name")
    @classmethod
    def no_villains(cls, value: str) -> str:
        if "villain" in value.lower():
            raise ValueError("a hero cannot be a villain")
        return value


class HeroAdmin(ModelAdmin, model=Hero):
    search_fields = ("name",)


@pytest.fixture
def client() -> TestClient:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        session.add(Hero(name="Deadpond", age=48))
        session.commit()
    app = FastAPI()
    mount_fjkit(app, FjkitConfig(plugins=(AdminPlugin(factory, views=(HeroAdmin,)),)))
    return TestClient(app)


def test_a_table_model_is_recognised_and_introspected():
    assert is_sqlmodel_table(Hero)
    assert set(HeroAdmin.info.columns) == {"id", "name", "age"}
    assert HeroAdmin.info.columns["name"].length == 50


def test_list_and_create_work_unchanged(client: TestClient):
    assert "Deadpond" in client.get("/admin/hero").text
    response = client.post("/admin/hero", json={"name": "Rusty-Man", "age": ""}, headers=HX)
    assert response.status_code == 200
    assert "Rusty-Man" in response.text


def test_the_classs_own_validator_runs_on_submit(client: TestClient):
    response = client.post("/admin/hero", json={"name": "Villain X", "age": "3"}, headers=HX)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["loc"] == ["body", "name"]
    assert "villain" in detail[0]["msg"]
