"""The workspace index: routes, response models, templates and the links between them.

Python files are read with `ast`; templates are scanned with regular expressions
so that every recorded item carries a line and a column.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".claude",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
    # A route or model in a test file never ships; indexing it puts throwaway
    # `def thing()` handlers next to the real ones in every answer.
    "tests",
}
TEMPLATE_SUFFIXES = {".html", ".jinja", ".j2", ".txt", ".xml", ".svg"}
#: `fjkit/ui/form.html` always means the kit's own copy, whatever shadows
#: `ui/form.html`. `fjkit.templating._ReservedNamespace` is the loader that
#: makes that true at runtime; resolution here has to agree with it.
FJKIT_NAMESPACE = "fjkit/"
KIT_TEMPLATES = "/src/fjkit/templates"
ROUTE_METHODS = {"get", "post", "put", "delete", "patch", "options", "head", "api_route", "route"}


@dataclass(frozen=True)
class Loc:
    path: Path
    line: int  # 0-based
    col: int = 0
    end_col: int | None = None


@dataclass(frozen=True)
class Emit:
    """One event a route raises through `hx_trigger` / `hx_trigger_after_swap`.

    `name` is the string itself, or the identifier that holds it — a route
    usually says `SELECTED_EVENT`, not `"task-selected"`, so the string is only
    known once that constant's module is indexed. `Index.event_name` does that.
    """

    name: str
    loc: Loc
    is_const: bool
    after_swap: bool


@dataclass
class Route:
    func: str
    name: str | None
    loc: Loc
    templates: tuple[str, ...]
    model: str | None
    module: Path
    method: str | None = None  # GET, POST, … — None for a @render with no route decorator
    path: str | None = None  # the router's prefix already applied
    emits: tuple[Emit, ...] = ()

    def matches(self, url: str) -> bool:
        """Whether a literal URL — query string and all — hits this route's path."""
        return self.path is not None and _path_pattern(self.path).fullmatch(url.split("?", 1)[0]) is not None


@dataclass
class Model:
    name: str
    loc: Loc
    fields: dict[str, Loc]
    annotations: dict[str, str]
    bases: list[str]
    module: Path


@dataclass
class TemplateRef:
    name: str
    loc: Loc
    kind: str  # extends | include | import | from | render | partial | literal


@dataclass
class Macro:
    name: str
    loc: Loc
    params: list[str]
    end_line: int


@dataclass
class Local:
    name: str
    loc: Loc
    kind: str  # set | for | call | param | import
    source: str | None = None  # for `for x in source`: the head identifier of the iterable
    end_line: int | None = None  # scope end for params


@dataclass
class Template:
    path: Path
    name: str
    text: str
    root: Path | None = None  # the templates directory the name is relative to
    refs: list[TemplateRef] = field(default_factory=list)
    macros: dict[str, Macro] = field(default_factory=dict)
    imports: dict[str, tuple[str, str]] = field(default_factory=dict)  # local -> (template, macro or "")
    locals: list[Local] = field(default_factory=list)
    ids: list[tuple[str, Loc]] = field(default_factory=list)  # id="…", as an attribute or a macro kwarg
    _code: str | None = field(default=None, repr=False, compare=False)

    def code(self) -> str:
        """The text with everything but Jinja code blanked out. Computed once:
        the same template is searched again for every field a query touches."""
        if self._code is None:
            self._code = _code_only(self.text)
        return self._code


_TAG = re.compile(r"\{%-?\s*(\w+)(.*?)-?%\}", re.DOTALL)
_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
_STRING = re.compile(r"\"([^\"]*)\"|'([^']*)'")
_IDENT = re.compile(r"[A-Za-z_]\w*")


def _first_string(body: str) -> str | None:
    m = _STRING.search(body)
    return (m.group(1) or m.group(2)) if m else None


def _split_top(s: str) -> list[str]:
    """Split on commas that are not nested in brackets."""
    out, depth, cur = [], 0, []
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur))
    return [p.strip() for p in out if p.strip()]


