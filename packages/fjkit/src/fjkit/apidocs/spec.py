"""The OpenAPI document, flattened into what a template can loop over.

A schema is `$ref`s into `components`, `allOf` chains and `anyOf` unions.
Resolving those in a template means recursive macros, `strict_undefined`
landmines, and a page that fails to render because one endpoint used `oneOf`. So
the whole document becomes plain frozen dataclasses here, once per process, and
the template only reads attributes that exist.

Built from `app.openapi()`, which FastAPI already caches, so this runs once. It
stays correct when a route changes, because it is the same document
`/openapi.json` serves.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Field",
    "Model",
    "Operation",
    "Param",
    "ResponseDoc",
    "SecurityScheme",
    "Server",
    "Shape",
    "Spec",
    "TagGroup",
    "build",
]

#: Anything outside this set is replaced in an operation's URL slug. Limited to
#: the characters that survive a path segment untouched, so the docs URL never
#: needs escaping and can be copied out of the address bar.
_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")

#: How deep an example generator follows `$ref`s before giving up and emitting
#: a placeholder. A self-referential model — a tree node, a comment with replies
#: — is normal and must not hang the docs page.
_MAX_DEPTH = 6

#: What each JSON type looks like when the schema gave no example of its own.
_PLACEHOLDERS: dict[str, Any] = {
    "string": "string",
    "integer": 0,
    "number": 0.0,
    "boolean": True,
    "array": [],
    "object": {},
    "null": None,
}

#: The methods the console offers. `trace` and `connect` are excluded: no
#: FastAPI app routes them, and OpenAPI puts other keys (`parameters`,
#: `summary`) alongside the methods in a path item.
METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

#: The body media types the console takes apart into fields rather than handing
#: over as one blob. `multipart` is here because the browser already has a
#: control for a file: the field becomes `<input type="file">`, the console
#: re-encodes what was uploaded, and the endpoint sees the multipart body it
#: declared.
FORM_MEDIA = "application/x-www-form-urlencoded"
MULTIPART_MEDIA = "multipart/form-data"
_FIELD_MEDIA = (FORM_MEDIA, MULTIPART_MEDIA)

#: How OpenAPI spells "this is a file": the one property type that cannot be
#: typed into a box, and so the one that decides a body goes up as multipart.
#:
#: There are two spellings and a document uses only one. OpenAPI 3.0 said
#: `format: binary`; 3.1 dropped it, because JSON Schema has no such format, and
#: says `contentMediaType` instead. FastAPI emits 3.1 for an `UploadFile`, so
#: reading only `format` finds nothing and every upload renders as a text box,
#: which posts the filename as a string and fails inside the endpoint, a long
#: way from the cause.
BINARY_FORMAT = "binary"
_BINARY_KEY = "contentMediaType"

#: What a schema's bounds read as on screen. Ordered, because "≥ 1 · ≤ 64 chars"
#: is a range and "≤ 64 chars · ≥ 1" is two adjacent facts. Symbols rather than
#: the JSON Schema keywords: the reader is told which values are allowed, not
#: which vocabulary the document used to say so.
_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("minimum", "≥ {}"),
    ("exclusiveMinimum", "> {}"),
    ("maximum", "≤ {}"),
    ("exclusiveMaximum", "< {}"),
    ("minLength", "≥ {} chars"),
    ("maxLength", "≤ {} chars"),
    ("minItems", "≥ {} items"),
    ("maxItems", "≤ {} items"),
    ("multipleOf", "multiple of {}"),
    ("pattern", "matches {}"),
)

#: Which HTML control a parameter gets. A closed lookup rather than passing the
#: JSON type through, because the value lands in `<input type="…">`, where an
#: unknown type becomes `text` in some browsers and nothing in others.
_CONTROLS = {
    "integer": "number",
    "number": "number",
    "string": "text",
    "boolean": "select",
    "array": "text",
    "object": "text",
}


@dataclass(frozen=True, slots=True)
class Param:
    """One path, query, header or cookie parameter."""

    name: str
    location: str
    required: bool
    type: str
    description: str = ""
    #: Rendered into the field, so a caller starts from a working value rather
    #: than an empty box.
    default: str = ""
    #: Non-empty turns the field into a `<select>`.
    choices: tuple[str, ...] = ()
    deprecated: bool = False
    #: `date-time`, `uuid`, `binary`, … — the half of a string's type that says
    #: what shape the string must be, and the only thing separating a field to
    #: type into from one to attach a file to.
    format: str = ""
    #: `≥ 1 · ≤ 64 chars`, already rendered. The document's bounds are the
    #: difference between guessing at a value and sending one that validates.
    constraints: str = ""
    #: The document's own `example`, when it wrote one that is not the default.
    example: str = ""

    @property
    def control(self) -> str:
        """Pick the try-it control: `"select"`, `"file"`, `"number"` or `"text"`."""
        if self.format == BINARY_FORMAT:
            return "file"
        if self.choices:
            return "select"
        return _CONTROLS.get(self.type, "text")

    @property
    def multi(self) -> bool:
        """Whether this parameter takes more than one value.

        An array parameter is `?tag=a&tag=b` on the wire — one name repeated,
        which is what FastAPI parses `tags: list[str] = Query(())` back out of.
        A single box holding `a,b` would send the literal string "a,b" and the
        endpoint would receive a one-element list, so the console splits on
        commas and newlines, and the field says so.
        """
        return self.type == "array" and not self.choices and self.format != BINARY_FORMAT

    @property
    def detail(self) -> str:
        """Everything about this parameter except its name and its prose.

        One string, because it is one line under a field label; building it at
        each call site is how two of them start to disagree.
        """
        return f"{self.location} · {self.type_detail}"

    @property
    def type_detail(self) -> str:
        """`detail` without the location, for the table that has a column for it.

        Repeating "form" in the In column and again at the front of the Type
        column is the duplication that makes a reference table look mechanically
        generated.
        """
        parts = [self.type + (f" ({self.format})" if self.format else "")]
        if self.required:
            parts.append("required")
        if self.deprecated:
            parts.append("deprecated")
        if self.constraints:
            parts.append(self.constraints)
        return " · ".join(parts)

    @property
    def pairs(self) -> tuple[tuple[str, str], ...]:
        """`choices` as the (value, label) pairs `select_field` takes."""
        return tuple((c, c) for c in self.choices)

    @property
    def field_name(self) -> str:
        """The form field this parameter arrives back in.

        Namespaced by location, because a `limit` query parameter and a `limit`
        header are different things and an OpenAPI document may declare both.
        """
        return f"p.{self.location}.{self.name}"


@dataclass(frozen=True, slots=True)
class Field:
    """One property of a model — a row in the Schema view.

    Not a `Param`: a parameter is what the console renders a control for, a
    field is what a reader is told about, and the two differ on the keywords
    that matter here — `readOnly`, `writeOnly`, and a `ref` that links to
    another model rather than naming a type.
    """

    name: str
    type: str
    required: bool = False
    description: str = ""
    format: str = ""
    constraints: str = ""
    choices: tuple[str, ...] = ()
    default: str = ""
    #: The name of the model this field is, when it is one. The Schema view
    #: renders it as a link rather than recursing: a `Task` with an
    #: `owner: User` with an `avatar: Image` is three tables deep before anyone
    #: scrolls, and the reader wanted the first one.
    ref: str = ""
    nullable: bool = False
    deprecated: bool = False
    read_only: bool = False
    write_only: bool = False

    @property
    def detail(self) -> str:
        """The type line: what it is, then everything qualifying it."""
        return " · ".join(x for x in (self.type + (f" ({self.format})" if self.format else ""), self.qualifiers) if x)

    @property
    def qualifiers(self) -> str:
        """`detail` without the type, for the row that renders the type as a link.

        Split out rather than sliced back off `detail` in the template: a
        property whose name is a substring of one of its own qualifiers would
        make that surgery wrong. The cost is one method.
        """
        parts: list[str] = []
        if self.nullable:
            parts.append("nullable")
        if self.required:
            parts.append("required")
        if self.read_only:
            # The difference between a field that belongs in a request body and
            # one that is rejected there. Swagger shows it for the same reason.
            parts.append("read-only")
        if self.write_only:
            parts.append("write-only")
        if self.deprecated:
            parts.append("deprecated")
        if self.constraints:
            parts.append(self.constraints)
        return " · ".join(parts)


@dataclass(frozen=True, slots=True)
class Shape:
    """What a body is, for the Schema half of an Example/Schema pair.

    The document describes a body twice: as a value that could be sent, and as
    the rules that value must obey. A reference offering only the first leaves
    the reader guessing from an example. This is the second, flattened one
    level: the properties of the object, or of the objects in the array, with
    anything deeper left as a link.
    """

    label: str
    #: The named model, when the schema was a `$ref` to one, so the view can
    #: link to the full definition instead of restating it.
    model: str = ""
    array: bool = False
    fields: tuple[Field, ...] = ()
    #: The schema itself, pretty-printed. The last resort for a shape nothing
    #: here can flatten — a union, a free-form object — and the thing to paste
    #: into a validator.
    source: str = ""

    @property
    def has_rows(self) -> bool:
        return bool(self.fields)


@dataclass(frozen=True, slots=True)
class Model:
    """One entry from `components.schemas` — a Swagger "Schemas" row.

    Every generated client, contract test and hand-written payload is built
    against these. An API reference that documents the endpoints but not the
    types they exchange has documented the easy half.
    """

    name: str
    slug: str
    description: str = ""
    #: `object` or `enum`. An alias for a scalar is rendered as an object with
    #: no rows and its `source` showing, which is honest about there being
    #: nothing to expand.
    kind: str = "object"
    fields: tuple[Field, ...] = ()
    choices: tuple[str, ...] = ()
    example: str = ""
    source: str = ""
    #: Operation ids that mention this model, so a type can be read back to the
    #: endpoints that carry it. The document holds this relation and most
    #: viewers never show it.
    used_by: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Server:
    """One entry from the document's `servers`.

    Shown, never selected. Swagger's server dropdown chooses where `fetch()`
    aims; this console replays in-process against the app that is answering, so
    a dropdown here would change nothing. The list still does what it was
    written for: telling a reader which base URL to point a real client at.
    """

    url: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class ResponseDoc:
    """One documented status code."""

    status: str
    description: str
    media_type: str = ""
    example: str = ""
    #: Name and description of each header the document promises. Almost the
    #: only place a `Location`, a `Retry-After` or a rate-limit budget is
    #: written down, and the panel below shows beside it what came back.
    headers: tuple[tuple[str, str], ...] = ()
    shape: Shape | None = None
    #: The document's named examples beyond the one shown by default, as
    #: `(label, value)`. An author who wrote out the empty case, the full case
    #: and the error case wrote three things worth reading; a viewer showing one
    #: throws the other two away.
    examples: tuple[tuple[str, str], ...] = ()

    @property
    def tone(self) -> str:
        """Map the status to a badge variant. Closed set — see `ui/data.html`."""
        if not self.status.isdigit():
            return "secondary"
        code = int(self.status)
        if code >= 500:
            return "destructive"
        if code >= 400:
            return "warning"
        if code >= 300:
            return "info"
        return "success"


@dataclass(frozen=True, slots=True)
class SecurityScheme:
    """What the document says authenticates a call.

    Shown because it is the contract other clients read, and captioned on the
    page because it is rarely the whole story: an app whose sessions come from
    `fjkit.auth` authenticates with a cookie the document does not describe and
    Swagger UI cannot send. The page names both.
    """

    name: str
    type: str
    detail: str = ""
    description: str = ""


@dataclass(frozen=True, slots=True)
class Operation:
    """One method on one path, with everything the page and the console need."""

    id: str
    method: str
    path: str
    summary: str
    description: str = ""
    tags: tuple[str, ...] = ()
    deprecated: bool = False
    params: tuple[Param, ...] = ()
    body_media: str = ""
    body_required: bool = False
    body_example: str = ""
    #: A form body, broken back out into the fields it was declared as. Empty
    #: for JSON and for anything else that has to be typed whole.
    body_fields: tuple[Param, ...] = ()
    responses: tuple[ResponseDoc, ...] = ()
    security: tuple[str, ...] = ()
    #: The `operationId` as the document spells it — the name every generated
    #: client gives this call. The `id` beside it is a URL slug and may have
    #: been renamed to break a collision, so the two are not interchangeable.
    operation_id: str = ""
    #: Every media type the body was declared in, not only the one the console
    #: picked. Swagger puts these in a dropdown; here it is a line of text,
    #: because the console composes exactly one of them and naming it is more
    #: use than offering a choice that does not work.
    media_types: tuple[str, ...] = ()
    body_shape: Shape | None = None
    body_examples: tuple[tuple[str, str], ...] = ()
    external_url: str = ""
    external_label: str = ""

    @property
    def label(self) -> str:
        return self.summary or f"{self.method} {self.path}"

    @property
    def has_body(self) -> bool:
        return bool(self.body_media)

    @property
    def multipart(self) -> bool:
        """Whether the body must go up as multipart, i.e. it carries a file."""
        return self.body_media == MULTIPART_MEDIA

    @property
    def haystack(self) -> str:
        """Everything the sidebar filter matches against, lowercased once.

        People type the path and the summary, but also the tag and — for anyone
        who has read the generated client — the operation id. Built here rather
        than in the filter, because it is a property of the operation and the
        filter runs once per keystroke.
        """
        return " ".join((self.method, self.path, self.summary, self.operation_id, *self.tags)).lower()

    @property
    def has_raw_body(self) -> bool:
        """Whether the console must offer a text box rather than fields.

        A `Form()` endpoint is the common shape in a fjkit app — every htmx form
        posts to one — and asking someone to hand-write `title=x&owner=y` into a
        textarea, correctly percent-encoded, would be worse than curl. So a form
        body becomes fields, and this is true only for bodies that are one blob:
        JSON, and the media types nothing here can take apart.
        """
        return self.has_body and not self.body_fields


@dataclass(frozen=True, slots=True)
class TagGroup:
    """The operations under one tag, in document order."""

    name: str
    description: str
    operations: tuple[Operation, ...]
    external_url: str = ""
    external_label: str = ""


@dataclass(slots=True)
class Spec:
    """The whole document, ready to render."""

    title: str
    version: str
    description: str = ""
    groups: tuple[TagGroup, ...] = ()
    schemes: tuple[SecurityScheme, ...] = ()
    #: id -> operation, so the detail route is a dict lookup rather than a scan.
    index: Mapping[str, Operation] = field(default_factory=dict)
    servers: tuple[Server, ...] = ()
    models: tuple[Model, ...] = ()
    #: slug -> model, the same trick `index` plays for operations.
    model_index: Mapping[str, Model] = field(default_factory=dict)
    #: name -> model. A `$ref` names a model; a URL needs its slug, and the
    #: templates have only the name — so the lookup lives here rather than as
    #: string surgery in Jinja.
    by_name: Mapping[str, Model] = field(default_factory=dict)
    #: The masthead facts OpenAPI carries and few viewers render: who to ask,
    #: which licence applies, what the terms are. They are in the document
    #: because somebody meant them to be read.
    contact: tuple[tuple[str, str], ...] = ()
    license_name: str = ""
    license_url: str = ""
    terms_url: str = ""
    external_url: str = ""
    external_label: str = ""

    @property
    def count(self) -> int:
        return len(self.index)

    @property
    def model_groups(self) -> tuple[tuple[str, tuple[Model, ...]], ...]:
        """`models`, split by kind, so the sidebar is not one long run.

        Objects and enums are different things to look up: an object is a shape
        to send or parse, an enum is a closed vocabulary to check a spelling
        against. In thirty names sorted alphabetically the five enums are
        scattered through the list, which is when the classification earns its
        place.

        Objects first: they are the majority and the reason anyone opened the
        branch. Declaration order inside each, because that is the order the
        document wrote them and re-sorting throws it away.

        Built here rather than with `selectattr` in the template, for the same
        reason `build()` exists: reshaping data is not markup's job, and a
        template reaching for a filter chain is one refactor from needing a
        second.
        """
        kinds = (("Objects", "object"), ("Enums", "enum"))
        groups = tuple((label, tuple(m for m in self.models if m.kind == kind)) for label, kind in kinds)
        return tuple((label, members) for label, members in groups if members)

    def filter(self, query: str) -> tuple[TagGroup, ...]:
        """`groups`, keeping only the operations that match `query`.

        Substring, case-insensitive, over path, summary, tag and operation id —
        the same match Swagger's filter box makes, minus its tag-only mode. A
        group with nothing left is dropped rather than rendered empty: typing is
        meant to shorten the list.

        Filtering server-side costs nothing here. The server already renders the
        list, an app with two hundred routes is the worst case for shipping all
        of them to the client to hide most of them, and `hx-get` on the input
        costs one attribute against a script that would have to be written,
        shipped and kept working with the DOM.
        """
        needle = query.strip().lower()
        if not needle:
            return self.groups
        kept: list[TagGroup] = []
        for group in self.groups:
            matched = tuple(op for op in group.operations if needle in op.haystack)
            if matched:
                kept.append(
                    TagGroup(
                        name=group.name,
                        description=group.description,
                        operations=matched,
                        external_url=group.external_url,
                        external_label=group.external_label,
                    )
                )
        return tuple(kept)


def build(schema: Mapping[str, Any], *, skip_prefix: str = "") -> Spec:
    """Flatten `app.openapi()`.

    `skip_prefix` drops the docs plugin's own routes. They already carry
    `include_in_schema=False`, so this is a second guard — but without it an app
    that mounts a second docs instance, or hand-writes its schema, would get a
    console that can call itself.
    """
    components = schema.get("components") or {}
    info = schema.get("info") or {}

    tag_order: list[str] = []
    tag_text: dict[str, str] = {}
    tag_links: dict[str, tuple[str, str]] = {}
    for entry in schema.get("tags") or ():
        name = str(entry.get("name", ""))
        if name:
            tag_order.append(name)
            tag_text[name] = str(entry.get("description", ""))
            tag_links[name] = _external(entry.get("externalDocs"))

    by_tag: dict[str, list[Operation]] = {}
    index: dict[str, Operation] = {}

    for path, item in (schema.get("paths") or {}).items():
        if skip_prefix and str(path).startswith(skip_prefix):
            continue
        if not isinstance(item, Mapping):
            continue
        shared = item.get("parameters") or ()
        for method in METHODS:
            body = item.get(method)
            if not isinstance(body, Mapping):
                continue
            operation = _operation(
                method=method,
                path=str(path),
                body=body,
                shared_params=shared,
                components=components,
                taken=index,
            )
            index[operation.id] = operation
            for tag in operation.tags:
                by_tag.setdefault(tag, []).append(operation)

    # Declared tags first, in the document's own order, then whatever a route
    # invented, alphabetically. An app that wrote a `tags=` list on its
    # FastAPI() is describing an information architecture, and re-sorting it
    # would throw that away.
    ordered = [t for t in tag_order if t in by_tag]
    ordered += sorted(t for t in by_tag if t not in tag_order)

    groups = tuple(
        TagGroup(
            name=t,
            description=tag_text.get(t, ""),
            operations=tuple(by_tag[t]),
            external_url=tag_links.get(t, ("", ""))[0],
            external_label=tag_links.get(t, ("", ""))[1],
        )
        for t in ordered
    )

    models = _models(components.get("schemas") or {}, components, index)
    contact = info.get("contact") or {}
    licence = info.get("license") or {}
    external_url, external_label = _external(schema.get("externalDocs"))

    return Spec(
        title=str(info.get("title", "API")),
        version=str(info.get("version", "")),
        description=str(info.get("description", "")),
        groups=groups,
        schemes=_schemes(components.get("securitySchemes") or {}),
        index=index,
        servers=tuple(
            Server(url=str(s.get("url", "")), description=str(s.get("description", "")))
            for s in (schema.get("servers") or ())
            if isinstance(s, Mapping) and s.get("url")
        ),
        models=models,
        model_index={m.slug: m for m in models},
        by_name={m.name: m for m in models},
        contact=tuple(
            (label, str(contact[key]))
            for key, label in (("name", "name"), ("email", "email"), ("url", "url"))
            if isinstance(contact, Mapping) and contact.get(key)
        ),
        license_name=str(licence.get("name", "")) if isinstance(licence, Mapping) else "",
        license_url=str(licence.get("url", "")) if isinstance(licence, Mapping) else "",
        terms_url=str(info.get("termsOfService", "")),
        external_url=external_url,
        external_label=external_label,
    )


def _external(raw: Any) -> tuple[str, str]:
    """Read an `externalDocs` object as (url, label).

    The one place a document can say "the real explanation is elsewhere". A
    viewer that drops it strips the author's link to their own prose.
    """
    if not isinstance(raw, Mapping) or not raw.get("url"):
        return "", ""
    return str(raw["url"]), str(raw.get("description") or "Read more")


def _operation(
    *,
    method: str,
    path: str,
    body: Mapping[str, Any],
    shared_params: Sequence[Any],
    components: Mapping[str, Any],
    taken: Mapping[str, Operation],
) -> Operation:
    params = tuple(
        _param(p, components) for p in (*shared_params, *(body.get("parameters") or ())) if isinstance(p, Mapping)
    )
    media, required, example, form_fields, shape, offered, named = _request_body(
        body.get("requestBody"), components
    )
    external_url, external_label = _external(body.get("externalDocs"))

    # `["default"]` is FastAPI's tag for an untagged route. Naming the group
    # that beats leaving it unnamed: a page with one unnamed section reads as
    # broken.
    tags = tuple(str(t) for t in (body.get("tags") or ())) or ("default",)

    return Operation(
        id=_unique(_slug(body.get("operationId") or f"{method}-{path}"), taken),
        operation_id=str(body.get("operationId", "")),
        media_types=offered,
        body_shape=shape,
        body_examples=named,
        external_url=external_url,
        external_label=external_label,
        method=method.upper(),
        path=path,
        summary=str(body.get("summary", "")),
        description=str(body.get("description", "")),
        tags=tags,
        deprecated=bool(body.get("deprecated", False)),
        params=params,
        body_media=media,
        body_required=required,
        body_example=example,
        body_fields=form_fields,
        responses=_responses(body.get("responses") or {}, components),
        security=tuple(name for entry in (body.get("security") or ()) for name in entry),
    )


def _param(raw: Mapping[str, Any], components: Mapping[str, Any]) -> Param:
    resolved = _effective(raw.get("schema") or {}, components)
    kind = _type_of(resolved)
    default = resolved.get("default", raw.get("example"))
    choices = tuple(_scalar(v) for v in resolved.get("enum", ()) if v is not None)
    if not choices and kind == "boolean":
        # A checkbox cannot express the third state a query parameter has:
        # absent. A select of `true`/`false`/blank can, and "leave it out" is
        # the answer that matters most on an optional flag.
        choices = ("true", "false")
    # `example` beside a schema shows a value that works, which is a different
    # statement from `default` and worth keeping when both are present: the
    # field prefills with the default and shows a real value underneath.
    example = raw.get("example", resolved.get("example"))
    return Param(
        name=str(raw.get("name", "")),
        location=str(raw.get("in", "query")),
        required=bool(raw.get("required", raw.get("in") == "path")),
        type=kind,
        description=str(raw.get("description", "")),
        default="" if default is None else _scalar(default),
        choices=choices,
        deprecated=bool(raw.get("deprecated", False)),
        format=_format_of(resolved),
        constraints=_constraints(resolved),
        example="" if example is None or example == default else _scalar(example),
    )


def _format_of(schema: Mapping[str, Any]) -> str:
    """Read the schema's `format`, folding in 3.1's way of saying "binary"."""
    declared = str(schema.get("format", ""))
    if not declared and schema.get(_BINARY_KEY):
        return BINARY_FORMAT
    return declared


def _constraints(schema: Mapping[str, Any]) -> str:
    """Render the schema's bounds as one line of prose.

    Each of these is a way for a call to be rejected with a 422 the reference
    could have prevented. Swagger shows them; without them a reader finds out
    about `maxLength` from the error.
    """
    return " · ".join(text.format(schema[key]) for key, text in _CONSTRAINTS if schema.get(key) is not None)


def _named(entry: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    """Read a media-type object's `examples` map as (label, pretty value) pairs.

    OpenAPI lets one body carry several worked examples, and FastAPI exposes
    that as `openapi_examples=`. Somebody who wrote out "minimal", "with an
    owner" and "the one that 422s" wrote three things worth reading; Swagger
    gives them a dropdown, and showing only the first throws two away.
    """
    examples = entry.get("examples")
    if not isinstance(examples, Mapping):
        return ()
    out: list[tuple[str, str]] = []
    for name, body in examples.items():
        if not isinstance(body, Mapping) or "value" not in body:
            continue
        # The summary when the author wrote one: it is prose meant to label
        # this example, which the key rarely is.
        out.append((str(body.get("summary") or name), _pretty(body["value"])))
    return tuple(out)


def _request_body(
    raw: Any, components: Mapping[str, Any]
) -> tuple[str, bool, str, tuple[Param, ...], Shape | None, tuple[str, ...], tuple[tuple[str, str], ...]]:
    if not isinstance(raw, Mapping):
        return "", False, "", (), None, (), ()
    content = raw.get("content") or {}
    if not isinstance(content, Mapping) or not content:
        return "", False, "", (), None, (), ()

    offered = tuple(str(m) for m in content)

    # A body with a file in it can go up only one way, so multipart wins over
    # JSON when the document offers both; otherwise the console would render the
    # JSON branch with no control for the upload the endpoint exists for.
    # Failing that, JSON when it is offered, and whatever came first when it is
    # not: a form-only endpoint is the usual case in a fjkit app.
    media = next(
        (m for m in content if m == MULTIPART_MEDIA),
        next((m for m in content if "json" in m), next(iter(content))),
    )
    entry = content.get(media) or {}
    required = bool(raw.get("required", False))
    shape = _shape(entry.get("schema"), components)
    named = _named(entry)

    if media in _FIELD_MEDIA:
        fields = _form_fields(entry.get("schema") or {}, components)
        if fields:
            return str(media), required, "", fields, shape, offered, named

    # The document's own example first, then the first one it named, then one
    # worked out from the schema: a value somebody wrote beats one this module
    # invented.
    if entry.get("example") is not None:
        text = _pretty(entry["example"])
        rest = named
    elif named:
        text, rest = named[0][1], named[1:]
    else:
        text, rest = _pretty(_example(entry.get("schema") or {}, components, 0)), ()
    return str(media), required, text, (), shape, offered, rest


def _form_fields(schema: Mapping[str, Any], components: Mapping[str, Any]) -> tuple[Param, ...]:
    """Read a form body's properties as parameters the console can render.

    The schema for `Annotated[str, Form()]` parameters is an ordinary object
    with `properties` and `required`, so the same `Param` that describes a query
    parameter describes one of these: enums become selects, integers become
    number boxes, and defaults prefill. `location="form"` tells `_compose` to
    encode the value into the body rather than onto the URL.

    A `multipart` body arrives here too, distinguished only by one or more of
    its properties being `format: binary`. Those become `<input type="file">`
    through the same `Param.control` lookup as everything else, which is why
    supporting uploads cost a branch rather than a parallel code path.
    """
    resolved = _resolve(schema, components, 0)
    properties = resolved.get("properties")
    if not isinstance(properties, Mapping) or not properties:
        return ()
    required = set(resolved.get("required") or ())
    return tuple(
        _param(
            {"name": str(name), "in": "form", "required": str(name) in required, "schema": sub},
            components,
        )
        for name, sub in properties.items()
    )


def _responses(raw: Mapping[str, Any], components: Mapping[str, Any]) -> tuple[ResponseDoc, ...]:
    docs: list[ResponseDoc] = []
    for status, entry in raw.items():
        if not isinstance(entry, Mapping):
            continue
        content = entry.get("content") or {}
        media = next((m for m in content if "json" in m), next(iter(content), ""))
        payload = (content.get(media) or {}) if media else {}
        # Same order of preference as a request body: what the document showed,
        # then the first thing it named, then something worked out from the
        # schema. The remaining named ones stay, as tabs beside it.
        named = _named(payload)
        if payload.get("example") is not None:
            text = _pretty(payload["example"])
        elif named:
            text, named = named[0][1], named[1:]
        elif payload.get("schema") is not None:
            text = _pretty(_example(payload["schema"], components, 0))
        else:
            text = ""
        docs.append(
            ResponseDoc(
                status=str(status),
                description=str(entry.get("description", "")),
                media_type=str(media),
                example=text,
                examples=named,
                headers=tuple(
                    (str(name), str(spec_.get("description", "")) if isinstance(spec_, Mapping) else "")
                    for name, spec_ in (entry.get("headers") or {}).items()
                ),
                shape=_shape(payload.get("schema"), components),
            )
        )
    # Numeric codes ascending, then `default` and anything else. Sorting the
    # whole thing as strings would put "422" before "5XX" but also "200" after
    # "1XX", which is not the order a response table is read in.
    docs.sort(key=lambda d: (0, int(d.status)) if d.status.isdigit() else (1, 0))
    return tuple(docs)


def _schemes(raw: Mapping[str, Any]) -> tuple[SecurityScheme, ...]:
    out: list[SecurityScheme] = []
    for name, entry in raw.items():
        if not isinstance(entry, Mapping):
            continue
        kind = str(entry.get("type", ""))
        if kind == "http":
            detail = str(entry.get("scheme", "")).title()
        elif kind == "apiKey":
            detail = f"{entry.get('in', '')} {entry.get('name', '')}".strip()
        elif kind == "oauth2":
            detail = ", ".join(str(f) for f in (entry.get("flows") or {}))
        else:
            detail = str(entry.get("openIdConnectUrl", ""))
        out.append(
            SecurityScheme(
                name=str(name), type=kind, detail=detail, description=str(entry.get("description", ""))
            )
        )
    return tuple(out)


# -------------------------------------------------------------------- shapes


def _ref_name(schema: Any) -> str:
    """Return the model name a `$ref` points at, or empty for anything else."""
    if not isinstance(schema, Mapping):
        return ""
    ref = schema.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/components/schemas/"):
        return ""
    return ref.removeprefix("#/components/schemas/")


def _shape(schema: Any, components: Mapping[str, Any]) -> Shape | None:
    """What a body is, one level deep.

    The Example half of the reference answers "what do I send"; this answers
    "what am I allowed to send", the question that arrives the moment the
    example stops working. One level and no further, by design: a model whose
    fields are models is a link away, and a Schema view that inlined the whole
    graph would put a page of `User` under an endpoint about tasks.
    """
    if not isinstance(schema, Mapping) or not schema:
        return None

    name = _ref_name(schema)
    resolved = _resolve(schema, components, 0)
    if not resolved:
        return None

    if _type_of(resolved) == "array":
        items = resolved.get("items") or {}
        inner = _ref_name(items)
        item_schema = _resolve(items, components, 0) if isinstance(items, Mapping) else {}
        return Shape(
            label=f"array of {inner or _type_of(item_schema) if item_schema else 'anything'}",
            model=inner,
            array=True,
            fields=_fields(item_schema, components) if not inner else (),
            source=_pretty(schema),
        )

    return Shape(
        label=name or _type_of(resolved),
        model=name,
        fields=_fields(resolved, components) if not name else (),
        source=_pretty(schema),
    )


def _fields(schema: Mapping[str, Any], components: Mapping[str, Any]) -> tuple[Field, ...]:
    """Read an object schema's properties as rows."""
    if not isinstance(schema, Mapping):
        return ()
    properties = schema.get("properties")
    if not isinstance(properties, Mapping) or not properties:
        return ()
    required = set(schema.get("required") or ())
    rows: list[Field] = []
    for name, raw in properties.items():
        if not isinstance(raw, Mapping):
            continue
        ref = _ref_name(raw)
        resolved = _effective(raw, components)
        # `_effective` unwraps `T | None`, the shape of every optional field
        # FastAPI emits, so nullability has to be read off the original, before
        # the branch that recorded it was dropped.
        nullable = _nullable(raw)
        if not ref:
            ref = next(
                (_ref_name(b) for b in _branches(raw) if _ref_name(b)),
                "",
            )
        default = resolved.get("default")
        rows.append(
            Field(
                name=str(name),
                type=ref or _type_of(resolved),
                required=str(name) in required,
                description=str(resolved.get("description", "")),
                format=_format_of(resolved),
                constraints=_constraints(resolved),
                choices=tuple(_scalar(v) for v in (resolved.get("enum") or ()) if v is not None),
                default="" if default is None else _scalar(default),
                ref=ref,
                nullable=nullable,
                deprecated=bool(resolved.get("deprecated", False)),
                read_only=bool(resolved.get("readOnly", False)),
                write_only=bool(resolved.get("writeOnly", False)),
            )
        )
    return tuple(rows)


