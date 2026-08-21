"""`FlashPlugin` — the message that has to outlive the response that raised it."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, Response
from fastapi.testclient import TestClient
from fjkit import FjkitConfig, FlashMessage, FlashPlugin, mount_fjkit, render
from jinja2 import DictLoader

TEMPLATES = {
    "page.html": "{% for m in flash %}[{{ m.category }}:{{ m.title }}:{{ m.text }}]{% endfor %}",
    "quiet.html": "no flash read here",
}


def make_app(**kwargs):
    flash = FlashPlugin(secret="test-secret", secure=False, **kwargs)
    router = APIRouter()

    @router.get("/page")
    @render("page.html")
    def page() -> dict[str, str]:
        return {}

    @router.get("/quiet")
    @render("quiet.html")
    def quiet() -> dict[str, str]:
        return {}

    @router.post("/raise")
    def raise_one(response: Response) -> Response:
        flash.add(response, "Saved", "Two rows changed.", category="success")
        response.status_code = 204
        return response

    app = FastAPI()
    templates = mount_fjkit(app, FjkitConfig(plugins=(flash,)))
    templates.env.loader = DictLoader(TEMPLATES)
    app.include_router(router)
    return flash, TestClient(app)


def test_a_message_survives_into_the_next_request():
    """The whole point: the response that sets it renders nothing."""
    _, client = make_app()

    client.post("/raise")

    assert client.get("/page").text == "[success:Saved:Two rows changed.]"


def test_it_is_shown_once_and_then_gone():
    """A reload must not replay it. That is what makes it a flash."""
    _, client = make_app()
    client.post("/raise")

    first = client.get("/page").text
    second = client.get("/page").text

    assert first == "[success:Saved:Two rows changed.]"
    assert second == ""


def test_a_page_that_never_rendered_it_does_not_consume_it():
    """A favicon, a stylesheet, an htmx poll — anything can arrive first.

    Clearing on any request that merely *carried* the cookie would let one of
    those eat the message before the page it belonged to was drawn.
    """
    _, client = make_app()
    client.post("/raise")

    assert client.get("/quiet").text == "no flash read here"
    assert client.get("/page").text == "[success:Saved:Two rows changed.]"


def test_a_message_raised_while_showing_one_is_not_swallowed():
    """The outgoing cookie is the next page's, not this page's leftovers."""
    flash, client = make_app()
    client.post("/raise")
    client.get("/page")  # consumes the first

    client.post("/raise")
    assert client.get("/page").text == "[success:Saved:Two rows changed.]"


def test_the_cookie_is_httponly_and_signed():
    flash, client = make_app()

    header = client.post("/raise").headers["set-cookie"]

    assert "HttpOnly" in header
    assert "." in client.cookies["fjkit_flash"], "body and signature"


def test_a_tampered_message_is_dropped():
    """An unsigned flash cookie is a way to make a site display any text an
    attacker likes — which is a phishing tool, not a message."""
    flash, client = make_app()
    client.post("/raise")

    body, _, signature = client.cookies["fjkit_flash"].partition(".")
    client.cookies.set("fjkit_flash", f"{body}x.{signature}")

    assert client.get("/page").text == ""


def test_a_cookie_signed_with_another_secret_is_dropped():
    flash, client = make_app()
    other = FlashPlugin(secret="different-secret", secure=False)

    forged = other._sign(b'[{"title":"Trust me","text":null,"category":"error"}]')
    client.cookies.set("fjkit_flash", forged)

    assert client.get("/page").text == ""


def test_several_messages_keep_their_order():
    flash, client = make_app()

    @flash_route(client)
    def _(response: Response) -> None:
        flash.set(
            response,
            [FlashMessage("First", category="info"), FlashMessage("Second", category="error")],
        )

    assert client.get("/page").text == "[info:First:None][error:Second:None]"


def flash_route(client):
    """Set a flash directly on a throwaway response and hand it to the client."""

    def decorate(fn):
        response = Response(status_code=204)
        fn(response)
        for cookie in response.headers.getlist("set-cookie"):
            name, _, rest = cookie.partition("=")
            client.cookies.set(name, rest.split(";")[0])
        return fn

    return decorate
