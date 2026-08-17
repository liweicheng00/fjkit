"""Measure what actually costs CPU and memory when Jinja2 renders.

Every claim in docs/jinja-performance.md comes from a case below. Re-run it on
your own hardware before believing any of the numbers — the *ordering* of the
results is stable, the absolute microseconds are not.

    uv run python bench/render_bench.py            # everything
    uv run python bench/render_bench.py macros     # one section
    uv run python bench/render_bench.py --json     # machine-readable
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import tempfile
import tracemalloc
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

#: The demo is a workspace member, not an installed package, so its own root
#: goes on the path before its schemas can be imported.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples" / "board"))

from app.features.tasks.schemas import Priority, Status, Task
from fjkit import FjkitConfig, build_environment
from fjkit.config import TEMPLATE_DIR as KIT_TEMPLATE_DIR
from jinja2 import Environment, FileSystemLoader, StrictUndefined

#: The benchmark renders the demo's real templates, so the Environment needs
#: the same two-layer search path the app uses: app first, kit second.
APP_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "examples" / "board" / "app" / "templates"


def app_env(**overrides) -> Environment:
    return build_environment(FjkitConfig(template_dir=APP_TEMPLATE_DIR, **overrides))


FIXTURES = Path(__file__).resolve().parent / "fixtures"
RESULTS: dict[str, list[dict]] = {}


# --------------------------------------------------------------------------- #
# harness
# --------------------------------------------------------------------------- #


def make_tasks(n: int) -> list[Task]:
    now = datetime.now(UTC)
    statuses, priorities = list(Status), list(Priority)
    return [
        Task(
            id=i,
            title=f"Task number {i} with a title of realistic length",
            status=statuses[i % 3],
            priority=priorities[i % 3],
            owner=f"owner{i % 7}",
            created_at=now,
        )
        for i in range(n)
    ]


def timed(fn: Callable[[], object], *, iterations: int, repeats: int = 7) -> float:
    """Median per-iteration time in microseconds, after a warmup round."""
    for _ in range(min(iterations, 50)):
        fn()
    samples = []
    for _ in range(repeats):
        start = perf_counter()
        for _ in range(iterations):
            fn()
        samples.append((perf_counter() - start) / iterations * 1e6)
    return statistics.median(samples)


def peak_kib(fn: Callable[[], object]) -> float:
    fn()  # warm caches so we measure the render, not the import
    tracemalloc.start()
    tracemalloc.reset_peak()
    fn()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak / 1024


def report(section: str, rows: list[dict], *, baseline: str | None = None) -> None:
    RESULTS[section] = rows
    if "--json" in sys.argv:
        return
    print(f"\n\033[1m{section}\033[0m")
    keys = [k for k in rows[0] if k != "case"]
    width = max(len(r["case"]) for r in rows) + 2
    print("  " + "case".ljust(width) + "".join(f"{k:>16}" for k in keys))
    print("  " + "-" * (width + 16 * len(keys)))
    base = next((r for r in rows if r["case"] == baseline), None)
    for row in rows:
        line = "  " + row["case"].ljust(width)
        for key in keys:
            value = row[key]
            line += f"{value:>16,.1f}" if isinstance(value, float) else f"{value:>16,}"
        if base and row is not base and isinstance(row[keys[0]], (int, float)):
            ratio = row[keys[0]] / base[keys[0]] if base[keys[0]] else 0
            line += f"   {ratio:.2f}x"
        print(line)


def fixture_env(**kwargs) -> Environment:
    kwargs.setdefault("auto_reload", False)
    return Environment(loader=FileSystemLoader(FIXTURES), autoescape=True, **kwargs)


# --------------------------------------------------------------------------- #
# 1. Environment settings on the hot path
# --------------------------------------------------------------------------- #


def bench_environment() -> None:
    """auto_reload, StrictUndefined and the LRU, measured per render.

    These are the knobs people argue about. Two of the three barely register;
    knowing which two is the point.
    """
    tasks = make_tasks(50)
    ctx = {"request": _FakeRequest(), "tasks": tasks}
    rows = []

    # auto_reload is charged at get_template() time, not at render() time — it
    # stats every file in the inheritance chain. Measuring it means calling
    # get_template() per iteration, which is what a route does anyway.
    for case, reload_ in [
        ("get_template + render, auto_reload=True", True),
        ("get_template + render, auto_reload=False", False),
    ]:
        env = app_env(auto_reload=reload_)
        env.get_template("tasks/report.html")
        rows.append(
            {
                "case": case,
                "us/render": timed(lambda e=env: e.get_template("tasks/report.html").render(**ctx), iterations=200),
            }
        )

    env = app_env(auto_reload=False)
    template = env.get_template("tasks/report.html")
    rows.append(
        {
            "case": "  ... template hoisted out of the call",
            "us/render": timed(lambda: template.render(**ctx), iterations=200),
        }
    )

    strict = app_env(auto_reload=False, strict_undefined=False)
    loose = strict.get_template("tasks/report.html")
    rows.append(
        {
            "case": "  ... and Undefined instead of Strict",
            "us/render": timed(lambda: loose.render(**ctx), iterations=200),
        }
    )

    report("1. Environment settings (50-row page)", rows, baseline="get_template + render, auto_reload=True")


class _FakeRequest:
    """Enough of a Request for the templates' url_for/is_active globals."""

    scope: dict = {}

    class _URL:
        path = "/tasks"

    url = _URL()

    def url_for(self, name: str, **params):
        from starlette.datastructures import URL

        return URL("http://bench/" + name + ("/" + "/".join(map(str, params.values())) if params else ""))