def _branches(schema: Mapping[str, Any]) -> tuple[Any, ...]:
    for key in ("anyOf", "oneOf", "allOf"):
        branches = schema.get(key)
        if branches:
            return tuple(branches)
    return ()


def _nullable(schema: Mapping[str, Any]) -> bool:
    """Whether the document says this may be `null`, either way of spelling it."""
    kind = schema.get("type")
    if kind == "null" or (isinstance(kind, list) and "null" in kind):
        return True
    return any(isinstance(b, Mapping) and b.get("type") == "null" for b in _branches(schema))


def _models(
    raw: Mapping[str, Any], components: Mapping[str, Any], index: Mapping[str, Operation]
) -> tuple[Model, ...]:
    """`components.schemas`, as the Schemas section renders it.

    FastAPI puts one entry here for every Pydantic model on the boundary, which
    makes this section the closest thing the document has to a data dictionary.
    Swagger renders it at the bottom of the page; here it is a branch of the
    sidebar, for the same reason the operations are — a list of two hundred
    types is navigation, not content.
    """
    if not isinstance(raw, Mapping) or not raw:
        return ()

    # Which operations exchange each model. Read off the shapes rather than by
    # crawling the document for `$ref` strings, and direct exchange is the
    # relation worth showing: `Task` is used by the three task endpoints, not by
    # every endpoint that returns something with a `Task` buried in it. The
    # nested ones are one link away, under the model that holds them.
    mentions: dict[str, list[str]] = {}
    for operation in index.values():
        seen = {
            shape.model
            for shape in (operation.body_shape, *(r.shape for r in operation.responses))
            if shape is not None and shape.model
        }
        for name in sorted(seen):
            mentions.setdefault(name, []).append(operation.id)

    taken: set[str] = set()
    models: list[Model] = []
    for name, schema in raw.items():
        if not isinstance(schema, Mapping):
            continue
        slug = _slug(str(name))
        while slug in taken:
            slug += "-2"
        taken.add(slug)
        choices = tuple(_scalar(v) for v in (schema.get("enum") or ()) if v is not None)
        models.append(
            Model(
                name=str(name),
                slug=slug,
                description=str(schema.get("description", "")),
                kind="enum" if choices else "object",
                fields=_fields(schema, components),
                choices=choices,
                example=_pretty(_example(schema, components, 0)),
                source=_pretty(schema),
                used_by=tuple(mentions.get(str(name), ())),
            )
        )
    return tuple(models)