_CODE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)
#: `id="board"` — an HTML attribute or a macro keyword, the regex does not care.
#: `\bid` keeps `field_id=` and `task_id=` out, because `_` is a word character.
_ID_ATTR = re.compile(r"\bid\s*=\s*\"([^\"]*)\"")
#: The receiver a route decorator is called on: `router` in `@router.get(...)`.
_ROUTER_PARAM = re.compile(r"\{(\w+)(?::(\w+))?\}")


def _path_pattern(path: str) -> re.Pattern[str]:
    """`/tasks/{task_id}/advance` as a regex; `{name:path}` swallows slashes like Starlette."""
    out, at = [], 0
    for m in _ROUTER_PARAM.finditer(path):
        out.append(re.escape(path[at : m.start()]))
        out.append(".+" if m.group(2) == "path" else "[^/]+")
        at = m.end()
    out.append(re.escape(path[at:]))
    return re.compile("".join(out))


def event_names(expr: ast.expr) -> list[tuple[str, bool]]:
    """The events an `hx_trigger` argument raises: (name, is_const).

    Reads the shapes the parameter documents — a string, a dict keyed by event,
    a lambda returning either, a conditional — and takes the top-level keys only:
    in `{SELECTED_EVENT: {SELECTED_KEY: task_id}}` the inner key is detail, not
    an event.
    """
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return [(expr.value, False)]
    if isinstance(expr, ast.Name):
        return [(expr.id, True)]
    if isinstance(expr, ast.Dict):
        return [n for k in expr.keys if k is not None for n in event_names(k)]
    if isinstance(expr, ast.Lambda):
        return event_names(expr.body)
    if isinstance(expr, ast.IfExp):
        return event_names(expr.body) + event_names(expr.orelse)
    return []


def _blank(m: re.Match[str]) -> str:
    """Spaces the length of the match, newlines kept: offsets *and* line numbers
    computed on the result still describe the original text."""
    return re.sub(r"[^\n]", " ", m.group(0))


def _code_only(text: str) -> str:
    """The text with everything outside Jinja expressions/tags, comments and string
    literals replaced by spaces, so offsets are unchanged."""
    text = _COMMENT.sub(_blank, text)
    out = [c if c == "\n" else " " for c in text]
    for m in _CODE.finditer(text):
        seg = _STRING.sub(_blank, m.group(0))
        out[m.start() : m.end()] = seg
    return "".join(out)


