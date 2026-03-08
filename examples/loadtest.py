"""
LoopSentry Load Tester
═════════════════════
Hammers the demo FastAPI app with concurrent requests across all endpoint types.
Tracks success/fail/slow per endpoint and generates HTML + JSON reports.

Usage:
    uv run loadtest.py                          # defaults: 100 concurrency, 10 min
    uv run loadtest.py --concurrency 500 --duration 300
    uv run loadtest.py -c 200 -d 60 --slow-threshold 1.0
"""

import asyncio
import httpx
import time
import json
import argparse
import random
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict

BASE = "http://127.0.0.1:8000"

ENDPOINTS = [
    ("GET",  "/healthy",                "Healthcheck"),
    ("GET",  "/users/sync",             "Sync DB Read"),
    ("GET",  "/users/1",                "User Lookup"),
    ("GET",  "/users/5",                "User Lookup"),
    ("POST", "/hash?password=secret123","CPU: PBKDF2 Hash"),
    ("POST", "/hash?password=long",     "CPU: PBKDF2 Hash"),
    ("GET",  "/external/sync",          "Sync HTTP (blocks)"),
    ("GET",  "/sleep/0.5",              "Blocking Sleep 0.5s"),
    ("GET",  "/sleep/1.0",              "Blocking Sleep 1.0s"),
    ("GET",  "/compute",                "CPU-bound Loop"),
    ("GET",  "/mixed",                  "Mixed Workload"),
]


