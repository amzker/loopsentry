# Changelog

## v1.1.1 — 2026-03-09

### Core Improvements

**Per-Core CPU Monitoring**
- System metrics now capture per-core CPU usage (`cpu_per_core`) at each event via `psutil.cpu_percent(percpu=True)`
- `cpu_percent` is now the system-wide average (sum of all cores / core count) instead of raw per-process value which could exceed 100%
- Per-core data displayed in both HTML report (color-coded badges) and TUI detail view

**Signal Handling Fix**
- Fixed Ctrl+C hang: signal handler now correctly calls `stop()`, restores default signal behavior, and re-raises the signal
- Process terminates cleanly even with multiple uvicorn workers

**Analyzer Enhancements**
- Added `hint` field for transition blocks 
- Added `async_total_time` stat — tracks cumulative duration of slow async tasks separately from blocking time
- Fixed `avg_duration` to only count blocking events (previously included async events)

**CLI**
- Added `--version` flag via `importlib.metadata`

### HTML Report Overhaul

- **Grouped View (default)** — events grouped by offending user-code location, sorted by total duration. Shows count, total, avg, CPU range per group
- **Timeline View** — flat chronological list with per-column filtering and 1000/page pagination
- **Stable Event IDs** — each event gets a permanent `#ID` (0, 1, 2...) that never changes with sorting/filtering
- **Per-core CPU** in detail panel — color-coded per-core breakdown (green/orange/red)
- **Stat card tooltips** — each summary metric now explains how it's calculated and notes that times are cumulative sums, not wall-clock
- **Column headers in groups** — expanded groups show sub-headers so columns are always readable
- Removed timeline bar chart
- Full-width layout

### Examples

**New: `app_async.py`**
- Fully async version of the demo app using `aiosqlite`, `aiohttp`, `asyncio.to_thread`, `asyncio.sleep`
- `SharedAiohttpSession` — lock-based lazy singleton, auto-recreates if closed
- `SharedAiosqlitePool` — connection pool with health checks and SQLite optimizations (WAL, synchronous=NORMAL, cache_size, mmap, temp_store=MEMORY)
- No comments/docstrings — clean reference implementation

**New: `mock_server.py`**
- Local aiohttp mock server replacing httpbin.org for stress testing
- Routes: `/delay/{s}`, `/status/{code}`, `/get`, `/post`, `/anything`
- Runs on `127.0.0.1:9999`

**Upgraded: `loadtest.py`**
- Concurrent load tester (100-1000 configurable concurrency)
- Configurable duration, slow request threshold
- Live progress bar with RPS, success/fail/slow counts
- Generates standalone HTML + JSON reports with per-endpoint breakdown and P50/P95/P99 latencies

**Updated: `app.py`**
- External endpoints now hit local mock server instead of httpbin.org
- Switched from httpx to aiohttp for async HTTP
- Graceful shutdown ensures `sentry.stop()` is called

### Dependencies

- Added `aiohttp`, `aiosqlite`, `orjson` to `[project.optional-dependencies.examples]`

### Documentation

- Added logo
- Added report interpretation guide
- Updated CLI reference with `--version`
- Updated example run instructions for mock server + load tester