class _Lines:
    def __init__(self, text: str) -> None:
        self.starts = [0]
        for m in re.finditer("\n", text):
            self.starts.append(m.end())

    def pos(self, offset: int) -> tuple[int, int]:
        lo, hi = 0, len(self.starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo, offset - self.starts[lo]


def scan_template(path: Path, name: str, text: str) -> Template:
    t = Template(path=path, name=name, text=text)
    lines = _Lines(text)
    # Blank out comments so a tag inside one is not indexed; offsets are preserved.
    clean = _COMMENT.sub(_blank, text)
    stack: list[Macro] = []

    def loc_of(offset: int, length: int = 0) -> Loc:
        line, col = lines.pos(offset)
        return Loc(path, line, col, col + length if length else None)

    for m in _ID_ATTR.finditer(clean):
        t.ids.append((m.group(1), loc_of(m.start(1), len(m.group(1)))))
    for m in _TAG.finditer(clean):
        tag, body = m.group(1), m.group(2)
        body_start = m.start(2)
        if tag in ("extends", "include"):
            s = _STRING.search(body)
            if s:
                t.refs.append(
                    TemplateRef(s.group(1) or s.group(2), loc_of(body_start + s.start(), len(s.group(0))), tag)
                )
        elif tag == "import":
            s = _STRING.search(body)
            alias = re.search(r"\bas\s+(\w+)", body)
            if s:
                tpl = s.group(1) or s.group(2)
                t.refs.append(TemplateRef(tpl, loc_of(body_start + s.start(), len(s.group(0))), tag))
                if alias:
                    t.imports[alias.group(1)] = (tpl, "")
                    t.locals.append(
                        Local(alias.group(1), loc_of(body_start + alias.start(1), len(alias.group(1))), "import")
                    )
        elif tag == "from":
            s = _STRING.search(body)
            if s:
                tpl = s.group(1) or s.group(2)
                t.refs.append(TemplateRef(tpl, loc_of(body_start + s.start(), len(s.group(0))), tag))
                imp = re.search(r"\bimport\b", body)
                if imp:
                    names_src = body[imp.end() :]
                    names_src = re.sub(r"\bwith(out)?\s+context\b", "", names_src)
                    base = body_start + imp.end()
                    off = 0
                    for part in names_src.split(","):
                        seg = part
                        mm = re.match(r"\s*(\w+)(?:\s+as\s+(\w+))?", seg)
                        if mm:
                            macro, alias = mm.group(1), mm.group(2) or mm.group(1)
                            t.imports[alias] = (tpl, macro)
                            at = base + off + (mm.start(2) if mm.group(2) else mm.start(1))
                            t.locals.append(Local(alias, loc_of(at, len(alias)), "import"))
                        off += len(part) + 1
        elif tag == "macro":
            mm = re.match(r"\s*(\w+)\s*\((.*)\)\s*$", body, re.DOTALL)
            if mm:
                params = [p.split("=", 1)[0].strip() for p in _split_top(mm.group(2))]
                mac = Macro(mm.group(1), loc_of(body_start + mm.start(1), len(mm.group(1))), params, -1)
                t.macros[mac.name] = mac
                stack.append(mac)
                for p in params:
                    pm = re.search(rf"\b{re.escape(p)}\b", body[mm.start(2) :])
                    at = body_start + mm.start(2) + (pm.start() if pm else 0)
                    t.locals.append(Local(p, loc_of(at, len(p)), "param", end_line=None))
        elif tag == "endmacro":
            if stack:
                mac = stack.pop()
                mac.end_line = lines.pos(m.start())[0]
                for lo in t.locals:
                    if lo.kind == "param" and lo.end_line is None and lo.loc.line >= mac.loc.line:
                        lo.end_line = mac.end_line
        elif tag == "set":
            head = body.split("=", 1)[0]
            for mm in _IDENT.finditer(head):
                t.locals.append(Local(mm.group(0), loc_of(body_start + mm.start(), len(mm.group(0))), "set"))
        elif tag == "for":
            mm = re.match(r"\s*(.*?)\s+in\s+(.*)$", body, re.DOTALL)
            if mm:
                src = _IDENT.search(mm.group(2))
                for im in _IDENT.finditer(mm.group(1)):
                    t.locals.append(
                        Local(
                            im.group(0),
                            loc_of(body_start + mm.start(1) + im.start(), len(im.group(0))),
                            "for",
                            source=src.group(0) if src else None,
                        )
                    )
        elif tag == "call":
            mm = re.match(r"\s*\((.*?)\)", body, re.DOTALL)
            if mm:
                for im in _IDENT.finditer(mm.group(1)):
                    t.locals.append(
                        Local(im.group(0), loc_of(body_start + mm.start(1) + im.start(), len(im.group(0))), "call")
                    )
        elif tag == "with":
            for part in _split_top(body):
                im = _IDENT.match(part.strip())
                if im:
                    t.locals.append(
                        Local(im.group(0), loc_of(body_start + body.find(part) + im.start(), len(im.group(0))), "set")
                    )
    return t


def _annotation_name(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    src = ast.unparse(node)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        src = node.value
    m = re.search(r"\b([A-Z]\w*)\b", src)
    return m.group(1) if m else None


def _decorator_call(dec: ast.expr) -> tuple[str, ast.Call, str | None] | None:
    """(attribute or function name, the call, the receiver) — `router` in `@router.get`."""
    if not isinstance(dec, ast.Call):
        return None
    f = dec.func
    if isinstance(f, ast.Name):
        return f.id, dec, None
    if isinstance(f, ast.Attribute):
        return f.attr, dec, f.value.id if isinstance(f.value, ast.Name) else None
    return None


def _is(a: Template | None, b: Template | None) -> bool:
    """The same file. Not `is`: an open buffer is re-scanned on every request, so
    the Template a query carries is a fresh object for an already indexed path."""
    return a is not None and b is not None and a.path == b.path


def _str(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


class Index:
    """Every template, route and model under `roots`, and the links between them.

    A repository holds more than one application — two demos and the docs
    workbench here — and each one has its own `base.html`. Template names are
    therefore only unique inside one app's loader chain, so the index keeps a
    chain per app rather than a single flat name table. See `chain_for`.
    """

    def __init__(self, roots: list[Path]) -> None:
        self.roots = [r.resolve() for r in roots]
        self.template_roots: list[Path] = []
        self.app_roots: list[Path] = []  # one per application, in path order
        self.shared_roots: list[Path] = []  # the kit's and every plugin's
        self.kit_root: Path | None = None  # packages/fjkit/src/fjkit/templates
        #: Every app in path order, then the shared roots. Used when nothing
        #: says which application is asking, so a name two apps share at least
        #: resolves to the same one every time.
        self.default_chain: list[Path] = []
        self._root_chains: dict[Path, list[Path]] = {}
        self.by_root: dict[Path, dict[str, Template]] = {}
        self.templates: dict[str, Template] = {}  # name -> template, over the default chain
        self.by_path: dict[Path, Template] = {}
        self.routes: list[Route] = []
        self.models: dict[str, list[Model]] = {}
        self.literals: list[TemplateRef] = []  # template names mentioned in python
        self.globals: dict[str, Loc] = {}  # env.globals["x"] = ...
        self.imports: dict[Path, dict[str, str]] = {}  # module -> {name: dotted module}
        self.constants: dict[Path, dict[str, tuple[str, Loc]]] = {}  # module -> {NAME: (value, where)}
        self.prefixes: dict[Path, dict[str, str]] = {}  # module -> {router variable: APIRouter(prefix=…)}
        self._chains: dict[Path, list[Path]] = {}  # module -> chain_for, memoised
        self._events: dict[str, list[tuple[Route, Emit]]] | None = None  # resolved lazily
        self.rebuild()

    # ---- building -------------------------------------------------------

    def _walk(self, suffixes: set[str]):
        for root in self.roots:
            for p in root.rglob("*"):
                if any(part in SKIP_DIRS or part.startswith(".") for part in p.relative_to(root).parts[:-1]):
                    continue
                if p.is_file() and p.suffix in suffixes:
                    yield p

    def rebuild(self) -> None:
        self.templates.clear()
        self.by_root.clear()
        self.by_path.clear()
        self.routes.clear()
        self.models.clear()
        self.literals.clear()
        self.globals.clear()
        self.imports.clear()
        self.constants.clear()
        self.prefixes.clear()
        self._chains.clear()
        self._events = None
        self._classify_roots()
        for p in self._walk(TEMPLATE_SUFFIXES):
            root = next((r for r in self.template_roots if p.is_relative_to(r)), None)
            if root is None:
                continue
            name = p.relative_to(root).as_posix()
            try:
                text = p.read_text(encoding="utf-8")
            except OSError:
                continue
            t = scan_template(p, name, text)
            t.root = root
            self.by_path[p] = t
            self.by_root.setdefault(root, {}).setdefault(name, t)
        for root in self.default_chain:
            for name, t in self.by_root.get(root, {}).items():
                self.templates.setdefault(name, t)
        for p in self._walk({".py"}):
            self._index_python(p)

    def _classify_roots(self) -> None:
        """Split every `templates` directory into the app roots and the shared ones.

        A directory under a package's `src/` belongs to a distribution — the kit
        or a plugin — and `mount_fjkit` puts it in every app's chain. Any other
        one is an application's own, seen by that application alone.
        """
        roots = set()
        for p in self._walk(TEMPLATE_SUFFIXES):
            for parent in p.parents:
                if parent.name == "templates":
                    roots.add(parent)
                    break
        self.template_roots = sorted(roots)
        self.shared_roots = [r for r in self.template_roots if "/src/" in f"{r}/"]
        self.app_roots = [r for r in self.template_roots if r not in self.shared_roots]
        self.kit_root = next((r for r in self.shared_roots if str(r).endswith(KIT_TEMPLATES)), None)
        # The kit last, so a plugin can replace one of its macros but never the
        # other way round — the order `build_environment` gives the ChoiceLoader.
        self.shared_roots.sort(key=lambda r: (r == self.kit_root, str(r)))
        # One chain per root, built once: an app sees its own templates, then
        # every plugin's, then the kit's. A distribution sees only the shared
        # ones — its templates name their own, never an application's.
        self._root_chains = {r: [r] + self.shared_roots for r in self.app_roots}
        self._root_chains.update({r: self.shared_roots for r in self.shared_roots})
        self.default_chain = self.app_roots + self.shared_roots

    def _index_python(self, path: Path) -> None:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            return
        imports: dict[str, str] = {}
        self.imports[path] = imports
        consts = self.constants.setdefault(path, {})
        prefixes = self.prefixes.setdefault(path, {})
        for stmt in tree.body:
            target = stmt.target if isinstance(stmt, ast.AnnAssign) else None
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
            if not isinstance(target, ast.Name):
                continue
            value = stmt.value
            where = Loc(path, target.lineno - 1, target.col_offset, target.end_col_offset)
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                consts[target.id] = (value.value, where)
            elif isinstance(value, ast.Call) and (_decorator_call(value) or ("",))[0] == "APIRouter":
                prefixes[target.id] = next((_str(k.value) or "" for k in value.keywords if k.arg == "prefix"), "")
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for a in node.names:
                    imports[a.asname or a.name] = node.module
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                v = node.value
                if self.resolve_template(v, path) is not None:
                    self.literals.append(
                        TemplateRef(v, Loc(path, node.lineno - 1, node.col_offset, node.end_col_offset), "literal")
                    )
            elif (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "globals"
            ):
                key = _str(node.slice)
                if key and key not in self.globals:
                    self.globals[key] = Loc(path, node.lineno - 1, node.col_offset, node.end_col_offset)
            elif isinstance(node, ast.ClassDef):
                self._index_class(path, node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._index_function(path, node)

    def _index_class(self, path: Path, node: ast.ClassDef) -> None:
        fields: dict[str, Loc] = {}
        annotations: dict[str, str] = {}
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                fields[stmt.target.id] = Loc(path, stmt.lineno - 1, stmt.col_offset, stmt.target.end_col_offset)
                annotations[stmt.target.id] = ast.unparse(stmt.annotation)
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decos = {ast.unparse(d).split("(")[0].split(".")[-1] for d in stmt.decorator_list}
                if decos & {"computed_field", "property", "cached_property"}:
                    fields[stmt.name] = Loc(path, stmt.lineno - 1, stmt.col_offset, stmt.col_offset + len(stmt.name))
                    annotations[stmt.name] = ast.unparse(stmt.returns) if stmt.returns else ""
        model = Model(
            name=node.name,
            loc=Loc(path, node.lineno - 1, node.col_offset, node.col_offset + len("class ") + len(node.name)),
            fields=fields,
            annotations=annotations,
            bases=[b for b in (_annotation_name(b) for b in node.bases) if b],
            module=path,
        )
        self.models.setdefault(node.name, []).append(model)

    def _index_function(self, path: Path, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        templates: list[str] = []
        route_name: str | None = None
        method: str | None = None
        route_path: str | None = None
        emits: list[Emit] = []
        for dec in node.decorator_list:
            dc = _decorator_call(dec)
            if not dc:
                continue
            fname, call, receiver = dc
            if fname == "render":
                tpl = _str(call.args[0]) if call.args else None
                for kw in call.keywords:
                    if kw.arg == "template":
                        tpl = _str(kw.value)
                    elif kw.arg == "partial" and _str(kw.value):
                        templates.append(_str(kw.value))  # type: ignore[arg-type]
                    elif kw.arg in ("hx_trigger", "hx_trigger_after_swap"):
                        v = kw.value
                        loc = Loc(path, v.lineno - 1, v.col_offset, v.end_col_offset)
                        emits.extend(Emit(n, loc, c, kw.arg.endswith("swap")) for n, c in event_names(v))
                if tpl:
                    templates.insert(0, tpl)
            elif fname in ROUTE_METHODS:
                method = fname.upper() if fname not in ("api_route", "route") else None
                raw = _str(call.args[0]) if call.args else None
                for kw in call.keywords:
                    if kw.arg == "name":
                        route_name = _str(kw.value)
                    elif kw.arg == "path":
                        raw = _str(kw.value)
                if raw is not None:
                    route_path = self.prefixes.get(path, {}).get(receiver or "", "") + raw
        if not templates and method is None and route_path is None:
            return
        self.routes.append(
            Route(
                func=node.name,
                name=route_name,
                loc=Loc(path, node.lineno - 1, node.col_offset, node.col_offset + len("def ") + len(node.name)),
                templates=tuple(templates),
                model=_annotation_name(node.returns),
                module=path,
                method=method,
                path=route_path,
                emits=tuple(emits),
            )
        )

    # ---- queries --------------------------------------------------------

    def template_at(self, path: Path) -> Template | None:
        return self.by_path.get(path.resolve())

    def app_dir(self, root: Path) -> Path:
        """The package an app root belongs to — `examples/fjkit-demo/app` for
        `examples/fjkit-demo/app/templates`. Its routes live under here."""
        return root.parent

    def chain_for(self, near: Template | Path | None) -> list[Path]:
        """The template roots visible from a template or a Python module, in the
        order `ChoiceLoader` searches them: the app's own, then plugins, then the
        kit. A file belonging to no application sees the shared roots only, which
        is right for the kit and for a plugin: their templates name their own."""
        if near is None:
            return self.default_chain
        if isinstance(near, Template):
            root = near.root or self.root_of(near.path)
            return self._root_chains.get(root, self.default_chain) if root else self.default_chain
        path = near.resolve()
        hit = self._chains.get(path)
        if hit is None:
            hit = next(
                (self._root_chains[root] for root in self.app_roots if path.is_relative_to(self.app_dir(root))),
                self.shared_roots or self.default_chain,
            )
            self._chains[path] = hit
        return hit

    def root_of(self, path: Path) -> Path | None:
        """The templates directory a file's name is relative to, if any."""
        return next((r for r in self.template_roots if path.resolve().is_relative_to(r)), None)

    def resolve_template(self, name: str, near: Template | Path | None = None) -> Template | None:
        """The template `name` means to whoever is asking.

        `near` is the file doing the naming; without it the default chain
        decides, which is only safe for a name no two applications share.
        """
        if name.startswith(FJKIT_NAMESPACE):
            kit = self.by_root.get(self.kit_root) if self.kit_root else None
            return kit.get(name[len(FJKIT_NAMESPACE) :]) if kit else None
        for root in self.chain_for(near):
            hit = self.by_root.get(root, {}).get(name)
            if hit is not None:
                return hit
        return None

    def resolve_model(self, name: str | None, module: Path) -> Model | None:
        if not name:
            return None
        candidates = self.models.get(name, [])
        if not candidates:
            return None
        for m in candidates:
            if m.module == module:
                return m
        dotted = self.imports.get(module, {}).get(name)
        if dotted:
            tail = Path(*dotted.split("."))
            for m in candidates:
                if m.module.with_suffix("").as_posix().endswith(tail.as_posix()):
                    return m
        return candidates[0]

    def model_fields(self, model: Model, seen: set[str] | None = None) -> dict[str, tuple[Model, Loc]]:
        """Own fields first, then inherited ones the class did not override."""
        seen = seen or set()
        seen.add(model.name)
        out = {k: (model, v) for k, v in model.fields.items()}
        for base in model.bases:
            if base in seen:
                continue
            bm = self.resolve_model(base, model.module)
            if bm:
                for k, v in self.model_fields(bm, seen).items():
                    out.setdefault(k, v)
        return out

    def routes_rendering(self, tpl: Template) -> list[Route]:
        """Routes whose `@render` names this very template — resolved in each
        route's own chain, so a name two applications share does not merge them."""
        return [
            r
            for r in self.routes
            if any(n == tpl.name and _is(self.resolve_template(n, r.module), tpl) for n in r.templates)
        ]

    def parents(self, tpl: Template) -> list[Template]:
        """Templates whose context reaches this one: those that include or extend it."""
        return [
            t
            for t in self.by_path.values()
            if any(
                r.name == tpl.name and r.kind in ("include", "extends") and _is(self.resolve_template(r.name, t), tpl)
                for r in t.refs
            )
        ]

    def context_routes(self, tpl: Template) -> list[Route]:
        """Every route whose returned model becomes the context this template sees."""
        out: list[Route] = []
        seen: set[Path] = set()

        def walk(t: Template) -> None:
            if t.path in seen:
                return
            seen.add(t.path)
            out.extend(self.routes_rendering(t))
            for parent in self.parents(t):
                walk(parent)

        walk(tpl)
        uniq: dict[tuple[Path, int], Route] = {}
        for r in out:
            uniq.setdefault((r.loc.path, r.loc.line), r)
        return list(uniq.values())

    def context_models(self, tpl: Template) -> list[tuple[Route, Model]]:
        out = []
        for r in self.context_routes(tpl):
            m = self.resolve_model(r.model, r.module)
            if m:
                out.append((r, m))
        return out

    def descendants(self, tpl: Template) -> list[Template]:
        """Templates that share this one's context: what it includes or extends, recursively."""
        out: list[Template] = []
        seen: set[Path] = set()

        def walk(t: Template) -> None:
            if t.path in seen:
                return
            seen.add(t.path)
            out.append(t)
            for r in t.refs:
                if r.kind in ("include", "extends"):
                    target = self.resolve_template(r.name, t)
                    if target is not None:
                        walk(target)

        walk(tpl)
        return out

    def references_to_template(self, tpl: Template) -> list[tuple[str, Loc]]:
        """Every place this template is named: Jinja tags, `@render`, and other
        Python string literals — each resolved from the file that wrote it."""
        out: list[tuple[str, Loc]] = []
        for t in self.by_path.values():
            for r in t.refs:
                if r.name == tpl.name and _is(self.resolve_template(r.name, t), tpl):
                    out.append((f"{r.kind} in {t.name}", r.loc))
        for lit in self.literals:
            if lit.name == tpl.name and _is(self.resolve_template(lit.name, lit.loc.path), tpl):
                out.append(("python", lit.loc))
        return out

    def route_by_name(self, name: str) -> Route | None:
        return next((r for r in self.routes if r.name == name), None)

    # ---- htmx: URLs, events and targets ---------------------------------

    def routes_near(self, near: Template | Path | None) -> list[Route]:
        """The routes an application mounts: its own, and every distribution's —
        a plugin's routes are visible from each app, an app's from itself only."""
        chain = self.chain_for(near)
        return [r for r in self.routes if self.chain_for(r.module) in (chain, self.shared_roots)]

    def routes_for_url(self, url: str, near: Template | Path | None = None) -> list[Route]:
        """Routes whose path a literal `hx-get="/tasks/7/advance"` would reach.
        Several when methods differ on one path — GET and DELETE on `/tasks/{id}`."""
        return [r for r in self.routes_near(near) if r.matches(url)]

    def _module_path(self, dotted: str) -> Path | None:
        tail = Path(*dotted.split(".")).as_posix()
        return next((m for m in self.imports if m.with_suffix("").as_posix().endswith(tail)), None)

    def constant(self, name: str, module: Path) -> tuple[str, Loc] | None:
        """A module-level string constant, by name, as seen from `module`: its own
        definition, or the one an `from … import` brought in."""
        own = self.constants.get(module, {}).get(name)
        if own:
            return own
        dotted = self.imports.get(module, {}).get(name)
        source = self._module_path(dotted) if dotted else None
        return self.constants.get(source, {}).get(name) if source else None

    def event_name(self, emit: Emit, module: Path) -> str | None:
        """The string an `Emit` raises — the literal, or the constant's value."""
        if not emit.is_const:
            return emit.name
        hit = self.constant(emit.name, module)
        return hit[0] if hit else None

    def events(self, near: Template | Path | None = None) -> dict[str, list[tuple[Route, Emit]]]:
        """Every event name a route raises, with the routes raising it — those
        the asking file's application mounts when `near` is given."""
        if near is not None:
            visible = {id(r) for r in self.routes_near(near)}
            return {k: [(r, e) for r, e in v if id(r) in visible] for k, v in self.events().items() if v}
        if self._events is None:
            out: dict[str, list[tuple[Route, Emit]]] = {}
            for r in self.routes:
                for e in r.emits:
                    name = self.event_name(e, r.module)
                    if name:
                        out.setdefault(name, []).append((r, e))
            self._events = out
        return self._events

    def event_constants(self, name: str) -> list[Loc]:
        """Where the constants holding this event's string are defined."""
        return [loc for consts in self.constants.values() for v, loc in consts.values() if v == name]

    def listeners(self, name: str, near: Template | Path | None = None) -> list[Loc]:
        """Every template place that names this event: a token of an `hx-trigger`
        value, or a string in code such as `subscribe(request, x, ["task-changed"])`.
        Quoted text only, so a word in prose does not count."""
        pat = rf"(?<![\w-]){re.escape(name)}(?![\w-])"
        out: list[Loc] = []
        for t in self._templates_in(self.chain_for(near)):
            lines = _Lines(t.text)
            # Comments blanked first: prose has apostrophes, and `sibling's … it's`
            # would otherwise read as one single-quoted string. Outside Jinja code
            # only double quotes count, for the same reason.
            text = _COMMENT.sub(_blank, t.text)
            code = [(m.start(), m.end()) for m in _CODE.finditer(text)]
            spans = [
                (m.start(), m.end())
                for m in _STRING.finditer(text)
                if m.group(0)[0] == '"' or any(a <= m.start() and m.end() <= b for a, b in code)
            ]
            for m in re.finditer(pat, text):
                if any(a < m.start() and m.end() < b for a, b in spans):
                    line, col = lines.pos(m.start())
                    out.append(Loc(t.path, line, col, col + len(name)))
        return out

    def ids_named(self, name: str, near: Template | Path | None = None) -> list[Loc]:
        """Elements with `id="name"`, in the templates the asking file can see.

        A dynamic id — `id="job-{{ job.id }}"` — matches a target that shares
        its literal prefix, `#job-{{ x }}` or `#job-7`; exact ids match exactly.
        """
        out: list[Loc] = []
        static = name.split("{{", 1)[0]
        for t in self._templates_in(self.chain_for(near)):
            for value, loc in t.ids:
                v_static = value.split("{{", 1)[0]
                dynamic = "{{" in value or "{{" in name
                if value == name or (dynamic and v_static and static and (v_static == static)):
                    out.append(loc)
        return out

    def target_references(self, name: str, near: Template | Path | None = None) -> list[Loc]:
        """Every `#name` a template writes into an `hx-*` value, attribute or kwarg."""
        pat = rf"\bhx[-_]\w+\s*=\s*[\"']#{re.escape(name.split('{{', 1)[0])}"
        out: list[Loc] = []
        for t in self._templates_in(self.chain_for(near)):
            # Attributes and kwargs both, so the raw text — with comments blanked,
            # or a macro's signature note quoting `hx_target="#board"` would count.
            text = _COMMENT.sub(_blank, t.text)
            lines = _Lines(t.text)
            for m in re.finditer(pat, text):
                line, col = lines.pos(m.start())
                hash_at = t.text.splitlines()[line].index("#", col)
                out.append(Loc(t.path, line, hash_at, hash_at + 1 + len(name)))
        return out

    def _templates_in(self, chain: list[Path]) -> list[Template]:
        return [t for r in chain for t in self.by_root.get(r, {}).values()]

    def macro_references(self, tpl: Template, macro: str) -> list[Loc]:
        out: list[Loc] = []
        for t in self.by_path.values():
            imports = {a: mn for a, (tn, mn) in t.imports.items() if _is(self.resolve_template(tn, t), tpl)}
            aliases = [a for a, mn in imports.items() if mn == macro] + ([macro] if _is(t, tpl) else [])
            modules = [a for a, mn in imports.items() if mn == ""]
            pats = [rf"\b{re.escape(a)}\s*\(" for a in aliases] + [
                rf"\b{re.escape(m)}\.{re.escape(macro)}\s*\(" for m in modules
            ]
            out.extend(self.word_occurrences(t, pats))
        return out

    @staticmethod
    def word_occurrences(t: Template, patterns: list[str], code_only: bool = True) -> list[Loc]:
        """Matches of `patterns`; by default only inside `{{ }}` / `{% %}` and outside string literals."""
        lines = _Lines(t.text)
        text = t.code() if code_only else t.text
        out = []
        for pat in patterns:
            for m in re.finditer(pat, text):
                line, col = lines.pos(m.start())
                out.append(Loc(t.path, line, col, col + len(m.group(0))))
        return sorted(out, key=lambda loc: (loc.line, loc.col))
