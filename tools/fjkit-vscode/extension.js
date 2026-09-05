"use strict";
// fjkit — definition, references and hover between FastAPI routes, response
// models, Jinja templates and htmx events, answered by `fjkit-lsp` over stdio.
//
// Plain JavaScript on the VS Code API and nothing else: no vscode-languageclient,
// no bundler, no npm. The client speaks the three requests the server answers
// and the four document notifications that keep the server's copy of an open
// buffer current. `tools/fjkit-vscode/build.py` zips it into a .vsix.

const vscode = require("vscode");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

/** Language ids the providers attach to. `html` is what `.vscode/settings.json`
 *  maps templates to; the two `jinja*` ids are what a Jinja grammar assigns. */
const LANGUAGES = ["html", "jinja-html", "jinja", "python"];

let output = null;
let server = null; // {proc, pending, nextId, buffer, ready}
let starting = Promise.resolve();

function log(line) {
  if (output) output.appendLine(line);
}

// ---- process and framing ---------------------------------------------------

function serverCommand(folder) {
  const configured = vscode.workspace.getConfiguration("fjkit").get("lsp.command") || [];
  if (configured.length) {
    return [path.resolve(folder, configured[0]), ...configured.slice(1)];
  }
  const entry = process.platform === "win32" ? ".venv\\Scripts\\fjkit-lsp.exe" : ".venv/bin/fjkit-lsp";
  return [path.join(folder, entry)];
}

function send(s, message) {
  const body = Buffer.from(JSON.stringify(message), "utf8");
  s.proc.stdin.write(`Content-Length: ${body.length}\r\n\r\n`);
  s.proc.stdin.write(body);
}

/** How long a request may go unanswered. The server answers in milliseconds;
 *  one it cannot parse it may not answer at all, and an editor waiting on a
 *  promise that never settles shows a spinner forever. */
const REQUEST_TIMEOUT_MS = 10000;

function request(s, method, params) {
  const id = s.nextId++;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      s.pending.delete(id);
      reject(new Error(`no answer to ${method} within ${REQUEST_TIMEOUT_MS / 1000}s`));
    }, REQUEST_TIMEOUT_MS);
    s.pending.set(id, {
      resolve: (v) => (clearTimeout(timer), resolve(v)),
      reject: (e) => (clearTimeout(timer), reject(e)),
    });
    send(s, { jsonrpc: "2.0", id, method, params });
  });
}

function notify(s, method, params) {
  send(s, { jsonrpc: "2.0", method, params });
}

/** Reassembles `Content-Length`-framed messages from stdout chunks. */
function onData(s, chunk) {
  s.buffer = Buffer.concat([s.buffer, chunk]);
  for (;;) {
    const separator = s.buffer.indexOf("\r\n\r\n");
    if (separator < 0) return;
    const header = s.buffer.subarray(0, separator).toString("ascii");
    const match = /Content-Length:\s*(\d+)/i.exec(header);
    const start = separator + 4;
    if (!match) {
      s.buffer = s.buffer.subarray(start);
      continue;
    }
    const length = Number(match[1]);
    if (s.buffer.length < start + length) return;
    const body = s.buffer.subarray(start, start + length).toString("utf8");
    s.buffer = s.buffer.subarray(start + length);
    let message;
    try {
      message = JSON.parse(body);
    } catch (e) {
      log(`unreadable message from the server: ${e.message}`);
      continue;
    }
    dispatch(s, message);
  }
}

function dispatch(s, message) {
  if (message.id !== undefined && message.method === undefined) {
    const waiting = s.pending.get(message.id);
    if (!waiting) return;
    s.pending.delete(message.id);
    if (message.error) waiting.reject(new Error(message.error.message));
    else waiting.resolve(message.result === undefined ? null : message.result);
  } else if (message.id !== undefined) {
    // A request from the server. Nothing it can ask for is needed here, and an
    // answer — any answer — is what keeps it from waiting.
    send(s, { jsonrpc: "2.0", id: message.id, result: null });
  } else if (message.method === "window/logMessage" || message.method === "window/showMessage") {
    log(message.params && message.params.message ? message.params.message : "");
  }
}

// ---- lifecycle -------------------------------------------------------------

async function start() {
  const folders = vscode.workspace.workspaceFolders || [];
  const folder = folders.length ? folders[0].uri.fsPath : null;
  if (!folder) {
    log("no workspace folder open; the server is not started");
    return;
  }
  const [command, ...args] = serverCommand(folder);
  if (!fs.existsSync(command)) {
    log(`${command} does not exist — run \`uv sync\` in ${folder}, then "fjkit: Restart language server"`);
    vscode.window.setStatusBarMessage("fjkit: language server not found — run uv sync", 8000);
    return;
  }
  const proc = spawn(command, args, { cwd: folder, env: process.env });
  const s = { proc, pending: new Map(), nextId: 1, buffer: Buffer.alloc(0), ready: false };
  server = s;
  proc.on("error", (e) => log(`could not start ${command}: ${e.message}`));
  proc.on("exit", (code, signal) => {
    log(`server exited (${code === null ? signal : code})`);
    for (const waiting of s.pending.values()) waiting.reject(new Error("fjkit-lsp exited"));
    s.pending.clear();
    if (server === s) server = null;
  });
  proc.stderr.on("data", (d) => log(String(d).trimEnd()));
  proc.stdout.on("data", (chunk) => onData(s, chunk));

  const uri = vscode.Uri.file(folder).toString();
  try {
    await request(s, "initialize", {
      processId: process.pid,
      rootUri: uri,
      workspaceFolders: [{ uri, name: path.basename(folder) }],
      capabilities: { textDocument: { hover: { contentFormat: ["markdown", "plaintext"] } } },
    });
  } catch (e) {
    log(`initialize failed: ${e.message}`);
    return;
  }
  notify(s, "initialized", {});
  s.ready = true;
  for (const doc of vscode.workspace.textDocuments) opened(doc);
  log(`started ${command}`);
}

