# Release targets. `make help` lists them; `make build verify` is the local
# rehearsal, and .github/workflows/release-*.yml run the same targets on a tag.
#
# Toolchain is uv only (CLAUDE.md). The one thing outside it is `npx ovsx`,
# which uploads the editor extension to Open VSX: it downloads into npm's
# cache and leaves nothing in the repository.
#
# No token is a Makefile variable. `uv publish` reads UV_PUBLISH_TOKEN from
# the environment, and the Open VSX target reads OPEN_VSX_TOKEN.
#
# The order of the six targets is fixed: fjkit first, because the other four
# Python distributions declare it as a dependency; fjkit-vscode last, because
# it starts `fjkit-lsp` from the user's own venv and is inert until that is
# installable.

PYTHON_DISTS := fjkit fjkit-charts fjkit-apidocs fjkit-admin fjkit-lsp
PLUGIN_DISTS := $(filter-out fjkit,$(PYTHON_DISTS))

DIST     := dist
VSIX_DIR := tools/fjkit-vscode/dist
DEMO_TEMPLATES := examples/fjkit-demo/app/templates examples/fjkit-admin-demo/admin_demo/templates

# Lazy (`=`) so a plain `make help` does not spawn uv.
VERSION      = $(shell uv version --package fjkit --short)
VSIX_VERSION = $(shell python3 -c "import json; print(json.load(open('tools/fjkit-vscode/package.json'))['version'])")

# `fjkit-charts` on the command line is `fjkit_charts-<version>` on disk.
dist_files = $(DIST)/$(subst -,_,$(1))-$(VERSION)*

# Set to 1 to mark the extension as a pre-release. The manifest cannot say so
# itself: VS Code requires a strict major.minor.patch, so the flag is the only
# way to publish 0.1.0 as a preview.
PRE_RELEASE ?=

PYPI_URL       := https://pypi.org/simple/
TEST_PYPI_URL  := https://test.pypi.org/simple/
TEST_PYPI_UPLOAD := https://test.pypi.org/legacy/

.PHONY: help check test lint vocab css docs docs-check \
        build $(addprefix build-,$(PYTHON_DISTS)) vsix verify \
        publish-test publish $(addprefix publish-,$(PYTHON_DISTS)) publish-vsix clean

help: ## List targets
	@grep -hE '^[a-z][a-zA-Z0-9_-]*:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'
	@printf "  %-16s %s\n" "build-<dist>" "One distribution; <dist> is one of: $(PYTHON_DISTS)" \
	                        "publish-<dist>" "One distribution to PyPI"

# ----------------------------------------------------------------- checks

check: test lint vocab ## Tests, ruff, and the closed-vocabulary gate

test: ## Every suite: kit, plugins, demos, lsp, extension
	uv run pytest

lint: ## ruff
	uv run ruff check

vocab: ## `fjkit check` on both demos' templates
	@for dir in $(DEMO_TEMPLATES); do uv run fjkit check $$dir || exit 1; done

# ------------------------------------------------------------------ build

# static/dist/ is gitignored, so it exists only where this has run. A wheel
# built without it carries stale CSS and nothing fails: Tailwind scanning a
# missing path is silent.
css: ## Rebuild static/dist/fjkit-<pack>.css (needed before any fjkit wheel)
	uv sync --group build
	uv run fjkit build-css

docs: ## Rebuild the docs site at docs/
	uv run python packages/fjkit/docs/workbench/build.py

docs-check: docs ## Fail if docs/ was stale (what .githooks/pre-push does)
	@git diff --quiet -- docs/ || { echo "docs/ is stale; commit the rebuilt site:"; git --no-pager diff --stat -- docs/; exit 1; }

build: css ## All five Python distributions into dist/
	rm -rf $(DIST)
	for p in $(PYTHON_DISTS); do uv build --package $$p -o $(DIST) || exit 1; done
	@ls -1 $(DIST)

# Static pattern rules rather than `build-%`: a .PHONY target skips implicit
# rule search, so a plain pattern would never fire for these names.
build-fjkit: css
$(addprefix build-,$(PYTHON_DISTS)): build-%:
	uv build --package $* -o $(DIST)

vsix: ## The editor extension as tools/fjkit-vscode/dist/*.vsix
	uv run python tools/fjkit-vscode/build.py

