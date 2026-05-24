# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`appbase` is a Python 3.14+ library providing reusable application building blocks: configuration management, SQLite ORM, SQL query building, authentication, and authorization. It is designed as a dependency for other projects, not a standalone application.

## Commands

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest test/ -v

# Run a single test
uv run pytest test/test_config.py::test_root_config -v

# Lint and format
uv run ruff check src/ test/
uv run ruff format src/ test/

# Type check
uv run ty check src/
```

## Architecture

### Module dependency graph

```
users.py ──→ database.py ──→ statements.py
    │
    └──→ security.py

config.py        (independent)
permissions.py   (independent)
```

### config.py — Configuration management

Multi-source configuration system with lazy loading and caching. Sources include file paths (`PathSource`), in-memory strings/dicts, and OS-specific directories (`PlatformdirsSource`). Supports TOML, JSON, and YAML (`yaml` uses safe load/dump; `unsafe_yaml` opts into arbitrary Python objects). Uses Pydantic `TypeAdapter` (cached in `TYPEADAPTER_CACHE`) for validation/serialization. Configuration classes are registered via `@section` and `@root` decorators on `ConfigConfig`.

### database.py — SQLite ORM

Wraps `sqlite3` with three cursor tiers:
- `CursorBase`: Statement execution, transactions, varparse helpers
- `EZCursor`: CRUD convenience methods (create, insert, select, update, delete, count)
- `ModelCursor[M]`: Type-parameterized cursor bound to a specific model

`Database` manages connection lifecycle, registers type adapters/converters (datetime, Path, timedelta), and sets SQLite pragmas (WAL mode, `busy_timeout`, mmap, foreign keys, secure delete); the connect handshake performs no writes, so a burst of simultaneous first-connects does not collide. Routine free-page reclamation runs on close via `PRAGMA incremental_vacuum` (best-effort; skipped if the DB is busy). Full compaction is opt-in via `Database.vacuum()` — it needs a database-wide exclusive lock, so run it only in a maintenance window on an idle connection, never under concurrent access. See **Concurrency** below for the multi-writer rules.

### statements.py — SQL query builders

Fluent/chainable API: `Create`, `Select`, `Insert`, `Update`, `Delete`, `Count`. All inherit from `Statement[C]` where `C` is the model type. Key function `annotations_from()` introspects dataclass/Pydantic model fields to auto-generate column definitions. Type annotations map to SQL types (str→TEXT, int→INTEGER, etc.) and `Annotated` metadata maps to constraints (e.g., `Annotated[int, "PRIMARY KEY"]`).

### security.py — Password hashing and JWT tokens

Argon2 for password hashing, HS256 JWT for tokens with expiration.

### permissions.py — RBAC authorization

Rule-based authorization with PERMIT/DENY/PASS decisions. Uses protocols (`HasId`, `HasOwner`, `HasPermissions`, `HasRole`) for duck-typed checks against subjects and resources.

### users.py — Lightweight user system

`User` dataclass + `Users` store built on `database.py` and `security.py`: registration (`add`), lookup (`get`/`get_by_id`/`all`/`count`), password auth (`login` with transparent argon2 rehash, `set_password`), and optional JWT issuance/verification (`issue_token`/`authenticate_token`). Construct `Users(db, token_secret=...)` then call `create_table()`.

## Concurrency (multiple writers)

appbase is tuned for several writer processes/connections on one database: `connect_raw` sets WAL mode and `busy_timeout = timeout * 1000` (30s default), and `connect()` performs no writes (so simultaneous cold connects don't collide). Beyond that, follow these rules — each maps to a measured boundary in `stress/` (`uv run python stress/concurrency.py`; details in `stress/FINDINGS.md`):

- **Wrap writes in `database.retry_on_locked(...)`** as the app-level backstop for lock contention that slips past `busy_timeout`. SQLite serializes writers (one at a time), so concurrency adds latency, not write throughput.
- **Never hold a streaming read (`ModelCursor.iter()` / `CursorBase.parsed()`) open across a write on the same connection.** In WAL it pins a read snapshot; once another connection commits, the next write fails `database is locked` *immediately* — neither `busy_timeout` nor `retry_on_locked` can recover it. Materialize first (`.all()`), read on a separate connection from the one you write on, or page with keyset pagination.
- **`Database.vacuum()` is maintenance-window-only** (needs a DB-wide exclusive lock; fails under any concurrent writer). Routine reclamation already happens via `incremental_vacuum` on close.

## Key Patterns

- **Type-driven SQL generation**: Python type annotations on dataclass/Pydantic fields drive table creation and column definitions. Use `Annotated` for SQL constraints (e.g., `INTPK = Annotated[int, "PRIMARY KEY"]`).
- **Fluent APIs**: Statement builders and cursor methods use method chaining.
- **Dual model support**: Both `@dataclass` and Pydantic `BaseModel` are supported throughout database and statement modules.
- **Protocol-based design**: Authorization uses structural typing protocols rather than inheritance.
- **Lazy caching**: Config data is loaded on first access and cached; use `reload()` to refresh.

## Ruff Rules

E, F, I, UP, B, SIM, RUF — targeting Python 3.14.