async function stop() {
  const s = server;
  if (!s) return;
  server = null;
  s.ready = false;
  try {
    await Promise.race([request(s, "shutdown", null), new Promise((r) => setTimeout(r, 1000))]);
    notify(s, "exit", null);
  } catch (_e) {
    // The process is going away either way.
  }
  setTimeout(() => {
    if (s.proc.exitCode === null) s.proc.kill();
  }, 500);
}

async function restart() {
  starting = starting.then(stop).then(start);
  return starting;
}

// ---- documents -------------------------------------------------------------

function ours(doc) {
  return doc.uri.scheme === "file" && LANGUAGES.includes(doc.languageId);
}

function opened(doc) {
  if (!server || !server.ready || !ours(doc)) return;
  notify(server, "textDocument/didOpen", {
    textDocument: { uri: doc.uri.toString(), languageId: doc.languageId, version: doc.version, text: doc.getText() },
  });
}

function changed(doc) {
  if (!server || !server.ready || !ours(doc)) return;
  // Whole text on every change: the server re-scans the buffer per request
  // anyway, and a template is small.
  notify(server, "textDocument/didChange", {
    textDocument: { uri: doc.uri.toString(), version: doc.version },
    contentChanges: [{ text: doc.getText() }],
  });
}

function saved(doc) {
  if (!server || !server.ready || !ours(doc)) return;
  notify(server, "textDocument/didSave", { textDocument: { uri: doc.uri.toString() } });
}

function closed(doc) {
  if (!server || !server.ready || !ours(doc)) return;
  notify(server, "textDocument/didClose", { textDocument: { uri: doc.uri.toString() } });
}

// ---- providers -------------------------------------------------------------

function at(doc, position) {
  return { textDocument: { uri: doc.uri.toString() }, position: { line: position.line, character: position.character } };
}

function toLocation(item) {
  const uri = item.uri || item.targetUri;
  const range = item.range || item.targetSelectionRange || item.targetRange;
  if (!uri || !range) return null;
  return new vscode.Location(
    vscode.Uri.parse(uri),
    new vscode.Range(range.start.line, range.start.character, range.end.line, range.end.character),
  );
}

async function locations(method, doc, position, extra) {
  const s = server;
  if (!s || !s.ready) return null;
  let result;
  try {
    result = await request(s, method, Object.assign(at(doc, position), extra || {}));
  } catch (e) {
    log(`${method}: ${e.message}`);
    return null;
  }
  if (!result) return null;
  const list = Array.isArray(result) ? result : [result];
  return list.map(toLocation).filter(Boolean);
}

async function hover(doc, position) {
  const s = server;
  if (!s || !s.ready) return null;
  let result;
  try {
    result = await request(s, "textDocument/hover", at(doc, position));
  } catch (e) {
    log(`textDocument/hover: ${e.message}`);
    return null;
  }
  const contents = result && result.contents;
  if (!contents) return null;
  const parts = Array.isArray(contents) ? contents : [contents];
  const value = parts.map((c) => (typeof c === "string" ? c : c.value)).join("\n\n");
  return new vscode.Hover(new vscode.MarkdownString(value));
}

// ---- entry points ----------------------------------------------------------

function activate(context) {
  output = vscode.window.createOutputChannel("fjkit");
  const selector = LANGUAGES.map((language) => ({ language, scheme: "file" }));
  context.subscriptions.push(
    output,
    vscode.commands.registerCommand("fjkit.restartServer", restart),
    vscode.languages.registerDefinitionProvider(selector, {
      provideDefinition: (doc, position) => locations("textDocument/definition", doc, position),
    }),
    vscode.languages.registerReferenceProvider(selector, {
      provideReferences: (doc, position) =>
        locations("textDocument/references", doc, position, { context: { includeDeclaration: true } }),
    }),
    vscode.languages.registerHoverProvider(selector, { provideHover: hover }),
    vscode.workspace.onDidOpenTextDocument(opened),
    vscode.workspace.onDidChangeTextDocument((e) => changed(e.document)),
    vscode.workspace.onDidSaveTextDocument(saved),
    vscode.workspace.onDidCloseTextDocument(closed),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("fjkit.lsp.command")) restart();
    }),
  );
  starting = start();
  return starting;
}

function deactivate() {
  return stop();
}

module.exports = { activate, deactivate, ready: () => starting };