# --------------------------------------------------------------------------- #
# 2. Cold start: compiling templates vs loading cached bytecode
# --------------------------------------------------------------------------- #

_COLD_START = """
import sys, time
from pathlib import Path
sys.path.insert(0, {root!r})
from fjkit import FjkitConfig, build_environment
start = time.perf_counter()
env = build_environment(FjkitConfig(
    template_dir=Path({app_templates!r}),
    auto_reload=False,
    bytecode_cache_dir=Path({cache_dir!r}) if {cache} else None,
))
names = [n for n in env.list_templates() if n.endswith(('.html', '.jinja'))]
for name in names:
    env.get_template(name)
print((time.perf_counter() - start) * 1000, len(names))
"""


def bench_cold_start() -> None:
    """The cost a *fresh process* pays before it can serve the first request.

    Invisible in a long-lived server, and squarely on the critical path for
    `--reload` loops, serverless cold starts and rolling deploys.
    """
    root = str(Path(__file__).resolve().parent.parent)
    rows = []
    with tempfile.TemporaryDirectory() as cache_dir:
        for case, cache in [("compile from source", "False"), ("warm bytecode cache", "True")]:
            script = _COLD_START.format(
                root=root, cache=cache, cache_dir=cache_dir, app_templates=str(APP_TEMPLATE_DIR)
            )
            if cache == "True":  # prime the cache first; measure the second run
                subprocess.run([sys.executable, "-c", script], capture_output=True, check=True)
            samples = []
            for _ in range(5):
                out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
                ms, count = out.stdout.split()
                samples.append(float(ms))
            rows.append({"case": case, "ms": statistics.median(samples), "templates": int(count)})
    report("2. Cold start: load every template in a fresh process", rows, baseline="compile from source")


# --------------------------------------------------------------------------- #
# 3. How you factor a repeated component
# --------------------------------------------------------------------------- #