# ------------------------------------------------------------------ examples


def _example(schema: Any, components: Mapping[str, Any], depth: int) -> Any:
    """Work out a value that satisfies `schema`, as far as the schema allows.

    Not validation and not a generator: it puts something in the request-body
    box that a developer can edit rather than compose from nothing. Where the
    schema is ambiguous — an untyped object, a union — it takes the first branch
    and moves on, because an example with the right shape and a wrong value
    beats an empty one.
    """
    if depth > _MAX_DEPTH or not isinstance(schema, Mapping):
        return None

    schema = _resolve(schema, components, depth)

    for key in ("example", "default"):
        if key in schema:
            return schema[key]
    examples = schema.get("examples")
    if isinstance(examples, Sequence) and not isinstance(examples, str) and examples:
        return examples[0]

    for key in ("allOf", "anyOf", "oneOf"):
        branches = schema.get(key)
        if not branches:
            continue
        if key == "allOf":
            merged: dict[str, Any] = {}
            for branch in branches:
                part = _example(branch, components, depth + 1)
                if isinstance(part, Mapping):
                    merged.update(part)
            return merged
        # A nullable field in OpenAPI 3.1 is `anyOf: [T, {type: null}]`, and an
        # example of `null` teaches nothing. Take the first branch that is not.
        for branch in branches:
            if isinstance(branch, Mapping) and branch.get("type") == "null":
                continue
            return _example(branch, components, depth + 1)
        return None

    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]

    kind = _type_of(schema)
    if kind == "object":
        properties = schema.get("properties") or {}
        return {str(name): _example(sub, components, depth + 1) for name, sub in properties.items()}
    if kind == "array":
        items = schema.get("items")
        return [_example(items, components, depth + 1)] if items else []
    if kind == "string" and schema.get("format") in ("date-time", "date"):
        return "2026-01-01T00:00:00Z" if schema["format"] == "date-time" else "2026-01-01"
    return _PLACEHOLDERS.get(kind)


