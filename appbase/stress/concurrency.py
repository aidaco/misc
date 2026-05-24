"""Stress-test appbase's SQLite usage to find the multi-writer boundaries.

Background
----------
~/Code/audiorotica ran several writer *processes* against one appbase SQLite
database (per-host fetchers + a pairing pass + a bulk link ingester) and hit
some rough edges. This harness reproduces and *measures* each boundary against
appbase's real connection config (`appbase.database.connect`: WAL,
`busy_timeout = timeout * 1000`, per-row autocommit) so we can state where the
boundaries actually are on this machine instead of guessing.

The four boundaries:

1. contention     - Many writers committing one row per transaction. With no
                    `busy_timeout` (timeout=0) and no retry, transient collisions
                    raise `OperationalError: database is locked` immediately. We
                    sweep writer counts under three regimes (busy_timeout absorbs
                    it / naked / app-level retry) to show the throughput ceiling,
                    latency growth, and failure rate.

2. connect_storm  - Surfaced by this harness, not by audiorotica, and since
                    fixed. appbase *used to* run `PRAGMA optimize` (an ANALYZE
                    *write*) on every connect; the write's read->write lock
                    upgrade returns SQLITE_BUSY immediately on contention,
                    bypassing busy_timeout, so a burst of simultaneous *first*
                    connects failed (50-88%) even at busy_timeout=30s. optimize
                    now runs only on close, so connect() is read-only; this
                    scenario is the regression guard (expects 0 failures).

3. staleness      - The real audiorotica root cause. A *streaming* read cursor
                    held open across writes pins a WAL read snapshot; the instant
                    another connection commits, the next write on the holding
                    connection fails SQLITE_BUSY *immediately* -- bypassing
                    busy_timeout -- and no retry can recover while the cursor
                    stays open. Materializing the read first avoids it.

4. vacuum         - `Database.vacuum()` needs a DB-wide exclusive lock, so it
                    collides with any concurrent writer.

Run:
    uv run python stress/concurrency.py                 # everything + findings
    uv run python stress/concurrency.py contention --writers 1,2,4,8,16,32
    uv run python stress/concurrency.py connect-storm
    uv run python stress/concurrency.py staleness
    uv run python stress/concurrency.py vacuum
"""

import multiprocessing as mp
import shutil
import sqlite3
import tempfile
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import BrokenBarrierError

import cyclopts
from rich.console import Console
from rich.table import Table

import appbase

# Faithful to audiorotica: separate OS processes, each its own connection. fork
# is fine because the parent never holds an open connection when it spawns
# workers -- every worker opens its own connection inside its target function.
CTX = mp.get_context("fork")
console = Console()
app = cyclopts.App(help="Find appbase's SQLite multi-writer boundaries.")


@dataclass
class Event:
    """A trivial write target. `id` is a rowid alias (auto), so inserts that omit
    it adapt their column list to the values passed (see statements.Insert)."""

    id: appbase.database.INTPK
    worker: int
    seq: int
    payload: str
    created: datetime


def is_lock_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "lock" in message or "busy" in message


