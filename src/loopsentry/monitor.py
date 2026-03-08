import asyncio
import time
import threading
import sys
import traceback
import json
import gc
import os
import signal
from datetime import datetime
from pathlib import Path
from rich.console import Console
import psutil

console = Console()

class LoopSentry:
    def __init__(
        self, 
        base_dir="sentry_logs", 
        threshold=0.1, 
        async_threshold=None,
        capture_args=False,
        detect_async_bottlenecks=False
    ):
        self.threshold = threshold
        self.async_threshold = async_threshold if async_threshold is not None else threshold
        self.capture_args = capture_args
        self.detect_async_bottlenecks = detect_async_bottlenecks
        
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
        
        self.process = psutil.Process(self.pid)

        self._original_factory = None
        self._factory_installed = False
        self._loop = None

    def start(self):
        if self.running: return
        self.running = True
        self._last_tick = time.time()
        
        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except ValueError:
            pass

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        self._loop = loop
        loop.call_soon(self._ticker)
        
        if self.detect_async_bottlenecks:
            self._original_factory = loop.get_task_factory()
            loop.set_task_factory(self._sentry_task_factory)
            self._factory_installed = True
            console.print("[cyan]ℹ Async Bottleneck Detector Enabled[/cyan]")

        self.thread = threading.Thread(target=self._watchdog, daemon=True, name="LoopSentry-Watchdog")
        self.thread.start()
        
        console.print(f"[green]✔ LoopSentry Active.[/green] [dim]PID: {self.pid} | Threshold: {self.threshold}s | Async Threshold: {self.async_threshold}s | Capture Args: {self.capture_args}[/dim]")

    def stop(self):
        """Stop monitoring and clean up resources."""
        if not self.running:
            return
        self.running = False
        self._stop_event.set()

        # Restore original task factory
        if self._loop and self._factory_installed:
            try:
                self._loop.set_task_factory(self._original_factory)
            except Exception:
                pass
            self._factory_installed = False

        # Flush and close log file
        if self._file_handle and not self._file_handle.closed:
            try:
                self._file_handle.flush()
                self._file_handle.close()
            except Exception:
                pass

        console.print("[yellow]⏹ LoopSentry Stopped.[/yellow]")

    def _signal_handler(self, signum, frame):
        self.stop()
        # Restore default handler and re-raise so the process actually exits
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    def _safe_repr(self, obj, max_len=150):
        try:
            s = repr(obj)
            return s[:max_len] + "..." if len(s) > max_len else s
        except:
            return "<unprintable>"

    def _capture_creation_traceback(self):
        """Capture a cleaned-up traceback at task creation time."""
        try:
            raw_stack = traceback.format_stack()
            # Filter out LoopSentry internals and asyncio internals
            cleaned = []
            for frame in raw_stack:
                if "loopsentry/monitor.py" in frame:
                    continue
                if "asyncio/" in frame and "task_factory" not in frame:
                    continue
                cleaned.append(frame)
            return cleaned if cleaned else raw_stack[-3:]
        except:
            return []

    def _sentry_task_factory(self, loop, coro, context=None):
        if self._original_factory:
            task = self._original_factory(loop, coro, context)
        else:
            task = asyncio.Task(coro, loop=loop, context=context)

        task._sentry_start = time.time()
        
        # Capture traceback at creation time (before frame is destroyed)
        task._sentry_creation_stack = self._capture_creation_traceback()
        
        # Capture Args at Start (Before frame is destroyed)
        task._sentry_locals = {}
        if self.capture_args:
            try:
                if hasattr(coro, 'cr_frame') and coro.cr_frame:
                    raw_locals = coro.cr_frame.f_locals
                    task._sentry_locals = {k: self._safe_repr(v) for k, v in raw_locals.items() if not k.startswith('_')}
            except:
                pass

        def _on_done(t):
            duration = time.time() - t._sentry_start
            if duration > self.async_threshold:
                coro_obj = t.get_coro()
                coro_name = getattr(coro_obj, '__name__', str(coro_obj))
                
                # Capture exception info if task failed
                exception_info = None
                try:
                    exc = t.exception()
                    if exc:
                        exception_info = {
                            "type": type(exc).__name__,
                            "message": str(exc),
                            "traceback": traceback.format_exception(type(exc), exc, exc.__traceback__)
                        }
                except (asyncio.CancelledError, asyncio.InvalidStateError):
                    pass

                self._write_event("async_bottleneck", {
                    "task_name": t.get_name(),
                    "coro": coro_name,
                    "info": "Slow Async Task",
                    "stack": getattr(t, '_sentry_creation_stack', []),
                    "locals": [{"func": coro_name, "vars": t._sentry_locals}] if t._sentry_locals else [],
                    "exception": exception_info,
                    "sys": self._get_sys_metrics(),
                }, duration=duration)

        task.add_done_callback(_on_done)
        return task

    def _ticker(self):
        self._last_tick = time.time()
        if self.running and self._loop:
            self._loop.call_later(self.threshold / 2, self._ticker)

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
                    console.print(f"[bold red]🚨 Block Detected![/bold red] ({delta:.2f}s)")
                
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

    def _get_sys_metrics(self):
        """Get system metrics (CPU, memory, GC) as a dict."""
        metrics = {
            "cpu_percent": 0.0,
            "cpu_per_core": [],
            "memory_mb": 0.0,
            "thread_count": threading.active_count(),
            "gc_counts": list(gc.get_count()),
        }
        try:
            per_core = psutil.cpu_percent(percpu=True)
            metrics["cpu_per_core"] = per_core
            metrics["cpu_percent"] = round(sum(per_core) / len(per_core), 1) if per_core else 0.0
            metrics["memory_mb"] = round(self.process.memory_info().rss / 1024 / 1024, 2)
        except:
            pass
        return metrics

    def _capture_state(self):
        data = {
            "timestamp": datetime.now().isoformat(),
            "stack": [],
            "locals": [],
            "trigger": "Unknown",
            "sys": self._get_sys_metrics(),
        }
        try:
            main_id = threading.main_thread().ident
            frames = sys._current_frames()
            frame = frames.get(main_id)
            if frame:
                stack = traceback.format_stack(frame)
                data["stack"] = stack
                data["trigger"] = stack[-1].strip() if stack else "Unknown"

                if self.capture_args:
                    curr = frame
                    depth = 0
                    while curr and depth < 5:
                        func_name = curr.f_code.co_name
                        local_vars = {}
                        for k, v in curr.f_locals.items():
                            if not k.startswith("__"):
                                local_vars[k] = self._safe_repr(v)
                        
                        if local_vars:
                            data["locals"].append({
                                "func": func_name,
                                "file": Path(curr.f_code.co_filename).name,
                                "line": curr.f_lineno,
                                "vars": local_vars
                            })
                        curr = curr.f_back
                        depth += 1
        except Exception:
            data["stack"] = ["Error capturing stack"]

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