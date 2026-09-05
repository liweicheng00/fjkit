# fjkit for VS Code and Cursor

Definition, references and hover between FastAPI routes, response models,
Jinja templates and htmx events, for both `.html` and `.py` files. The
answers come from [`fjkit-lsp`](../fjkit-lsp/README.md); this is the editor
side, and it is deliberately small: plain JavaScript on the VS Code API, no
`vscode-languageclient`, no bundler, no npm.

## Install

```bash
uv sync                                          # puts fjkit-lsp in .venv
uv run python tools/fjkit-vscode/build.py        # writes dist/fjkit-vscode-<version>.vsix
code   --install-extension tools/fjkit-vscode/dist/fjkit-vscode-*.vsix
cursor --install-extension tools/fjkit-vscode/dist/fjkit-vscode-*.vsix
```

The `.vsix` is a zip that `build.py` assembles with the standard library, so
there is no `vsce` and nothing to install first. Cursor cannot fetch this from
a marketplace — it is not published to one — and needs the file either way.

## How it finds the server

`.venv/bin/fjkit-lsp` under the first workspace folder (`.venv\Scripts\
fjkit-lsp.exe` on Windows), spawned with that folder as its working directory.
It is named by path rather than as `uv run fjkit-lsp` because an editor started
from the Dock carries the bare GUI PATH, `~/.local/bin` is not on it, and `uv`
would be ENOENT; the entry point's shebang is absolute and needs no PATH.

`fjkit.lsp.command` overrides that — a command and its arguments, resolved
against the workspace folder. Any change to it restarts the server, as does
the **fjkit: Restart language server** command. The **fjkit** channel in the
Output panel has the start-up line, or the reason there was none.

## What it does not do

Publish to a marketplace. That needs publisher accounts on two of them and a
release step per change, which CHARTER §6 leaves to a human. The build is one
command, and reinstalling is one more.
