"""Package the extension as a .vsix, with no npm and no `vsce`.

A .vsix is a zip: `[Content_Types].xml`, `extension.vsixmanifest`, and the
extension under `extension/`. Everything the manifest needs is already in
package.json, so this reads it and writes the XML.

    uv run python tools/fjkit-vscode/build.py            # -> tools/fjkit-vscode/dist/
    code   --install-extension tools/fjkit-vscode/dist/fjkit-vscode-0.1.0.vsix
    cursor --install-extension tools/fjkit-vscode/dist/fjkit-vscode-0.1.0.vsix
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
#: What goes into the archive, besides the manifest and the licence.
FILES = ("package.json", "extension.js", "README.md")
CONTENT_TYPES = {"json": "application/json", "js": "application/javascript", "md": "text/markdown", "txt": "text/plain"}


def manifest(pkg: dict) -> str:
    props = {
        "Microsoft.VisualStudio.Code.Engine": pkg["engines"]["vscode"],
        "Microsoft.VisualStudio.Code.ExtensionDependencies": "",
        "Microsoft.VisualStudio.Code.ExtensionPack": "",
        # It spawns a process next to the workspace, so in a remote session it
        # belongs on the remote side, where the workspace and its .venv are.
        "Microsoft.VisualStudio.Code.ExtensionKind": "workspace",
        "Microsoft.VisualStudio.Code.ExecutesCode": "true",
        "Microsoft.VisualStudio.Services.Links.Source": pkg["repository"]["url"],
        "Microsoft.VisualStudio.Services.GitHubFlavoredMarkdown": "true",
    }
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011"'
        ' xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">',
        "  <Metadata>",
        f'    <Identity Language="en-US" Id="{pkg["name"]}" Version="{pkg["version"]}"'
        f' Publisher="{pkg["publisher"]}"/>',
        f"    <DisplayName>{escape(pkg['displayName'])}</DisplayName>",
        f'    <Description xml:space="preserve">{escape(pkg["description"])}</Description>',
        f"    <Tags>{escape(','.join(pkg.get('keywords', [])))}</Tags>",
        f"    <Categories>{escape(','.join(pkg.get('categories', [])))}</Categories>",
        "    <Properties>",
        *[f'      <Property Id="{k}" Value="{escape(v)}"/>' for k, v in props.items()],
        "    </Properties>",
        "    <License>extension/LICENSE</License>",
        "  </Metadata>",
        '  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>',
        "  <Dependencies/>",
        "  <Assets>",
        *[
            f'    <Asset Type="Microsoft.VisualStudio.{kind}" Path="extension/{file}" Addressable="true"/>'
            for kind, file in (
                ("Code.Manifest", "package.json"),
                ("Services.Content.Details", "README.md"),
                ("Services.Content.License", "LICENSE"),
            )
        ],
        "  </Assets>",
        "</PackageManifest>",
    ]
    return "\n".join(lines) + "\n"


def content_types() -> str:
    defaults = "".join(f'<Default Extension="{e}" ContentType="{t}"/>' for e, t in CONTENT_TYPES.items())
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        f'<Default Extension="vsixmanifest" ContentType="text/xml"/>{defaults}</Types>'
    )


def build(out_dir: Path) -> Path:
    pkg = json.loads((HERE / "package.json").read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{pkg['name']}-{pkg['version']}.vsix"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types())
        z.writestr("extension.vsixmanifest", manifest(pkg))
        for name in FILES:
            z.write(HERE / name, f"extension/{name}")
        z.write(ROOT / "LICENSE", "extension/LICENSE")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--out", type=Path, default=HERE / "dist", help="directory for the .vsix (default: dist/)")
    print(build(ap.parse_args().out))


if __name__ == "__main__":
    main()
