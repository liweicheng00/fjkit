"""The package builds, and — where Node is on the PATH — the client drives the server."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]


def test_the_vsix_carries_the_manifest_and_the_code(tmp_path: Path) -> None:
    subprocess.run([sys.executable, str(HERE / "build.py"), "--out", str(tmp_path)], check=True, capture_output=True)
    (vsix,) = tmp_path.glob("*.vsix")
    with zipfile.ZipFile(vsix) as z:
        names = set(z.namelist())
        manifest = z.read("extension.vsixmanifest").decode()
    pkg = json.loads((HERE / "package.json").read_text())
    expected = {"[Content_Types].xml", "extension.vsixmanifest", "extension/package.json", "extension/extension.js"}
    assert expected <= names
    assert f'Id="{pkg["name"]}"' in manifest and f'Version="{pkg["version"]}"' in manifest
    assert vsix.name == f"{pkg['name']}-{pkg['version']}.vsix"


def test_the_manifest_declares_no_dependencies_and_no_scripts() -> None:
    """The toolchain rule: a manifest is unavoidable, a dependency tree is not."""
    pkg = json.loads((HERE / "package.json").read_text())
    assert not {"dependencies", "devDependencies", "scripts"} & pkg.keys()


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on the PATH")
def test_the_client_drives_the_server_end_to_end() -> None:
    result = subprocess.run(["node", str(HERE / "tests/check.js")], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
