# LoopSentry

### Asyncio Event Loop Blocker Detector & Analyzer

Detect blocking calls, slow async tasks, and performance bottlenecks in your asyncio applications. Captures stack traces, function arguments, CPU/memory/GC metrics. Generates standalone HTML reports and CSV exports.

### HTML Report 
![Checkout Full HTML Report](https://htmlpreview.github.io/?https://github.com/amzker/loopsentry/blob/master/examples/report.html)
![HTML Report](https://raw.githubusercontent.com/amzker/loopsentry/master/images/html_report.png)


![LoopSentry Interface](https://raw.githubusercontent.com/amzker/loopsentry/master/images/frontview.png)

## Installation

```bash
pip install loopsentry
```
OR
```bash
uv add loopsentry
```

## Quick Start

```python
import asyncio
from loopsentry import LoopSentry

async def main():
    sentry = LoopSentry(threshold=0.1)
    sentry.start()
    # ... your application

asyncio.run(main())
```

## Configuration

```python
sentry = LoopSentry(
    base_dir="sentry_logs",          # log output directory
    threshold=0.1,                   # blocking detection threshold (seconds)
    async_threshold=1.0,             # slow async task threshold (seconds)
    capture_args=True,               # capture function arguments at block time
    detect_async_bottlenecks=True,   # track slow async tasks
)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `base_dir` | `"sentry_logs"` | Directory for log output |
| `threshold` | `0.1` | Seconds before a blocking call is flagged |
| `async_threshold` | Same as `threshold` | Separate threshold for slow async tasks |
| `capture_args` | `False` | Capture local variables from stack frames |
| `detect_async_bottlenecks` | `False` | Monitor async task completion times |

## FastAPI / Uvicorn

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from loopsentry import LoopSentry

@asynccontextmanager
async def lifespan(app: FastAPI):
    sentry = LoopSentry(
        threshold=0.1,
        async_threshold=2.0,
        capture_args=True,
        detect_async_bottlenecks=True,
    )
    sentry.start()
    yield

app = FastAPI(lifespan=lifespan)
```

## What It Detects

| Pattern | Type | Example |
|---------|------|---------|
| Blocking sleep | Block | `time.sleep()` in async context |
| Sync HTTP | Block | `requests.get()` instead of aiohttp/httpx |
| Sync DB calls | Block | PyMongo, sqlite3 sync operations |
| Subprocess | Block | `subprocess.run()` |
| CPU loops | Block | Tight loops without yielding |
| Slow coroutines | Async | Tasks exceeding `async_threshold` |
| Crashes | Crash | Process killed during a block |

## CLI

### Interactive TUI

```bash
loopsentry analyze                          # auto-select latest logs
loopsentry analyze -d sentry_logs/          # specific directory
```

| Key | Action |
|-----|--------|
| `<ID>` | View event detail (stack trace, args, metrics) |
| `n` / `p` | Next / Previous page |
| `g` | Toggle group view (top offenders) |
| `s` | Cycle sort: time → duration → cpu → memory → type |
| `s:cpu` | Sort by specific column |
| `/text` | Search/filter events |
| `q` | Quit |

### HTML Report

```bash
loopsentry analyze -d sentry_logs/ --html
loopsentry analyze -d sentry_logs/ --html -o report.html
```

Generates a standalone HTML file — no dependencies, no internet required. Open directly in any browser.


[▶ View Sample Report](https://htmlpreview.github.io/?https://github.com/amzker/loopsentry/blob/master/examples/report.html)


### CSV Export

```bash
loopsentry analyze -d sentry_logs/ --csv
loopsentry analyze -d sentry_logs/ --csv -o data.csv
```

### Full CLI Reference

```
loopsentry analyze [OPTIONS]

  -d, --dir DIR          Directory to scan
  -f, --file FILE        Specific .jsonl file to scan
  --html                 Generate standalone HTML report
  --csv                  Generate CSV report
  --sort COLUMN          Sort by: time | duration | cpu | memory | type
  -o, --output PATH      Output file path for HTML/CSV
```

## Example

The [`examples/`](examples/) directory contains a complete FastAPI application that deliberately triggers every type of blocking pattern LoopSentry detects.

**Run the demo:**

```bash
cd examples/

# Terminal 1 — start the server
uv run app.py

# Terminal 2 — fire test requests
uv run loadtest.py

# Terminal 1 — stop server (Ctrl+C), then generate report
loopsentry analyze -d example_logs/ --html
```

**Endpoints in the demo app:**

| Endpoint | What it does |
|----------|-------------|
| `GET /healthy` | Clean async endpoint (no block) |
| `GET /users/sync` | Sync SQLite query blocking the loop |
| `POST /hash` | CPU-bound PBKDF2 hashing |
| `GET /external` | Async HTTP via httpx (clean) |
| `GET /external/sync` | Sync HTTP via requests (blocks loop) |
| `GET /sleep/{seconds}` | `time.sleep()` blocking the loop |
| `GET /compute` | CPU-bound loop (5M iterations) |
| `GET /mixed` | Sleep + DB + hashing in one request |



## License

MIT
