<!--
Release pull request: release/v<X.Y.Z> -> main.  Title: chore(release): v<X.Y.Z>
Fill this in when the branch is complete; RELEASE.md, "Release branch", has the steps.
Delete every row and line that does not apply. Merge with "Create a merge commit".
-->

## Versions

| Distribution | From | To | Tag |
|---|---|---|---|
| fjkit | 0.0.0 | 0.0.0 | `v0.0.0` |
| fjkit-charts | 0.0.0 | 0.0.0 | `charts-v0.0.0` |
| fjkit-apidocs | 0.0.0 | 0.0.0 | `apidocs-v0.0.0` |
| fjkit-admin | 0.0.0 | 0.0.0 | `admin-v0.0.0` |
| fjkit-lsp | 0.0.0 | 0.0.0 | `lsp-v0.0.0` |
| fjkit-vscode | 0.0.0 | 0.0.0 | `vscode-v0.0.0` |

## Changes

<!-- git log --no-merges --format='- %s' v<previous>..release/v<X.Y.Z>, grouped by type. -->

### Breaking

- 

### Features

- 

### Fixes

- 

### Docs and internal

- 

## Plugin bounds

<!-- One line per plugin in Versions: the bound it now declares, and why. -->

- `fjkit-admin`: `fjkit>=0.0.0` — unchanged / raised for <macro, knob or hook>.

## Rehearsal

| Distribution | TestPyPI run |
|---|---|
| fjkit | |

## Checklist

- [ ] The first commit bumps `fjkit`, and only `fjkit`
- [ ] Every plugin that changed has its own bump commit
- [ ] `fjkit>=` bounds are raised wherever a plugin uses something this release adds
- [ ] `docs/` is rebuilt
- [ ] CI is green
- [ ] Every distribution above installed from TestPyPI at its new version

## After merge

Tag the merge commit on `main`, in this order: `v<X.Y.Z>`, then the plugin tags above, then `lsp-v…`, then `vscode-v…`. Each PyPI run waits for the `pypi` environment's reviewer.
