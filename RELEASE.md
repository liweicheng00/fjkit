# fjkit — Release

## Introduction

This repository publishes six artefacts to two registries: `fjkit`, `fjkit-charts`, `fjkit-apidocs`, `fjkit-admin` and `fjkit-lsp` to PyPI, and `fjkit-vscode` to Open VSX. A release is a tag push, and each artefact has its own tag prefix and its own version: the admin ships when the admin changes, not when the kit does. Every step a maintainer could run by hand is a `make` target and the workflows in `.github/workflows/` call those same targets, so the local rehearsal and the automated publish cannot drift; PyPI uploads authenticate through Trusted Publishing and the Open VSX token is a repository secret, so cutting a release needs no credential on a maintainer's machine.

---

## Git flow

### Branches and pull requests

`main` is protected. Every change arrives as a pull request, and a pull request merges only with CI green.

| Rule           | Value                                                                    |
| -------------- | ------------------------------------------------------------------------ |
| Branch name    | `feat/<slug>`, `fix/<slug>`, `docs/<slug>`, `chore/<slug>`, `rfc/<slug>` |
| Scope          | One issue, one branch, one pull request                                  |
| Size           | Split anything over roughly 400 changed lines                            |
| Commit subject | Conventional Commits — `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`   |

There is no `CHANGELOG.md`, by decision: release notes are generated from the commit subjects on `main`. A commit subject that does not name the change is therefore a release note that does not name it either.

A breaking change is `feat!:`, or a `BREAKING CHANGE:` footer. Before 1.0 that needs no ceremony; after 1.0 it needs an RFC and a deprecation period spanning two minor versions (`CHARTER.md` §6).

**Warning**: `docs/` at the repository root is a build artefact that is committed. A push that changes the site's source but not its output ships a site describing the previous commit. Enable the hook once — `git config core.hooksPath .githooks` — and `.githooks/pre-push` rebuilds the site and blocks the push while it is stale. The `docs` job in `ci.yml` catches the same thing through `make docs-check` when the hook was never enabled.

### Versions

Each distribution carries its own version, and nothing in the tooling compares one against another. The weekly `0.x.0` cadence is `fjkit`'s; a plugin releases when the plugin changes. Macro signatures are not frozen until 1.0.

Bump one package:

```bash
uv version --package fjkit-admin --bump minor
uv version --package fjkit-admin --short      # the number its tag must carry
```

`--bump stable` turns `0.1.0.dev0` into `0.1.0`; `--bump minor` turns it into `0.2.0`. A `.devN` or `.rcN` version is a PEP 440 pre-release, which `pip install fjkit` does not select: a reader of the release announcement needs `pip install --pre fjkit` or `uv add --prerelease allow fjkit`.

**Warning**: a plugin's `fjkit>=` lower bound is the only statement of which kit that release needs. Raise it in the same pull request that starts using a new macro, a new `FjkitConfig` knob or a new plugin hook — otherwise the plugin resolves against an older kit and fails at import, or renders a macro that is not there. `make verify` fails a plugin whose metadata carries no bound at all; it cannot tell whether an existing bound is high enough.

`fjkit-lsp` declares no dependency on `fjkit` and has nothing to raise. `fjkit-charts`, `fjkit-apidocs` and `fjkit-admin` each declare one, with no upper bound: a plugin accepts every later kit, which stays true only while a kit release keeps its macros.

### Tags

One tag publishes one distribution.

| Tag | Publishes | Version source |
|---|---|---|
| `v<X.Y.Z>` | `fjkit` to PyPI | `packages/fjkit/pyproject.toml` |
| `charts-v<X.Y.Z>` | `fjkit-charts` to PyPI | `packages/fjkit-charts/pyproject.toml` |
| `apidocs-v<X.Y.Z>` | `fjkit-apidocs` to PyPI | `packages/fjkit-apidocs/pyproject.toml` |
| `admin-v<X.Y.Z>` | `fjkit-admin` to PyPI | `packages/fjkit-admin/pyproject.toml` |
| `lsp-v<X.Y.Z>` | `fjkit-lsp` to PyPI | `tools/fjkit-lsp/pyproject.toml` |
| `vscode-v<X.Y.Z>` | `fjkit-vscode` to Open VSX | `tools/fjkit-vscode/package.json` |

