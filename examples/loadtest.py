import asyncio
import httpx
import sys
import time

BASE = "http://0.0.0.0:8000"

SCENARIOS = [
    ("GET", "/healthy", "Healthcheck"),
    ("GET", "/users/sync", "Sync DB read"),
    ("GET", "/users/1", "Single user lookup"),
    ("GET", "/users/5", "Single user lookup"),
    ("POST", "/hash?password=secret123", "CPU: PBKDF2 hash"),
    ("POST", "/hash?password=longpassword", "CPU: PBKDF2 hash"),
    ("GET", "/external", "Async HTTP (clean)"),
    ("GET", "/external/sync", "Sync HTTP (blocks loop)"),
    ("GET", "/sleep/0.5", "Blocking sleep 0.5s"),
    ("GET", "/sleep/1.0", "Blocking sleep 1.0s"),
    ("GET", "/compute", "CPU-bound loop"),
    ("GET", "/mixed", "Mixed workload"),
    ("GET", "/users/sync", "Sync DB read"),
    ("POST", "/hash?password=another", "CPU: PBKDF2 hash"),
    ("GET", "/external/sync", "Sync HTTP (blocks loop)"),
    ("GET", "/mixed", "Mixed workload"),
]


async def run():
    print(f"\n{'='*60}")
    print(f"  LoopSentry Load Test — {len(SCENARIOS)} requests")
    print(f"{'='*60}\n")

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, (method, path, label) in enumerate(SCENARIOS, 1):
            url = BASE + path
            t0 = time.time()
            try:
                if method == "GET":
                    resp = await client.get(url)
                else:
                    resp = await client.post(url)
                elapsed = time.time() - t0
                status = resp.status_code
                marker = "🟢" if elapsed < 0.2 else "🟡" if elapsed < 1.0 else "🔴"
                print(f"  {marker} [{i:02d}/{len(SCENARIOS)}] {label:30s} {elapsed:.3f}s  HTTP {status}")
            except Exception as e:
                print(f"  ❌ [{i:02d}/{len(SCENARIOS)}] {label:30s} FAILED: {e}")

            await asyncio.sleep(0.1)

    print(f"\n{'='*60}")
    print("  Done. Stop the server and run:")
    print("  loopsentry analyze -d example_logs/ --html")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(run())