def pct(values: list[float], p: float) -> float:
    """Nearest-rank percentile of an unsorted list (p in 0..100)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))
    return ordered[k]


def setup_db(uri: Path) -> None:
    """Create the events table on its own connection, then close it -- so the
    parent holds nothing open when it forks workers."""
    db = appbase.database.connect(uri)
    db.table(Event).create().if_not_exists().execute()
    db.close()


def seed_rows(uri: Path, n: int) -> None:
    db = appbase.database.connect(uri)
    cur = db.table(Event)
    for seq in range(n):
        cur.insert().values(
            worker=-1, seq=seq, payload="seed", created=datetime.now(UTC)
        ).execute()
    db.close()


# --------------------------------------------------------------------------- #
# Scenario 1: contention sweep
# --------------------------------------------------------------------------- #


def hammer_worker(
    barrier: object,
    result_q: object,
    uri: str,
    timeout: int,
    worker_id: int,
    rows: int,
    payload: str,
    use_retry: bool,
) -> None:
    """One writer process: open a connection, then commit `rows` single-row
    inserts as fast as possible. Reports a summary dict; never raises out, so the
    parent's queue drain can't deadlock."""
    result: dict = {
        "worker": worker_id,
        "written": 0,
        "failures": 0,
        "first_error": None,
        "crashed": None,
        "latencies": [],
        "start": None,
        "end": None,
    }

    # Connection setup is NOT the thing under test here -- the cold-connect storm
    # is its own scenario (`connect_storm`). Retry the handshake so a connect-time
    # collision can't contaminate the insert-contention numbers, and so a setup
    # failure can't strand peers on the barrier (we abort it instead of hanging).
    try:

        def _open() -> appbase.database.Database:
            db = appbase.database.connect(uri, timeout=timeout)
            db.connect()  # run the pragma handshake now, before the timed phase
            return db

        db = appbase.database.retry_on_locked(
            _open, attempts=20, base_delay=0.02, max_delay=1.0
        )
        cur = db.table(Event)
    except BaseException as exc:  # report a setup failure; don't hang peers
        result["crashed"] = f"setup: {type(exc).__name__}: {exc}"
        with suppress(Exception):
            barrier.abort()  # release peers immediately instead of a 60s hang
        result_q.put(result)
        return

    try:
        with suppress(BrokenBarrierError):
            barrier.wait(timeout=60)  # all writers start hammering together
        result["start"] = time.time()
        for seq in range(rows):
            t0 = time.perf_counter()
            try:
                op = (
                    cur.insert()
                    .values(
                        worker=worker_id,
                        seq=seq,
                        payload=payload,
                        created=datetime.now(UTC),
                    )
                    .execute
                )
                appbase.database.retry_on_locked(op) if use_retry else op()
                result["written"] += 1
            except sqlite3.OperationalError as exc:
                if is_lock_error(exc):
                    result["failures"] += 1
                    if result["first_error"] is None:
                        result["first_error"] = str(exc)
                else:
                    raise
            result["latencies"].append((time.perf_counter() - t0) * 1000)
        result["end"] = time.time()
        db.close()
    except BaseException as exc:  # report, never hang the parent's queue drain
        result["crashed"] = f"{type(exc).__name__}: {exc}"
        result["start"] = result["start"] or time.time()
        result["end"] = time.time()
    result_q.put(result)


@dataclass
class RunResult:
    writers: int
    written: int
    failures: int
    throughput: float
    p50: float
    p99: float
    maxlat: float
    wal_mb: float
    crashes: list[str]


def run_contention(
    uri: Path, *, writers: int, rows: int, payload: str, timeout: int, use_retry: bool
) -> RunResult:
    setup_db(uri)
    barrier = CTX.Barrier(writers)
    q = CTX.Queue()
    procs = [
        CTX.Process(
            target=hammer_worker,
            args=(barrier, q, str(uri), timeout, w, rows, payload, use_retry),
        )
        for w in range(writers)
    ]
    for p in procs:
        p.start()
    results = [q.get() for _ in range(writers)]  # drain before join (avoid deadlock)
    for p in procs:
        p.join()

    latencies = [lat for r in results for lat in r["latencies"]]
    starts = [r["start"] for r in results if r["start"] is not None]
    ends = [r["end"] for r in results if r["end"] is not None]
    wall = (max(ends) - min(starts)) if starts and ends else 0.0
    written = sum(r["written"] for r in results)
    wal = uri.with_name(uri.name + "-wal")
    wal_mb = (wal.stat().st_size / 1e6) if wal.exists() else 0.0

    return RunResult(
        writers=writers,
        written=written,
        failures=sum(r["failures"] for r in results),
        throughput=(written / wall) if wall > 0 else 0.0,
        p50=pct(latencies, 50),
        p99=pct(latencies, 99),
        maxlat=max(latencies) if latencies else 0.0,
        wal_mb=wal_mb,
        crashes=[r["crashed"] for r in results if r["crashed"]],
    )


@app.command
def contention(
    writers: str = "1,2,4,8,16,32",
    rows: int = 300,
    payload_bytes: int = 256,
) -> None:
    """Sweep concurrent writer counts under three lock-handling regimes."""
    counts = [int(w) for w in writers.split(",")]
    payload = "x" * payload_bytes
    regimes = [
        ("busy_timeout 30s (default)", 30, False),
        ("busy_timeout 0 (no wait, no retry)", 0, False),
        ("busy_timeout 0 + app retry", 0, True),
    ]
    workdir = Path(tempfile.mkdtemp(prefix="appbase-stress-"))
    console.rule("[bold]Scenario 1: write contention[/bold]")
    console.print(
        f"{rows} single-row autocommit inserts per writer, "
        f"{payload_bytes} B payload, separate processes.\n"
    )
    try:
        for label, timeout, use_retry in regimes:
            table = Table(title=label, title_style="bold cyan")
            for col in (
                "writers",
                "written",
                "lock fails",
                "fail %",
                "rows/s",
                "p50 ms",
                "p99 ms",
                "max ms",
                "WAL MB",
            ):
                table.add_column(col, justify="right")
            for n in counts:
                uri = workdir / f"c_{timeout}_{int(use_retry)}_{n}.db"
                res = run_contention(
                    uri,
                    writers=n,
                    rows=rows,
                    payload=payload,
                    timeout=timeout,
                    use_retry=use_retry,
                )
                attempted = res.written + res.failures
                fail_pct = (100 * res.failures / attempted) if attempted else 0.0
                style = "red" if res.failures else None
                table.add_row(
                    str(res.writers),
                    str(res.written),
                    str(res.failures),
                    f"{fail_pct:.1f}",
                    f"{res.throughput:,.0f}",
                    f"{res.p50:.2f}",
                    f"{res.p99:.2f}",
                    f"{res.maxlat:.1f}",
                    f"{res.wal_mb:.1f}",
                    style=style,
                )
                if res.crashes:
                    console.print(f"  [red]crash @ {n} writers:[/red] {res.crashes[0]}")
            console.print(table)
            console.print()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Scenario 2: cold-connect storm
# --------------------------------------------------------------------------- #


def connect_worker(
    barrier: object, result_q: object, uri: str, timeout: int, use_retry: bool
) -> None:
    """Open one fresh connection at the barrier and report any failure. With
    `use_retry`, wrap the handshake in retry_on_locked."""
    with suppress(BrokenBarrierError):
        barrier.wait(timeout=30)
    err = None
    try:

        def _open() -> appbase.database.Database:
            db = appbase.database.connect(uri, timeout=timeout)
            db.connect()  # the pragma handshake; PRAGMA optimize writes (ANALYZE)
            return db

        db = (
            appbase.database.retry_on_locked(
                _open, attempts=20, base_delay=0.02, max_delay=1.0
            )
            if use_retry
            else _open()
        )
        db.close()
    except sqlite3.OperationalError as exc:
        err = str(exc)
    except BaseException as exc:  # report, never hang the parent's queue drain
        err = f"{type(exc).__name__}: {exc}"
    result_q.put(err)


def run_connect_storm(
    uri: Path, *, writers: int, timeout: int, use_retry: bool
) -> list[str]:
    setup_db(uri)  # create the db in WAL with the table; parent then holds nothing
    barrier = CTX.Barrier(writers)
    q = CTX.Queue()
    procs = [
        CTX.Process(
            target=connect_worker, args=(barrier, q, str(uri), timeout, use_retry)
        )
        for _ in range(writers)
    ]
    for p in procs:
        p.start()
    errs = [q.get() for _ in range(writers)]
    for p in procs:
        p.join()
    return [e for e in errs if e]


@app.command
def connect_storm(writers: str = "2,4,8,16,32,64", timeout: int = 30) -> None:
    """Many processes opening their *first* connection at the same instant.

    Regression guard. appbase *used to* run `PRAGMA optimize` on every connect;
    optimize performs an ANALYZE write, and the write's read->write lock upgrade
    returns SQLITE_BUSY *immediately* on contention (deadlock avoidance), bypassing
    busy_timeout -- so a burst of simultaneous cold connects failed even at
    busy_timeout = 30 s. optimize now runs only on close, so connect() is
    read-only and this should report 0 failures. Nonzero == a connect-time write
    regressed.
    """
    counts = [int(w) for w in writers.split(",")]
    console.rule("[bold]Scenario 2: cold-connect storm[/bold]")
    console.print(
        f"All writers call connect() at once; busy_timeout = {timeout * 1000} ms. "
        f"connect() is read-only (PRAGMA optimize moved to close), so this should "
        f"report 0 failures; nonzero means a connect-time write regressed.\n"
    )
    workdir = Path(tempfile.mkdtemp(prefix="appbase-stress-"))
    try:
        table = Table()
        table.add_column("simultaneous connects", justify="right")
        table.add_column("connect() failures", justify="right")
        table.add_column("fail %", justify="right")
        table.add_column("failures w/ retry", justify="right")
        for n in counts:
            no_retry = run_connect_storm(
                workdir / f"cs_n_{n}.db", writers=n, timeout=timeout, use_retry=False
            )
            retried = run_connect_storm(
                workdir / f"cs_y_{n}.db", writers=n, timeout=timeout, use_retry=True
            )
            table.add_row(
                str(n),
                str(len(no_retry)),
                f"{100 * len(no_retry) / n:.0f}",
                str(len(retried)),
                style="red" if no_retry else None,
            )
        console.print(table)
        console.print(
            "connect()'s handshake performs no writes, so a cold-connect burst no "
            "longer contends. (Before the fix, [bold]PRAGMA optimize = 0x10002[/bold] "
            "-- an ANALYZE write -- failed 50-88% here; busy_timeout did not cover "
            "it, but app-level connect retry did.)\n"
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Scenario 3: WAL snapshot staleness
# --------------------------------------------------------------------------- #


@dataclass
class StaleResult:
    case: str
    outcome: str
    latency_ms: float
    note: str


def run_staleness_case(
    uri: Path, *, materialize: bool, use_retry: bool, timeout: int
) -> StaleResult:
    """Reproduce the snapshot-staleness boundary on two real connections.

    `holder` opens a read over the events table. If `materialize`, we drain it
    into a list (closing the read txn) before writing; otherwise we hold the
    streaming cursor open. `other` then commits, making holder's pinned snapshot
    stale. Finally holder writes: with the streaming cursor still open this fails
    SQLITE_BUSY immediately, no matter the busy_timeout.
    """
    holder = appbase.database.connect(uri, timeout=timeout)
    other = appbase.database.connect(uri, timeout=timeout)
    try:
        read_cur = holder.table(Event)
        if materialize:
            rows = list(read_cur.select().execute().iter())  # read txn closes here
            _ = rows[0]
            note = "read fully materialized before write (the audiorotica fix)"
        else:
            stream = read_cur.select().execute().iter()
            _ = next(stream)  # snapshot pinned; cursor left open across the write
            note = "streaming read cursor held open across the write"

        # Another connection commits -> holder's snapshot is now stale.
        other.table(Event).insert().values(
            worker=-2, seq=0, payload="external", created=datetime.now(UTC)
        ).execute()

        write_cur = holder.table(Event)
        op = (
            write_cur.insert()
            .values(worker=-3, seq=0, payload="holder", created=datetime.now(UTC))
            .execute
        )
        t0 = time.perf_counter()
        try:
            # Tiny budget + near-zero delays: enough to prove retry can't recover
            # a stale snapshot without making the demo wait out a 30s budget.
            if use_retry:
                appbase.database.retry_on_locked(
                    op, attempts=5, base_delay=0.01, max_delay=0.05
                )
            else:
                op()
            outcome = "survived"
        except sqlite3.OperationalError as exc:
            outcome = f"FAILED: {exc}"
        latency_ms = (time.perf_counter() - t0) * 1000
    finally:
        holder.close()
        other.close()

    label = "materialized" if materialize else "streaming"
    if use_retry:
        label += " + retry(5)"
    return StaleResult(label, outcome, latency_ms, note)


@app.command
def staleness() -> None:
    """Show a streaming read held across a write fails the instant another
    connection commits -- and that busy_timeout and retry don't save it."""
    console.rule("[bold]Scenario 3: WAL snapshot staleness[/bold]")
    timeout = 30
    console.print(
        f"Two connections, busy_timeout = {timeout * 1000} ms. A failure latency "
        f"far below {timeout * 1000} ms proves busy_timeout is bypassed.\n"
    )
    workdir = Path(tempfile.mkdtemp(prefix="appbase-stress-"))
    try:
        cases = [
            dict(materialize=False, use_retry=False),
            dict(materialize=True, use_retry=False),
            dict(materialize=False, use_retry=True),
        ]
        table = Table(show_lines=True)
        for col, just in (
            ("read pattern", "left"),
            ("holder write", "left"),
            ("latency ms", "right"),
            ("note", "left"),
        ):
            table.add_column(col, justify=just)
        for i, case in enumerate(cases):
            uri = workdir / f"stale_{i}.db"
            setup_db(uri)
            seed_rows(uri, 200)  # enough rows that one fetch leaves the cursor open
            res = run_staleness_case(uri, timeout=timeout, **case)
            survived = res.outcome == "survived"
            table.add_row(
                res.case,
                f"[green]{res.outcome}[/green]"
                if survived
                else f"[red]{res.outcome}[/red]",
                f"{res.latency_ms:.2f}",
                res.note,
            )
        console.print(table)
        console.print()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Scenario 3: VACUUM under concurrency