The tag is the version, and both workflows refuse a tag that disagrees with the manifest: `make verify PACKAGE=<dist> EXPECT_VERSION=<X.Y.Z>` for PyPI, a direct comparison against `package.json` for the extension.

The kit's prefix is matched as `v[0-9]*`, because the glob `v*` also matches `vscode-v0.1.0` and would hand the extension's tag to the PyPI workflow.

A VS Code manifest requires a strict three-segment version, so `0.1.0.dev0` is rejected by the packager. The extension stays at `0.1.0` and marks a preview with a publish flag instead — `make publish-vsix PRE_RELEASE=1`.

Cut the tag after the version bump is merged to `main`:

```bash
git switch main && git pull
git tag admin-v0.2.0 && git push origin admin-v0.2.0
```

**Warning**: a published version number is permanent. PyPI and Open VSX both refuse a re-upload, and deleting a release does not free the number. The same holds for the six project names and the Open VSX namespace: neither registry transfers or recycles them. Claiming a name or issuing a credential needs a human decision (`CHARTER.md` §6.5, §6.6); releasing an `0.x` does not.

---

## Pipeline

### The three workflows

| Workflow             | Trigger                            | What it does                                                                                            |
| -------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `ci.yml`             | push to `main`, every pull request | `make check` (pytest, ruff, `fjkit check`), `make docs-check`, `make build && make verify && make vsix` |
| `release-pypi.yml` | tag `v[0-9]*`, `charts-v*`, `apidocs-v*`, `admin-v*`, `lsp-v*`, or a manual run | builds and verifies the one distribution the tag names, then uploads it |
| `release-vscode.yml` | tag `vscode-v*`, or a manual run   | builds the `.vsix` and uploads it to Open VSX                                                           |

`ci.yml` builds and verifies all six artefacts on every push, so a broken wheel surfaces before a tag exists rather than after the upload.

### Publish order

When more than one artefact goes out together, the order is fixed:

```
fjkit  ──►  fjkit-charts · fjkit-apidocs · fjkit-admin  ──►  fjkit-lsp  ──►  fjkit-vscode
```

The arrows bind tags, not jobs. `release-pypi.yml` publishes whatever its tag names and has no cross-package `needs`, so nothing stops a plugin's tag from going first — and a plugin uploaded before the `fjkit` its lower bound requires installs nowhere until the kit's tag lands. Push the kit's tag first and let it reach the index whenever a plugin release raises that bound.

`fjkit-charts`, `fjkit-apidocs` and `fjkit-admin` declare `Requires-Dist: fjkit>=…`. `fjkit-lsp` depends only on `pygls`, so its tag is free of that order; it comes before the extension because `fjkit-vscode` starts `.venv/bin/fjkit-lsp` from the user's own workspace and installs but does nothing until the server is on PyPI.

A plugin release that needs no new kit feature keeps its existing bound and can go out alone, on any day, with one tag.

### PyPI, through Trusted Publishing