def _effective(schema: Mapping[str, Any], components: Mapping[str, Any]) -> Mapping[str, Any]:
    """The schema a form field is built from, with the optional wrapper removed.

    `status: Literal["todo", "doing"] | None = None` is the commonest parameter
    in a FastAPI app, and OpenAPI 3.1 writes it as

        {"anyOf": [{"type": "string", "enum": [...]}, {"type": "null"}],
         "default": null}

    Reading `enum` off the outer object finds nothing, and the field degrades
    from a three-choice select to a free-text box — which still works and is
    still wrong. So the null branch is dropped, the remaining one is resolved,
    and the outer `default` and `description` are kept: they belong to the
    parameter, not to the branch.
    """
    resolved = dict(_resolve(schema, components, 0))
    for key in ("anyOf", "oneOf", "allOf"):
        branches = resolved.get(key)
        if not branches:
            continue
        real = [b for b in branches if isinstance(b, Mapping) and b.get("type") != "null"]
        if len(real) != 1:
            # A genuine union of two shapes. No single control expresses it, so
            # it stays a text box rather than picking one branch and hiding the
            # other.
            break
        inner = dict(_resolve(real[0], components, 0))
        inner.update({k: v for k, v in resolved.items() if k not in (key, *inner)})
        return inner
    return resolved


