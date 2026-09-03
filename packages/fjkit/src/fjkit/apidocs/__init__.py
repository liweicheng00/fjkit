"""API reference and console for a fjkit app, in place of Swagger UI.

    from fjkit import FjkitConfig, mount_fjkit
    from fjkit.apidocs import ApiDocsPlugin
    from fjkit.auth import AuthPlugin

    auth = AuthPlugin(secret=…, source=MyOIDCSource(), trusted_origins=[…])
    app = FastAPI(docs_url=None, redoc_url=None)
    mount_fjkit(app, FjkitConfig(template_dir=…, plugins=(auth, ApiDocsPlugin())))

That is the whole setup. The page appears at `/api-docs`, built from the same
`app.openapi()` document Swagger reads, and its sign-in panel is wired to
`auth`, which the plugin finds in the same `plugins` tuple.

Two things Swagger UI cannot do, both for the same reason:

* **Sign-in is the app's own code.** `AuthFlow` is a Python object, so "log in"
  means whatever the app defines. `SessionFlow` runs `AuthPlugin.issue`, which
  runs the app's `TokenSource`. OpenAPI cannot describe that, and Swagger's
  Authorize dialog has no room for it.
* **Calls carry a credential JavaScript cannot reach.** The console replays the
  request through the app in-process, forwarding the caller's HttpOnly session
  cookie. The middleware the call passes through handles token refresh,
  revocation and CSRF; the page does not reimplement them.

The rest is ordinary fjkit: server-rendered macros, htmx swaps, no build step.
Shadow any template by dropping a file of the same name into the app's own
`templates/apidocs/`.
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