class LoadTester:
    def __init__(self, base_url, concurrency, duration, slow_threshold):
        self.base_url = base_url
        self.concurrency = concurrency
        self.duration = duration
        self.slow_threshold = slow_threshold
        self.results = []
        self.start_time = 0
        self.end_time = 0
        self._lock = asyncio.Lock()
        self._total_sent = 0
        self._running = True

    async def _send_request(self, client, method, path, label):
        url = self.base_url + path
        t0 = time.time()
        status = 0
        error = None
        try:
            if method == "GET":
                resp = await client.get(url)
            else:
                resp = await client.post(url)
            status = resp.status_code
        except Exception as e:
            error = str(e)
        elapsed = time.time() - t0

        result = {
            "method": method,
            "path": path,
            "label": label,
            "status": status,
            "elapsed": round(elapsed, 4),
            "error": error,
            "timestamp": datetime.now().isoformat(),
            "success": status in range(200, 400) and error is None,
            "slow": elapsed >= self.slow_threshold,
        }
        async with self._lock:
            self.results.append(result)
            self._total_sent += 1

        return result

    async def _worker(self, client, sem):
        while self._running:
            method, path, label = random.choice(ENDPOINTS)
            async with sem:
                if not self._running:
                    break
                await self._send_request(client, method, path, label)

    async def _progress_printer(self):
        while self._running:
            elapsed = time.time() - self.start_time
            remaining = self.duration - elapsed
            rps = self._total_sent / max(elapsed, 0.1)
            success = sum(1 for r in self.results if r["success"])
            failed = self._total_sent - success
            slow = sum(1 for r in self.results if r["slow"])
            bar_width = 40
            pct = min(elapsed / self.duration, 1.0)
            filled = int(bar_width * pct)
            bar = "█" * filled + "░" * (bar_width - filled)

            sys.stdout.write(
                f"\r  [{bar}] {pct*100:5.1f}%  "
                f"| {self._total_sent:,} reqs  "
                f"| {rps:.0f} rps  "
                f"| ✅ {success:,}  ❌ {failed:,}  🐢 {slow:,}  "
                f"| {remaining:.0f}s left  "
            )
            sys.stdout.flush()
            await asyncio.sleep(0.5)

    async def run(self):
        print(f"\n{'═'*70}")
        print(f"  LoopSentry Load Tester")
        print(f"  Target:       {self.base_url}")
        print(f"  Concurrency:  {self.concurrency}")
        print(f"  Duration:     {self.duration}s ({self.duration/60:.1f}m)")
        print(f"  Slow thresh:  {self.slow_threshold}s")
        print(f"{'═'*70}\n")

        self.start_time = time.time()
        sem = asyncio.Semaphore(self.concurrency)

        limits = httpx.Limits(
            max_connections=self.concurrency,
            max_keepalive_connections=min(self.concurrency, 100),
        )
        timeout = httpx.Timeout(30.0, connect=10.0)

        async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
            # Start workers — more than concurrency to keep the pipeline saturated
            workers = [asyncio.create_task(self._worker(client, sem)) for _ in range(self.concurrency * 2)]
            progress = asyncio.create_task(self._progress_printer())

            # Wait for duration
            await asyncio.sleep(self.duration)
            self._running = False

            # Let in-flight requests finish (up to 5s grace)
            try:
                await asyncio.wait_for(
                    asyncio.gather(*workers, return_exceptions=True),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                for w in workers:
                    w.cancel()

            progress.cancel()
            try:
                await progress
            except asyncio.CancelledError:
                pass

        self.end_time = time.time()
        sys.stdout.write("\r" + " " * 120 + "\r")
        sys.stdout.flush()
        print(f"\n  ✔ Done. {self._total_sent:,} requests in {self.end_time - self.start_time:.1f}s\n")

    def build_report(self):
        total = len(self.results)
        success = sum(1 for r in self.results if r["success"])
        failed = total - success
        slow = sum(1 for r in self.results if r["slow"])
        durations = [r["elapsed"] for r in self.results]
        durations.sort()
        wall_time = self.end_time - self.start_time

        def percentile(arr, p):
            if not arr:
                return 0
            k = (len(arr) - 1) * (p / 100)
            f = int(k)
            c = f + 1
            if c >= len(arr):
                return arr[-1]
            return arr[f] + (arr[c] - arr[f]) * (k - f)

        # Per-endpoint stats
        by_endpoint = defaultdict(lambda: {"count": 0, "success": 0, "failed": 0, "slow": 0, "durations": [], "errors": []})
        for r in self.results:
            key = f"{r['method']} {r['path']}"
            ep = by_endpoint[key]
            ep["count"] += 1
            ep["label"] = r["label"]
            ep["durations"].append(r["elapsed"])
            if r["success"]:
                ep["success"] += 1
            else:
                ep["failed"] += 1
                if r["error"]:
                    ep["errors"].append(r["error"])
            if r["slow"]:
                ep["slow"] += 1

        endpoints = []
        for key, ep in sorted(by_endpoint.items(), key=lambda x: -x[1]["count"]):
            ep_durs = sorted(ep["durations"])
            endpoints.append({
                "endpoint": key,
                "label": ep["label"],
                "count": ep["count"],
                "success": ep["success"],
                "failed": ep["failed"],
                "slow": ep["slow"],
                "avg": round(sum(ep_durs) / len(ep_durs), 4) if ep_durs else 0,
                "min": round(ep_durs[0], 4) if ep_durs else 0,
                "max": round(ep_durs[-1], 4) if ep_durs else 0,
                "p50": round(percentile(ep_durs, 50), 4),
                "p95": round(percentile(ep_durs, 95), 4),
                "p99": round(percentile(ep_durs, 99), 4),
                "error_sample": list(set(ep["errors"]))[:3],
            })

        report = {
            "generated_at": datetime.now().isoformat(),
            "target": self.base_url,
            "config": {
                "concurrency": self.concurrency,
                "duration_seconds": self.duration,
                "slow_threshold": self.slow_threshold,
            },
            "summary": {
                "total_requests": total,
                "success": success,
                "failed": failed,
                "slow": slow,
                "wall_time_seconds": round(wall_time, 2),
                "rps": round(total / max(wall_time, 0.1), 2),
                "avg_latency": round(sum(durations) / max(len(durations), 1), 4),
                "min_latency": round(durations[0], 4) if durations else 0,
                "max_latency": round(durations[-1], 4) if durations else 0,
                "p50": round(percentile(durations, 50), 4),
                "p95": round(percentile(durations, 95), 4),
                "p99": round(percentile(durations, 99), 4),
            },
            "endpoints": endpoints,
        }
        return report

    def save_json(self, report, path):
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"  📄 JSON report: {path}")

    def save_html(self, report, path):
        s = report["summary"]
        ep_rows = ""
        for ep in report["endpoints"]:
            fail_cls = "fail" if ep["failed"] > 0 else ""
            err_info = f'<br><small style="color:#ef4444">{"; ".join(ep["error_sample"])}</small>' if ep["error_sample"] else ""
            ep_rows += f"""<tr class="{fail_cls}">
                <td class="mono">{ep['endpoint']}</td><td>{ep['label']}</td>
                <td class="num">{ep['count']:,}</td>
                <td class="num ok">{ep['success']:,}</td>
                <td class="num {'err' if ep['failed'] else ''}">{ep['failed']:,}{err_info}</td>
                <td class="num {'slow-val' if ep['slow'] else ''}">{ep['slow']:,}</td>
                <td class="num">{ep['avg']:.4f}s</td>
                <td class="num">{ep['min']:.4f}s</td>
                <td class="num">{ep['max']:.4f}s</td>
                <td class="num">{ep['p50']:.4f}s</td>
                <td class="num">{ep['p95']:.4f}s</td>
                <td class="num">{ep['p99']:.4f}s</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>LoopSentry Load Test Report</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0b0e17;--sf:#131829;--sf2:#1a2035;--bd:#252d48;
  --text:#e2e8f0;--dim:#64748b;--accent:#6366f1;--accent2:#818cf8;
  --red:#ef4444;--orange:#f97316;--yellow:#eab308;--green:#22c55e;--cyan:#06b6d4;--pink:#ec4899;
  --font:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  --mono:'SF Mono','Fira Code',Consolas,monospace;
}}
body{{font-family:var(--font);background:var(--bg);color:var(--text);padding:0;line-height:1.6}}
.wrap{{width:100%;padding:32px}}
h1{{font-size:28px;font-weight:800;background:linear-gradient(135deg,var(--accent),var(--cyan));-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:4px}}
.sub{{color:var(--dim);font-size:13px;margin-bottom:32px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:32px}}
.card{{background:var(--sf);border:1px solid var(--bd);border-radius:12px;padding:18px;text-align:center}}
.card .v{{font-size:30px;font-weight:800;margin-bottom:2px}}
.card .l{{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--dim)}}
.card.green .v{{color:var(--green)}}.card.red .v{{color:var(--red)}}
.card.orange .v{{color:var(--orange)}}.card.cyan .v{{color:var(--cyan)}}
.card.yellow .v{{color:var(--yellow)}}.card.pink .v{{color:var(--pink)}}
.card.accent .v{{color:var(--accent2)}}
h2{{font-size:18px;font-weight:700;margin:32px 0 16px;color:var(--dim)}}
table{{width:100%;border-collapse:collapse;font-size:13px;border:1px solid var(--bd);border-radius:12px;overflow:hidden}}
th{{background:var(--sf);padding:12px 14px;text-align:left;font-weight:700;text-transform:uppercase;font-size:11px;letter-spacing:.5px;color:var(--dim);border-bottom:2px solid var(--bd)}}
td{{padding:10px 14px;border-bottom:1px solid var(--bd)}}
tr:hover{{background:var(--sf2)}}
.mono{{font-family:var(--mono);font-size:12px}}
.num{{font-family:var(--mono);text-align:right}}
.ok{{color:var(--green)}}.err{{color:var(--red);font-weight:700}}.slow-val{{color:var(--orange);font-weight:700}}
.fail td{{border-left:3px solid var(--red)}}
.config{{background:var(--sf);border:1px solid var(--bd);border-radius:12px;padding:20px;margin-bottom:32px;font-size:13px;display:flex;gap:32px;flex-wrap:wrap}}
.config dt{{color:var(--dim);font-weight:600}}.config dd{{color:var(--text);font-family:var(--mono)}}
.footer{{text-align:center;padding:32px 0;color:var(--dim);font-size:12px;border-top:1px solid var(--bd);margin-top:48px}}
</style>
</head>
<body>
<div class="wrap">
  <h1>⚡ LoopSentry Load Test Report</h1>
  <div class="sub">Generated {report['generated_at']} — Target: {report['target']}</div>

  <div class="config">
    <div><dt>Concurrency</dt><dd>{report['config']['concurrency']}</dd></div>
    <div><dt>Duration</dt><dd>{report['config']['duration_seconds']}s</dd></div>
    <div><dt>Slow Threshold</dt><dd>{report['config']['slow_threshold']}s</dd></div>
    <div><dt>Wall Time</dt><dd>{s['wall_time_seconds']}s</dd></div>
  </div>

  <div class="cards">
    <div class="card accent"><div class="v">{s['total_requests']:,}</div><div class="l">Total Requests</div></div>
    <div class="card green"><div class="v">{s['success']:,}</div><div class="l">Success</div></div>
    <div class="card red"><div class="v">{s['failed']:,}</div><div class="l">Failed</div></div>
    <div class="card orange"><div class="v">{s['slow']:,}</div><div class="l">Slow</div></div>
    <div class="card cyan"><div class="v">{s['rps']}</div><div class="l">Req/sec</div></div>
    <div class="card yellow"><div class="v">{s['avg_latency']:.4f}s</div><div class="l">Avg Latency</div></div>
    <div class="card pink"><div class="v">{s['p95']:.4f}s</div><div class="l">P95 Latency</div></div>
    <div class="card red"><div class="v">{s['p99']:.4f}s</div><div class="l">P99 Latency</div></div>
  </div>

  <h2>Per-Endpoint Breakdown</h2>
  <table>
    <thead><tr>
      <th>Endpoint</th><th>Label</th><th>Count</th><th>✅ OK</th><th>❌ Fail</th><th>🐢 Slow</th>
      <th>Avg</th><th>Min</th><th>Max</th><th>P50</th><th>P95</th><th>P99</th>
    </tr></thead>
    <tbody>{ep_rows}</tbody>
  </table>

  <div class="footer">Generated by <strong>LoopSentry Load Tester</strong></div>
</div>
</body>
</html>"""

        with open(path, "w") as f:
            f.write(html)
        print(f"  🌐 HTML report: {path}")

    def print_summary(self, report):
        s = report["summary"]
        print(f"  {'─'*50}")
        print(f"  Total:   {s['total_requests']:>8,}  |  RPS:     {s['rps']:>8}")
        print(f"  Success: {s['success']:>8,}  |  Failed:  {s['failed']:>8,}")
        print(f"  Slow:    {s['slow']:>8,}  |  Wall:    {s['wall_time_seconds']:>7}s")
        print(f"  Latency  avg={s['avg_latency']:.4f}s  p50={s['p50']:.4f}s  p95={s['p95']:.4f}s  p99={s['p99']:.4f}s")
        print(f"  {'─'*50}")
        print()
        for ep in report["endpoints"]:
            marker = "❌" if ep["failed"] > 0 else "🐢" if ep["slow"] > 0 else "✅"
            print(f"  {marker} {ep['endpoint']:32s} {ep['count']:>5,} reqs  avg={ep['avg']:.4f}s  p95={ep['p95']:.4f}s  fail={ep['failed']}")
        print()


def main():
    parser = argparse.ArgumentParser(description="LoopSentry Load Tester")
    parser.add_argument("-c", "--concurrency", type=int, default=100, help="Max concurrent requests (default: 100)")
    parser.add_argument("-d", "--duration", type=int, default=600, help="Test duration in seconds (default: 600 = 10min)")
    parser.add_argument("--slow-threshold", type=float, default=0.5, help="Slow request threshold in seconds (default: 0.5)")
    parser.add_argument("--base-url", default=BASE, help=f"Target base URL (default: {BASE})")
    parser.add_argument("-o", "--output", default="loadtest_report", help="Output file prefix (default: loadtest_report)")
    args = parser.parse_args()

    tester = LoadTester(args.base_url, args.concurrency, args.duration, args.slow_threshold)
    asyncio.run(tester.run())

    report = tester.build_report()

    # Save reports
    json_path = f"{args.output}.json"
    html_path = f"{args.output}.html"
    tester.save_json(report, json_path)
    tester.save_html(report, html_path)
    tester.print_summary(report)

    print(f"  Stop the server and analyze LoopSentry logs:")
    print(f"  loopsentry analyze -d example_logs/ --html\n")


if __name__ == "__main__":
    main()