def _resolve(schema: Mapping[str, Any], components: Mapping[str, Any], depth: int) -> Mapping[str, Any]:
    """Follow `$ref` into `components`, as far as it goes.

    Local refs only. Following a `$ref` to another document would mean fetching
    it, and a docs page that makes outbound HTTP requests to render hangs behind
    a firewall.

    Keywords written beside a `$ref` survive the hop. OpenAPI 3.1 allows them —
    `{"$ref": ".../Priority", "default": "normal"}` is how FastAPI writes a
    parameter whose type is an enum and whose default is one of its members —
    and dropping them loses the part that belongs to this use of the schema
    rather than to the schema itself. The outermost wins, as the most specific
    place anyone wrote it down.
    """
    seen: set[str] = set()
    siblings: dict[str, Any] = {}
    while isinstance(schema, Mapping) and "$ref" in schema and depth <= _MAX_DEPTH:
        ref = str(schema["$ref"])
        if ref in seen or not ref.startswith("#/components/"):
            return {}
        seen.add(ref)
        for key, value in schema.items():
            if key != "$ref":
                siblings.setdefault(key, value)
        target: Any = components
        for part in ref.removeprefix("#/components/").split("/"):
            if not isinstance(target, Mapping):
                return {}
            target = target.get(part)
        if not isinstance(target, Mapping):
            return {}
        schema = target
    if not isinstance(schema, Mapping):
        return {}
    return {**schema, **siblings} if siblings else schema


def _type_of(schema: Mapping[str, Any]) -> str:
    """Read the JSON type, collapsing 3.1's list form to its first real entry."""
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), None)
    if kind:
        return str(kind)
    return "object" if "properties" in schema else "string"


def _pretty(value: Any) -> str:
    try:
        return json.dumps(value, indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError):  # pragma: no cover — `default=str` covers it
        return str(value)


def _scalar(value: Any) -> str:
    """Render a parameter value as it goes on the wire.

    `True` becomes `true`, not `True`: the value goes into a query string that
    FastAPI parses back, and Python's repr is not what it accepts.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    return _pretty(value)


def _slug(text: str) -> str:
    return _UNSAFE.sub("-", str(text)).strip("-").lower() or "operation"


def _unique(slug: str, taken: Mapping[str, Operation]) -> str:
    if slug not in taken:
        return slug
    n = 2
    while f"{slug}-{n}" in taken:
        n += 1
    return f"{slug}-{n}"