Uploads authenticate with OIDC, so there is no token in the repository and nothing to rotate. Registration is one-time, per index and per project name. A name that does not exist yet is registered as a *pending* publisher at [https://pypi.org/manage/account/publishing/](https://pypi.org/manage/account/publishing/):

| Field             | Value                                                                |
| ----------------- | -------------------------------------------------------------------- |
| PyPI project name | `fjkit`, `fjkit-charts`, `fjkit-apidocs`, `fjkit-admin`, `fjkit-lsp` |
| Owner             | `liweicheng00`                                                       |
| Repository name   | `fjkit`                                                              |
| Workflow name     | `release-pypi.yml`                                                   |
| Environment name  | `pypi`, or `testpypi` for the rehearsal                              |

Create both environments under Settings → Environments. A required reviewer on `pypi` turns a tag push into an approval step, which is the only brake that exists on an irreversible upload.

### Rehearsing on TestPyPI

Run `release-pypi.yml` from the Actions tab: pick the distribution in the `package` input, and leave `target` at its `testpypi` default. A manual run takes the version from that package's pyproject.toml, so there is no tag to cut for a rehearsal. TestPyPI rejects a malformed README at upload time, which is the failure worth catching before a version number is spent.

TestPyPI is a separate namespace, not a mirror, and `fastapi` there is an unrelated and broken package. Installing back from it therefore depends on index order:

```bash
uv run --isolated --no-project \
  --index https://pypi.org/simple/ \
  --index https://test.pypi.org/simple/ \
  --prerelease allow --with fjkit \
  python -c "import fjkit; print(fjkit.__name__)"
```

uv's default `first-index` strategy takes the first index that carries the name: the real dependencies resolve from PyPI, and only the `fjkit*` names fall through to TestPyPI. Do not add `--index-strategy unsafe-best-match` — it compares versions across every index and selects TestPyPI's unrelated `fastapi`, which fails to build.

### Open VSX

One-time setup, before the first extension release:

1. Sign in at [https://open-vsx.org](https://open-vsx.org) with GitHub.
2. Sign the Eclipse Publisher Agreement. An unsigned agreement is the usual cause of a rejected publish.
3. Create an access token, and store it as the repository secret `OPEN_VSX_TOKEN`.
4. Claim the namespace once, from a machine: `npx ovsx create-namespace fjkit -p <token>`.

`npx` runs from npm's cache and leaves no `node_modules` in the repository. The `.vsix` itself is built by `tools/fjkit-vscode/build.py`, which writes the zip directly and needs neither npm nor `vsce`. The archive embeds timestamps, so two builds of one commit differ by hash; do not treat the hash as a version identifier.

Open VSX serves Cursor, VSCodium, Windsurf and Gitpod. VS Code reads only Microsoft's Marketplace, so those users sideload the `.vsix`. Publishing there as well is undecided and would need a separate Azure DevOps account and token.

### Rehearsing the whole thing locally

```bash
make check                  # pytest, ruff, fjkit check
make build                  # `make css` first, then all five into dist/
make build-fjkit-admin      # or one of them
make verify                 # each distribution at its own version: licence, wheel, sdist, bound
make verify PACKAGE=fjkit-admin EXPECT_VERSION=0.2.0   # what a tag checks
make vsix                   # the extension archive
```

**Warning**: `make css` writes `static/dist/`, which is gitignored. A wheel built without it carries stale CSS and nothing fails, because Tailwind scanning a missing path is silent. `make build` and `make verify` both cover this — `verify` counts the eight style packs inside the wheel — so build through the targets rather than calling `uv build` directly.

`make publish-test` uploads everything in `dist/` to TestPyPI, `make publish` uploads everything to PyPI, and `make publish-<dist>` uploads one — all three from a maintainer's machine, with `UV_PUBLISH_TOKEN`. They exist as a fallback for a broken pipeline; the tag is the normal path, and it needs no token at all.

### Not automated

| Step                                                | Status                                                                                                                                                                                                         |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GitHub Release and its notes                        | Manual. Generated from the Conventional Commits subjects on `main`.                                                                                                                                            |
| Version bumps | Manual, one `uv version --package <dist>` call per distribution. |
| Extension version against the Python version        | Unchecked. The two tags are independent.                                                                                                                                                                       |
| Whether a plugin's `fjkit>=` bound is high enough | Unchecked. `make verify` fails a plugin that declares no bound; it cannot tell that an existing one is too low. |
| End-to-end editor verification                      | Manual: install the extension in Cursor, open a project with `fjkit-lsp` installed, confirm hover and go-to-definition. This is the only check that proves the extension, the server and their wiring at once. |
| Render-performance regression                       | Ungated. `bench/render_bench.py` prints numbers; the threshold is undecided.                                                                                                                                   |
