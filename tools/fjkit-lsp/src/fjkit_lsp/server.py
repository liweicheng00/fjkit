"""The LSP front: definition, references and hover for Python and template files."""

from __future__ import annotations

from pathlib import Path

from lsprotocol import types as t
from pygls.lsp.server import LanguageServer
from pygls.uris import from_fs_path, to_fs_path

from fjkit_lsp.index import Index, Loc
from fjkit_lsp.resolve import Resolver


class FjkitServer(LanguageServer):
    def __init__(self) -> None:
        super().__init__("fjkit-lsp", "0.1.0")
        self.index: Index | None = None
        self.resolver: Resolver | None = None

    def build(self, roots: list[Path]) -> None:
        self.index = Index(roots)
        self.resolver = Resolver(self.index)

    def roots(self) -> list[Path]:
        folders = [to_fs_path(f.uri) for f in self.workspace.folders.values()]
        if not folders and self.workspace.root_path:
            folders = [self.workspace.root_path]
        return [Path(f) for f in folders if f]


server = FjkitServer()


def _location(loc: Loc) -> t.Location:
    end = loc.end_col if loc.end_col is not None else loc.col
    return t.Location(
        uri=from_fs_path(str(loc.path)) or "",
        range=t.Range(start=t.Position(loc.line, loc.col), end=t.Position(loc.line, end)),
    )


def _symbol(ls: FjkitServer, params: t.TextDocumentPositionParams):
    if ls.resolver is None:
        ls.build(ls.roots())
    doc = ls.workspace.get_text_document(params.text_document.uri)
    path = Path(to_fs_path(doc.uri) or "")
    return ls.resolver.symbol(path, doc.source, params.position.line, params.position.character)  # type: ignore[union-attr]


@server.feature(t.INITIALIZED)
def on_initialized(ls: FjkitServer, _params: t.InitializedParams) -> None:
    ls.build(ls.roots())


@server.feature(t.TEXT_DOCUMENT_DID_SAVE)
def on_save(ls: FjkitServer, _params: t.DidSaveTextDocumentParams) -> None:
    ls.build(ls.roots())


@server.feature(t.TEXT_DOCUMENT_DEFINITION)
def on_definition(ls: FjkitServer, params: t.DefinitionParams):
    sym = _symbol(ls, params)
    return [_location(loc) for loc in ls.resolver.definition(sym)] or None  # type: ignore[union-attr]


@server.feature(t.TEXT_DOCUMENT_REFERENCES)
def on_references(ls: FjkitServer, params: t.ReferenceParams):
    sym = _symbol(ls, params)
    return [_location(loc) for loc in ls.resolver.references(sym)] or None  # type: ignore[union-attr]


@server.feature(t.TEXT_DOCUMENT_HOVER)
def on_hover(ls: FjkitServer, params: t.HoverParams):
    sym = _symbol(ls, params)
    text = ls.resolver.hover(sym)  # type: ignore[union-attr]
    if not text:
        return None
    return t.Hover(contents=t.MarkupContent(kind=t.MarkupKind.Markdown, value=text))


def start() -> None:
    server.start_io()
