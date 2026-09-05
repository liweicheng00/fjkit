"use strict";
// Drives extension.js under Node with a stand-in for the `vscode` module:
// activates it against this repository, then asks the providers what an editor
// would — definition, hover and references on `task.title` in the demo — and
// checks that an edited buffer is what the server sees. Exit 0 when all hold.

const Module = require("node:module");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..", "..", "..");
const DOC = path.join(ROOT, "examples/fjkit-demo/app/templates/tasks/macros.html");
const ROUTER = path.join(ROOT, "examples/fjkit-demo/app/features/tasks/router.py");
const SCHEMAS = path.join(ROOT, "examples/fjkit-demo/app/features/tasks/schemas.py");
const EVENTS = path.join(ROOT, "examples/fjkit-demo/app/features/search/schemas.py");

// ---- the vscode stand-in ---------------------------------------------------

class Uri {
  constructor(fsPath) {
    this.fsPath = fsPath;
    this.scheme = "file";
  }
  static file(p) {
    return new Uri(p);
  }
  static parse(s) {
    return new Uri(decodeURIComponent(s.replace(/^file:\/\//, "")));
  }
  toString() {
    return "file://" + encodeURI(this.fsPath);
  }
}
class Position {
  constructor(line, character) {
    this.line = line;
    this.character = character;
  }
}
class Range {
  constructor(sl, sc, el, ec) {
    this.start = new Position(sl, sc);
    this.end = new Position(el, ec);
  }
}
class Location {
  constructor(uri, range) {
    this.uri = uri;
    this.range = range;
  }
}
class MarkdownString {
  constructor(value) {
    this.value = value;
  }
}
class Hover {
  constructor(contents) {
    this.contents = contents;
  }
}
const providers = {};
const handlers = {};
const disposable = () => ({ dispose() {} });
const log = [];
const vscode = {
  Uri,
  Position,
  Range,
  Location,
  MarkdownString,
  Hover,
  window: {
    createOutputChannel: () => ({ appendLine: (l) => log.push(l), dispose() {} }),
    setStatusBarMessage: () => {},
  },
  workspace: {
    workspaceFolders: [{ uri: Uri.file(ROOT), name: "repo" }],
    textDocuments: [],
    getConfiguration: () => ({ get: () => [] }),
    onDidOpenTextDocument: (h) => ((handlers.open = h), disposable()),
    onDidChangeTextDocument: (h) => ((handlers.change = h), disposable()),
    onDidSaveTextDocument: (h) => ((handlers.save = h), disposable()),
    onDidCloseTextDocument: (h) => ((handlers.close = h), disposable()),
    onDidChangeConfiguration: () => disposable(),
  },
  languages: {
    registerDefinitionProvider: (_s, p) => ((providers.definition = p), disposable()),
    registerReferenceProvider: (_s, p) => ((providers.references = p), disposable()),
    registerHoverProvider: (_s, p) => ((providers.hover = p), disposable()),
  },
  commands: { registerCommand: () => disposable() },
};
const resolve = Module._resolveFilename;
Module._resolveFilename = function (request, ...rest) {
  return request === "vscode" ? "vscode" : resolve.call(this, request, ...rest);
};
require.cache["vscode"] = { id: "vscode", filename: "vscode", loaded: true, exports: vscode };

// ---- the checks ------------------------------------------------------------

function document(text, version, file = DOC, languageId = "html") {
  return { uri: Uri.file(file), languageId, version, getText: () => text };
}

function positionOf(text, needle, on) {
  if (!text.includes(needle)) throw new Error(`not in the fixture: ${needle}`);
  const offset = text.indexOf(needle) + needle.indexOf(on);
  const line = text.slice(0, offset).split("\n").length - 1;
  return new Position(line, offset - text.lastIndexOf("\n", offset - 1) - 1);
}

function assert(condition, what) {
  if (!condition) {
    console.error(`FAILED: ${what}`);
    console.error(log.join("\n"));
    process.exit(1);
  }
  console.log(`ok  ${what}`);
}

(async () => {
  const ext = require("../extension.js");
  ext.activate({ subscriptions: [] });
  await ext.ready();
  assert(log.some((l) => l.startsWith("started ")), "the server starts from .venv");

  const text = fs.readFileSync(DOC, "utf8");
  let doc = document(text, 1);
  handlers.open(doc);
  const pos = positionOf(text, "cell(task.title", "title");

  const defs = await providers.definition.provideDefinition(doc, pos);
  assert(defs && defs.length === 1 && defs[0].uri.fsPath.endsWith("features/tasks/schemas.py"), "definition of task.title is Task.title in schemas.py");
  assert(defs[0] instanceof Location && defs[0].range.start.line > 0, "a Location with a range");

  const hover = await providers.hover.provideHover(doc, pos);
  assert(hover && hover.contents.value.includes("Task.title: str"), "hover names the field and its annotation");

  const refs = await providers.references.provideReferences(doc, pos);
  assert(refs && refs.length >= 10, `references across the templates (${refs ? refs.length : 0})`);

  // An unsaved edit: a line inserted at the top moves everything down by one,
  // and the server must see the buffer, not the file.
  doc = document("{# inserted #}\n" + text, 2);
  handlers.change({ document: doc });
  const shifted = new Position(pos.line + 1, pos.character);
  const after = await providers.definition.provideDefinition(doc, shifted);
  assert(after && after.length === 1 && after[0].uri.fsPath.endsWith("schemas.py"), "the server sees the edited buffer");
  const stale = await providers.definition.provideDefinition(doc, pos);
  assert(!stale || stale.length === 0, "the old position no longer resolves in the edited buffer");

  handlers.close(doc);

  // The other direction — the reason this client exists: from Python.
  const router = fs.readFileSync(ROUTER, "utf8");
  const py = document(router, 1, ROUTER, "python");
  handlers.open(py);
  const tpl = await providers.definition.provideDefinition(py, positionOf(router, '@render("tasks/page.html"', "tasks/page"));
  assert(tpl && tpl.length === 1 && tpl[0].uri.fsPath.endsWith("templates/tasks/page.html"), "a @render string in Python opens its template");
  handlers.close(py);

  const schemas = fs.readFileSync(SCHEMAS, "utf8");
  const model = document(schemas, 1, SCHEMAS, "python");
  handlers.open(model);
  const field = positionOf(schemas, "    tasks: list[Task]", "tasks");
  const uses = await providers.references.provideReferences(model, field);
  assert(uses && uses.length >= 3 && uses.every((l) => l.uri.fsPath.endsWith(".html")), `a model field in Python finds its template uses (${uses ? uses.length : 0})`);
  const own = await providers.definition.provideDefinition(model, field);
  assert(!own || own.length === 0, "and offers no definition of its own — Pyright has that one");
  handlers.close(model);

  const events = fs.readFileSync(EVENTS, "utf8");
  const evdoc = document(events, 1, EVENTS, "python");
  handlers.open(evdoc);
  const constant = positionOf(events, 'CHANGED_EVENT = "task-changed"', "CHANGED_EVENT");
  const listeners = await providers.references.provideReferences(evdoc, constant);
  assert(listeners && listeners.some((l) => l.uri.fsPath.endsWith("panels/page.html")), "an event constant in Python finds the templates listening");
  handlers.close(evdoc);

  // A request the server never answers must not hang the editor.
  const bogus = await providers.definition.provideDefinition(evdoc, new Position(-1, -1));
  assert(bogus === null && log.some((l) => l.includes("no answer")), "an unanswered request times out instead of waiting forever");

  await ext.deactivate();
  await new Promise((r) => setTimeout(r, 700));
  assert(log.some((l) => l.startsWith("server exited")), "the server exits on deactivate");
  process.exit(0);
})().catch((e) => {
  console.error(e);
  console.error(log.join("\n"));
  process.exit(1);
});