def bench_macros() -> None:
    """macro vs include vs inline, for a component repeated N times.

    `{% include %}` inside a loop re-resolves the template and builds a fresh
    context per iteration. A macro is a call on a module that was built once.
    """
    env = fixture_env()
    rows = []
    for n in (10, 100, 1000):
        tasks = make_tasks(n)
        measured = {}
        for case, name in [
            ("inline", "loop_inline.html"),
            ("macro", "loop_macro.html"),
            ("include", "loop_include.html"),
        ]:
            template = env.get_template(name)
            measured[case] = timed(
                lambda t=template, ts=tasks: t.render(tasks=ts),
                iterations=max(5, 2000 // n),
            )
        rows.append(
            {
                "case": f"{n:>4} rows",
                "inline us": measured["inline"],
                "macro us": measured["macro"],
                "include us": measured["include"],
            }
        )
    report("3. Repeated component: inline vs macro vs include", rows)


# --------------------------------------------------------------------------- #
# 4. `with context` on imports
# --------------------------------------------------------------------------- #


def bench_import_context() -> None:
    """`{% from x import y %}` vs the same line `with context`.

    Without context (the default) Jinja hands back a module it built once and
    cached on the Template. `with context` rebuilds that module — re-running
    every top-level statement in the imported file — on every single render.
    """
    env = fixture_env()
    rows = []
    for case, name in [
        ("without context (default)", "import_without_context.html"),
        ("with context", "import_with_context.html"),
    ]:
        template = env.get_template(name)
        measured = {}
        for label, n in [("1 row us", 1), ("20 rows us", 20)]:
            tasks = make_tasks(n)
            measured[label] = timed(lambda t=template, tk=tasks: t.render(tasks=tk), iterations=500)
        rows.append({"case": case, **measured})
    report("4. Macro imports: with vs without context", rows, baseline="without context (default)")


# --------------------------------------------------------------------------- #
# 5. Whitespace control
# --------------------------------------------------------------------------- #


def bench_whitespace() -> None:
    """trim_blocks/lstrip_blocks: bytes on the wire, and what that costs."""
    tasks = make_tasks(200)
    rows = []
    for case, trim in [("trim_blocks off", False), ("trim_blocks on", True)]:
        env = Environment(
            loader=FileSystemLoader([APP_TEMPLATE_DIR, KIT_TEMPLATE_DIR]),
            autoescape=True,
            auto_reload=False,
            trim_blocks=trim,
            lstrip_blocks=trim,
            undefined=StrictUndefined,
        )
        env.globals.update(app_env().globals)
        template = env.get_template("tasks/report.html")
        ctx = {"request": _FakeRequest(), "tasks": tasks}
        html = template.render(**ctx)
        rows.append(
            {
                "case": case,
                "bytes": len(html.encode()),
                "us/render": timed(lambda t=template, c=ctx: t.render(**c), iterations=100),
            }
        )
    report("5. Whitespace control (200-row page)", rows, baseline="trim_blocks off")


# --------------------------------------------------------------------------- #
# 6. Memory: buffering the page vs streaming it
# --------------------------------------------------------------------------- #


def bench_memory() -> None:
    """Peak allocation for one large page, three ways.

    render() materialises every fragment and then one joined string. Streaming
    holds one buffer. The gap is the whole document.
    """
    env = app_env(auto_reload=False)
    template = env.get_template("tasks/report.html")
    rows = []
    for n in (1_000, 20_000):
        tasks = make_tasks(n)
        ctx = {"request": _FakeRequest(), "tasks": tasks}
        size = len(template.render(**ctx).encode()) / 1024

        def drain_stream(buffer: int, template=template, ctx=ctx) -> None:
            stream = template.stream(**ctx)
            stream.enable_buffering(buffer)
            for _ in stream:
                pass

        rows.append(
            {
                "case": f"{n:>6,} rows ({size / 1024:.1f} MiB html)",
                "render KiB": peak_kib(lambda t=template, c=ctx: t.render(**c)),
                "buf=64 KiB": peak_kib(lambda: drain_stream(64)),
                "buf=5 KiB": peak_kib(lambda: drain_stream(5)),
            }
        )
    report("6. Peak allocation: render() vs stream()", rows)


# --------------------------------------------------------------------------- #
# 7. Streaming chunk size
# --------------------------------------------------------------------------- #


def bench_stream_buffer() -> None:
    """Un-buffered streaming is a trap — but not for the reason you'd guess.

    Jinja does not care how you drain its generator. The cost lands one layer
    up: every yielded fragment becomes an ASGI `http.response.body` message and
    an HTTP chunked-encoding frame. So this measures the generator alone *and*
    the same page served through the ASGI stack, because only the second
    number moves.
    """
    import anyio
    import httpx
    from starlette.applications import Starlette
    from starlette.responses import StreamingResponse
    from starlette.routing import Route

    env = app_env(auto_reload=False)
    template = env.get_template("tasks/report.html")
    ctx = {"request": _FakeRequest(), "tasks": make_tasks(2_000)}

    def chunks(buffer: int):
        stream = template.stream(**ctx)
        if buffer:
            stream.enable_buffering(buffer)
        return stream

    def endpoint(buffer: int):
        async def handler(request):
            return StreamingResponse(iter(chunks(buffer)), media_type="text/html")

        return handler

    async def serve(buffer: int) -> float:
        app = Starlette(routes=[Route("/", endpoint(buffer))])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://bench") as client:
            await client.get("/")
            samples = []
            for _ in range(5):
                start = perf_counter()
                await client.get("/")
                samples.append((perf_counter() - start) * 1000)
            return statistics.median(samples)

    rows = []
    for case, buffer in [("no buffering", 0), ("buffer=16", 16), ("buffer=64", 64), ("buffer=512", 512)]:
        rows.append(
            {
                "case": case,
                "chunks": sum(1 for _ in chunks(buffer)),
                "jinja ms": timed(lambda b=buffer: sum(1 for _ in chunks(b)), iterations=5, repeats=5) / 1000,
                "over ASGI ms": anyio.run(serve, buffer),
            }
        )
    report("7. Streaming chunk size (2,000-row page)", rows)


# --------------------------------------------------------------------------- #
# 8. Blocking the event loop
# --------------------------------------------------------------------------- #


def bench_event_loop() -> None:
    """Rendering is CPU-bound and synchronous. Where it runs decides whether one
    slow page also makes every *other* page slow.

    A pinger task hammers a trivial endpoint while heavy renders run. The
    number that matters is not the ping's own latency but the largest *gap*
    between two consecutive pings: that gap is how long the event loop was
    unavailable to everybody else.
    """
    import anyio
    import httpx
    from fastapi import FastAPI
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import StreamingResponse

    env = app_env(auto_reload=False)
    template = env.get_template("tasks/report.html")
    heavy_ctx = {"request": _FakeRequest(), "tasks": make_tasks(4_000)}

    app = FastAPI()

    @app.get("/heavy-async")
    async def heavy_async() -> str:
        return template.render(**heavy_ctx)

    @app.get("/heavy-sync")
    def heavy_sync() -> str:  # Starlette runs this in the threadpool
        return template.render(**heavy_ctx)

    @app.get("/heavy-threadpool")
    async def heavy_threadpool() -> str:
        return await run_in_threadpool(template.render, **heavy_ctx)

    @app.get("/heavy-stream")
    async def heavy_stream() -> StreamingResponse:
        stream = template.stream(**heavy_ctx)
        stream.enable_buffering(512)
        return StreamingResponse(iter(stream), media_type="text/html")

    @app.get("/ping")
    async def ping() -> str:
        return "pong"

    async def measure(heavy_path: str) -> dict[str, float]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://bench", timeout=60) as client:
            await client.get("/ping")
            await client.get(heavy_path)  # warm the template and the threadpool
            stamps: list[float] = []
            done = False

            async def heavy() -> None:
                nonlocal done
                started = perf_counter()
                for _ in range(4):
                    await client.get(heavy_path)
                nonlocal elapsed
                elapsed = (perf_counter() - started) * 1000
                done = True

            async def pinger() -> None:
                # The `done` check goes *after* the stamp on purpose: the last
                # stall only becomes visible on the ping that follows it, and
                # `while not done` would exit before recording it.
                while True:
                    await client.get("/ping")
                    stamps.append(perf_counter())
                    if done:
                        return
                    await anyio.sleep(0)

            elapsed = 0.0
            async with anyio.create_task_group() as tg:
                tg.start_soon(pinger)
                await anyio.sleep(0.02)  # let the pinger settle into its loop
                tg.start_soon(heavy)

            gaps = [(b - a) * 1000 for a, b in zip(stamps, stamps[1:], strict=False)]
            return {
                "4 renders ms": elapsed,
                "pings served": len(stamps),
                "worst stall ms": max(gaps) if gaps else 0.0,
            }

    rows = []
    for case, path in [
        ("async def — renders on the loop", "/heavy-async"),
        ("def — Starlette threadpool", "/heavy-sync"),
        ("async def + run_in_threadpool", "/heavy-threadpool"),
        ("async def + StreamingResponse", "/heavy-stream"),
    ]:
        rows.append({"case": case, **anyio.run(measure, path)})
    report("8. Event-loop availability during 4 heavy renders", rows)


# --------------------------------------------------------------------------- #

SECTIONS: dict[str, Callable[[], None]] = {
    "environment": bench_environment,
    "coldstart": bench_cold_start,
    "macros": bench_macros,
    "imports": bench_import_context,
    "whitespace": bench_whitespace,
    "memory": bench_memory,
    "stream": bench_stream_buffer,
    "eventloop": bench_event_loop,
}


def main() -> None:
    wanted = [a for a in sys.argv[1:] if not a.startswith("-")] or list(SECTIONS)
    unknown = [w for w in wanted if w not in SECTIONS]
    if unknown:
        raise SystemExit(f"unknown section(s): {', '.join(unknown)}\navailable: {', '.join(SECTIONS)}")
    for name in wanted:
        SECTIONS[name]()
    if "--json" in sys.argv:
        print(json.dumps(RESULTS, indent=2))
    else:
        print()


if __name__ == "__main__":
    main()