# The checks from the release procedure: every wheel carries the licence, the
# five versions agree, fjkit still has no extras (the style markers were
# withdrawn before 0.1.0 and must not come back), and the built CSS is inside.
# EXPECT_VERSION, when given, must match too; CI passes the tag here.
verify: ## Inspect dist/ before uploading (EXPECT_VERSION=x.y.z to pin)
	@test -d $(DIST) || { echo "no $(DIST)/ — run make build"; exit 1; }
	@v="$(VERSION)"; \
	if [ -n "$(EXPECT_VERSION)" ] && [ "$(EXPECT_VERSION)" != "$$v" ]; then \
	  echo "version mismatch: expected $(EXPECT_VERSION), pyproject says $$v"; exit 1; fi; \
	for p in $(PYTHON_DISTS); do \
	  pv=$$(uv version --package $$p --short); \
	  [ "$$pv" = "$$v" ] || { echo "$$p is $$pv, fjkit is $$v"; exit 1; }; \
	  n=$$(ls $(DIST)/$$(echo $$p | tr - _)-$$v-*.whl $(DIST)/$$(echo $$p | tr - _)-$$v.tar.gz 2>/dev/null | wc -l | tr -d ' '); \
	  [ "$$n" = "2" ] || { echo "$$p: expected a wheel and an sdist for $$v in $(DIST)/, found $$n"; exit 1; }; \
	done; \
	for w in $(DIST)/*.whl; do \
	  meta=$$(unzip -p "$$w" '*/METADATA'); \
	  echo "$$meta" | grep -q '^License-Expression: MIT' || { echo "$$w: no License-Expression: MIT"; exit 1; }; \
	done; \
	fj=$$(ls $(DIST)/fjkit-$$v-*.whl); \
	extras=$$(unzip -p "$$fj" '*/METADATA' | grep -c '^Provides-Extra' || true); \
	[ "$$extras" = "0" ] || { echo "$$fj declares $$extras extras; the style markers must stay withdrawn"; exit 1; }; \
	css=$$(unzip -l "$$fj" | grep -c 'static/dist/' || true); \
	[ "$$css" -ge 8 ] || { echo "$$fj has $$css files under static/dist/, expected the 8 style packs — run make css"; exit 1; }; \
	echo "verify: $(words $(PYTHON_DISTS)) distributions at $$v, licence and CSS present, no extras"

# ---------------------------------------------------------------- publish

# TestPyPI is a separate index with its own accounts and tokens, not a mirror.
# UV_PUBLISH_TOKEN must be the TestPyPI one here.
publish-test: verify ## Upload dist/ to TestPyPI (UV_PUBLISH_TOKEN = TestPyPI token)
	@test -n "$$UV_PUBLISH_TOKEN" || { echo "set UV_PUBLISH_TOKEN to a TestPyPI token"; exit 1; }
	uv publish --publish-url $(TEST_PYPI_UPLOAD) --check-url $(TEST_PYPI_URL) $(DIST)/*

# `--check-url` skips files already on the index, so a run that stopped
# half-way is rerun with the same command. Uploading a version is irreversible.
publish: verify ## Upload to PyPI, fjkit first (UV_PUBLISH_TOKEN = PyPI token)
	@test -n "$$UV_PUBLISH_TOKEN" || { echo "set UV_PUBLISH_TOKEN to a PyPI token"; exit 1; }
	$(MAKE) publish-fjkit
	for p in $(PLUGIN_DISTS); do $(MAKE) publish-$$p || exit 1; done

$(addprefix publish-,$(PYTHON_DISTS)): publish-%:
	uv publish --check-url $(PYPI_URL) $(call dist_files,$*)

# One-time, before the first publish: `npx ovsx create-namespace fjkit -p $OPEN_VSX_TOKEN`.
publish-vsix: vsix ## Upload the extension to Open VSX (OPEN_VSX_TOKEN; PRE_RELEASE=1 to flag it)
	@test -n "$$OPEN_VSX_TOKEN" || { echo "set OPEN_VSX_TOKEN"; exit 1; }
	npx --yes ovsx publish $(VSIX_DIR)/fjkit-vscode-$(VSIX_VERSION).vsix $(if $(PRE_RELEASE),--pre-release) -p "$$OPEN_VSX_TOKEN"

clean: ## Remove dist/ and the built .vsix
	rm -rf $(DIST) $(VSIX_DIR)