# --------------------------------------------------------------------------- #


@app.command
def vacuum() -> None:
    """Show Database.vacuum() collides with a concurrent writer (needs an
    exclusive lock), confirming it is maintenance-window only."""
    console.rule("[bold]Scenario 4: VACUUM under a concurrent writer[/bold]")
    timeout = 2  # short, so vacuum gives up quickly instead of waiting 30s
    workdir = Path(tempfile.mkdtemp(prefix="appbase-stress-"))
    try:
        uri = workdir / "vac.db"
        setup_db(uri)
        seed_rows(uri, 50)
        holder = appbase.database.connect(uri)
        vac = appbase.database.connect(uri, timeout=timeout)
        try:
            conn = holder.connect()
            conn.execute("BEGIN IMMEDIATE")  # acquire and hold the WAL write lock
            conn.execute(
                "INSERT INTO event(worker, seq, payload, created) VALUES (?,?,?,?)",
                (-9, 0, "lockholder", datetime.now(UTC).isoformat()),
            )
            t0 = time.perf_counter()
            try:
                vac.vacuum()
                outcome = "[green]completed[/green] (no writer lock was held?!)"
            except sqlite3.OperationalError as exc:
                outcome = f"[red]blocked then failed: {exc}[/red]"
            dt = (time.perf_counter() - t0) * 1000
            conn.execute("ROLLBACK")
        finally:
            holder.close()
            vac.close()
        console.print(
            f"Writer holds BEGIN IMMEDIATE; another connection calls vacuum() "
            f"(busy_timeout = {timeout * 1000} ms):"
        )
        console.print(f"  -> {outcome}  (after {dt:.0f} ms)\n")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@app.default
def run_all(
    writers: str = "1,2,4,8,16,32",
    rows: int = 300,
    payload_bytes: int = 256,
) -> None:
    """Run every scenario and print the boundaries found."""
    console.print(
        f"[bold]appbase SQLite multi-writer stress test[/bold]\n"
        f"sqlite {sqlite3.sqlite_version}, "
        f"{CTX.cpu_count() if hasattr(CTX, 'cpu_count') else mp.cpu_count()} CPUs\n"
    )
    contention(writers=writers, rows=rows, payload_bytes=payload_bytes)
    connect_storm()
    staleness()
    vacuum()


if __name__ == "__main__":
    app()
