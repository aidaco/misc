# appbase SQLite multi-writer stress test

A harness that reproduces and **measures** the multi-writer SQLite boundaries
that ~/Code/audiorotica hit when several writer processes shared one appbase
database. It exercises appbase's *real* connection config
(`appbase.database.connect`: WAL, `busy_timeout = timeout * 1000`, per-row
autocommit), so the numbers reflect what downstream consumers actually get.

This is **not** part of the pytest suite — it is slow, spawns OS processes, and
is non-deterministic by design. Run it by hand when changing connection/pragma
behavior in `database.py` or when sizing a concurrent workload.

## Running

```bash
uv run python stress/concurrency.py                       # all scenarios + tables
uv run python stress/concurrency.py contention --writers 1,2,4,8,16,32 --rows 300
uv run python stress/concurrency.py connect-storm
uv run python stress/concurrency.py staleness
uv run python stress/concurrency.py vacuum
```

## What each scenario probes

| Scenario        | Boundary | origin |
|-----------------|----------|--------|
| `contention`    | Many processes each committing one row per transaction. Sweeps writer counts under three regimes — default `busy_timeout` (30 s), `busy_timeout = 0` (no wait), and `busy_timeout = 0` + app-level retry — reporting throughput, latency percentiles, lock-failure rate, and WAL growth. | audiorotica: "write bursts without retry crashed immediately" |
| `connect_storm` | Many processes opening their **first** connection at the same instant. appbase *used to* run `PRAGMA optimize` (an ANALYZE **write**) on every connect; the write's lock upgrade returned `SQLITE_BUSY` immediately, bypassing `busy_timeout`, so a burst of cold connects failed at 50–88%. **Fixed** (optimize moved to close-only); now a regression guard expecting 0 failures. | **surfaced by this harness** (not seen in audiorotica) |
| `staleness`     | A **streaming** read cursor held open across a write pins a WAL read snapshot; the instant another connection commits, the holder's next write fails `SQLITE_BUSY` **immediately, bypassing `busy_timeout`**, and **no retry recovers** while the cursor stays open. Materializing the read first avoids it. | audiorotica: the real root cause (CR2) |
| `vacuum`        | `Database.vacuum()` needs a DB-wide exclusive lock, so it collides with any concurrent writer. Confirms it is maintenance-window-only. | audiorotica: VACUUM-on-close self-collision |

## Design notes

- **Processes, not threads** — faithful to audiorotica (separate CLI runs). The
  parent never holds an open connection when it forks; each worker opens its
  own. `contention` and `connect_storm` use `multiprocessing` (fork);
  `staleness`/`vacuum` are deterministic two-connection experiments in one
  process (the staleness mechanism only needs *a different connection* to commit
  — process vs thread vs second handle is irrelevant to it).
- **`retry_on_locked`** is appbase's own `database.retry_on_locked` (the harness
  dogfoods it rather than carrying a copy). It is the app-level backstop that
  pairs with the `busy_timeout` appbase already sets — full jitter, capped
  exponential backoff.

See `FINDINGS.md` for the measured boundaries.
