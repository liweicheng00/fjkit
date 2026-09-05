# fjkit-apidocs

An API reference and in-process console for FastAPI, in place of Swagger UI.
A [fjkit](https://liweicheng00.github.io/fjkit/) plugin — server-rendered
macros, htmx swaps, no build step.

```bash
uv add fjkit-apidocs
```

```python
from fastapi import FastAPI
from fjkit import FjkitConfig, mount_fjkit
from fjkit_apidocs import ApiDocsPlugin

app = FastAPI(docs_url=None, redoc_url=None)
mount_fjkit(app, FjkitConfig(template_dir=APP_DIR / "templates", plugins=(ApiDocsPlugin(),)))
```

The page appears at `/api-docs`, built from the same `app.openapi()` document
Swagger reads. Two things Swagger UI cannot do:

- **Sign-in is the app's own code.** `AuthFlow` is a Python object, so "log in"
  means whatever the app defines.
- **Calls carry a credential JavaScript cannot reach.** The console replays the
  request through the app in-process, forwarding the caller's HttpOnly session
  cookie, so token refresh, revocation and CSRF are handled by the middleware
  the call passes through rather than reimplemented in the page.

Shadow any template by dropping a file of the same name into the app's own
`templates/apidocs/`.

## License

MIT. See [LICENSE](LICENSE).
