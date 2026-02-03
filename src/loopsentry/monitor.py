import asyncio
import time
import threading
import sys
import traceback
import json
import os
import signal
from datetime import datetime
from pathlib import Path
from rich.console import Console

console = Console()

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

class LoopSentry:
    def __init__(self, base_dir="sentry_logs", threshold=0.1):
        self.threshold = threshold
        self.running = False
        self._last_tick = 0
        self._is_blocking = False
        self._stop_event = threading.Event()
        
        self._segment_start_time = 0
        self._last_stack_signature = None
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        self.log_dir = Path(base_dir) / date_str
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.pid = os.getpid()
        self.log_file = self.log_dir / f"sentry_{self.pid}.jsonl"
        self._file_handle = open(self.log_file, "a", encoding="utf-8")
        
        self.process = psutil.Process(self.pid) if PSUTIL_AVAILABLE else None

    def start(self):
        if self.running: return
        self.running = True
        self._last_tick = time.time()
        
        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except ValueError:
            pass

        asyncio.get_event_loop().call_soon(self._ticker)
        
        self.thread = threading.Thread(target=self._watchdog, daemon=True, name="LoopSentry-Watchdog")
        self.thread.start()
        
        console.print(f"[green]✔ LoopSentry Pro Active.[/green] [dim]PID: {self.pid} | Log: {self.log_file}[/dim]")

    def _signal_handler(self, signum, frame):
        self.running = False
        self._stop_event.set()
        if self._file_handle:
            self._file_handle.flush()
            self._file_handle.close()
        sys.exit(0)

    def _ticker(self):
        self._last_tick = time.time()
        if self.running:
            asyncio.get_event_loop().call_later(self.threshold / 2, self._ticker)

    def _watchdog(self):
        while self.running and not self._stop_event.is_set():
            time.sleep(self.threshold)
            now = time.time()
            delta = now - self._last_tick
            
            if delta > self.threshold:
                snapshot = self._capture_state()
                current_signature = "".join(snapshot['stack'])
                
                if not self._is_blocking:
                    self._is_blocking = True
                    self._segment_start_time = now - self.threshold
                    self._last_stack_signature = current_signature
                    self._write_event("block_started", snapshot, duration=delta)
                    console.print(f"[bold red] Block Detected![/bold red] ({delta:.2f}s)")
                
                elif current_signature != self._last_stack_signature:
                    segment_duration = now - self._segment_start_time
                    self._write_event("block_resolved", {}, duration=segment_duration)
                    
                    self._segment_start_time = now
                    self._last_stack_signature = current_signature
                    self._write_event("block_started", snapshot, duration=delta)
                    console.print(f"[bold red]>>> Block Shift Detected![/bold red]")

            else:
                if self._is_blocking:
                    self._is_blocking = False
                    segment_duration = now - self._segment_start_time
                    self._write_event("block_resolved", {}, duration=segment_duration)
                    console.print(f"[green]✔ Recovered.[/green]")
                    self._last_stack_signature = None

    def _capture_state(self):
        data = {
            "timestamp": datetime.now().isoformat(),
            "stack": [],
            "trigger": "Unknown",
            "sys": { "cpu_percent": 0.0, "memory_mb": 0.0, "thread_count": threading.active_count() }
        }
        try:
            main_id = threading.main_thread().ident
            frames = sys._current_frames()
            frame = frames.get(main_id)
            if frame:
                stack = traceback.format_stack(frame)
                data["stack"] = stack
                data["trigger"] = stack[-1].strip() if stack else "Unknown"
        except Exception:
            data["stack"] = ["Error capturing stack"]

        if self.process:
            try:
                with self.process.oneshot():
                    data["sys"]["cpu_percent"] = self.process.cpu_percent()
                    data["sys"]["memory_mb"] = self.process.memory_info().rss / 1024 / 1024
            except Exception:
                pass     
        return data

    def _write_event(self, event_type, data, duration=0.0):
        entry = {
            "type": event_type,
            "pid": self.pid,
            "timestamp": datetime.now().isoformat(),
            "duration_current": duration,
            **data
        }
        try:
            self._file_handle.write(json.dumps(entry) + "\n")
            self._file_handle.flush()
        except Exception:
            pass