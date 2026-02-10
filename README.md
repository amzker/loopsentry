# LoopSentry

### **Asyncio Event Loop Blockers Detector & Analyzer**
- utility for detecting blocking calls in asyncio event loops

![LoopSentry Interface](https://raw.githubusercontent.com/amzker/loopsentry/master/images/frontview.png)

### **Installation**

```bash
uv add loopsentry
```
pip way

```bash
pip install loopsentry
```

### **Usage**
1. Basic Usage

```python
import asyncio
from loopsentry import LoopSentry

async def main():
    # start monitoring (default threshold: 0.1s) ie: if blocks is >= 0.1 , it is logged
    sentry = LoopSentry(threshold=0.1,
                        capture_args=False, # this is basically do you want to capture arguments of functions at the time
                        detect_async_bottlenecks=False) # other than blocking it also detects slow asyncio tasks which are going on. helps to find bottlenecks
    sentry.start()

    print("Running...")
    ... # rest of your application

if __name__ == "__main__":
    asyncio.run(main())
```

2. Use inside Uvicorn/gunicorn workers in fastapi
- you need to put it inside a `lifespan` context manager , so if you use multiple workers eachh gets their own LoopSentry instance

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from loopsentry import LoopSentry

@asynccontextmanager
async def lifespan(app: FastAPI):
    sentry = LoopSentry()
    sentry.start()
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"message": "I am being monitored!"}
```

### **Log Analysis**

```bash
uv run loopsentry analyze -d log_directory
```
NOTE: if you used pip to install then

```bash
loopsentry analyze -d log_directory
```

### CLI Controls
*   **`/text`**: Search/Filter logs.
*   **`g`**: Group view (see top offenders).
*   **`s`**: Sort by Duration vs Time.
*   **`ID`**: Enter an ID number to view stack trace & arguments.

## Gallery

### 1. Traceback with Argument Capture
Pinpoint exactly *where* the code blocked and *what* arguments caused it.
![Traceback View](https://raw.githubusercontent.com/amzker/loopsentry/master/images/traceback_blocker_view.png)

### 2. Grouped View (Top Offenders)
Quickly identify which files or functions are causing the most performance hits.
![Grouped View](https://raw.githubusercontent.com/amzker/loopsentry/master/images/grouped_view.png)

### 3. Slow Async Task Detection
Detect tasks that are async but still taking too long (Bottlenecks).
![Slow Async View](https://raw.githubusercontent.com/amzker/loopsentry/master/images/slowasync_request_view.png)

