"""An API reference and console for a fjkit app — Swagger UI's job, done here.

    from fjkit import FjkitConfig, mount_fjkit
    from fjkit.apidocs import ApiDocsPlugin
    from fjkit.auth import AuthPlugin

    auth = AuthPlugin(secret=…, source=MyOIDCSource(), trusted_origins=[…])
    app = FastAPI(docs_url=None, redoc_url=None)
    mount_fjkit(app, FjkitConfig(template_dir=…, plugins=(auth, ApiDocsPlugin())))

That is the whole setup: the page appears at `/api-docs`, built from the same
`app.openapi()` document Swagger reads, and its sign-in panel is already wired
to `auth` — the plugin finds it in the same `plugins` tuple.

Two things it does that Swagger UI cannot, both for the same reason:

* **Sign-in is your code.** `AuthFlow` is a Python object, so "log in" can be
  whatever your app means by it. `SessionFlow` runs `AuthPlugin.issue`, which
  runs your `TokenSource`; OpenAPI has no way to describe that and Swagger's
  Authorize dialog has no room for it.
* **Calls carry a credential JavaScript cannot touch.** The console replays the
  request through the app in-process, forwarding the caller's HttpOnly session
  cookie. Token refresh, revocation and CSRF are handled by the middleware the
  call passes through, not reimplemented in the page.

The rest is ordinary fjkit: server-rendered macros, htmx for the swaps, no
build step, and every template shadowable by dropping a file of the same name
into the app's own `templates/apidocs/`.
"""

from __future__ import annotations

from fjkit.apidocs.console import Recorded
from fjkit.apidocs.flows import (
    AuthFlow,
    FlowError,
    FlowField,
    FlowState,
    HeaderFlow,
    NoFlow,
    SessionFlow,
)
from fjkit.apidocs.plugin import ApiDocsPlugin
from fjkit.apidocs.spec import (
    Field,
    Model,
    Operation,
    Param,
    ResponseDoc,
    SecurityScheme,
    Server,
    Shape,
    Spec,
    TagGroup,
)

__all__ = [
    "ApiDocsPlugin",
    "AuthFlow",
    "Field",
    "FlowError",
    "FlowField",
    "FlowState",
    "HeaderFlow",
    "Model",
    "NoFlow",
    "Operation",
    "Param",
    "Recorded",
    "ResponseDoc",
    "SecurityScheme",
    "Server",
    "SessionFlow",
    "Shape",
    "Spec",
    "TagGroup",
]
