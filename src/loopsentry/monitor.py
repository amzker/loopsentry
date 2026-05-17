from __future__ import annotations

import asyncio
import gc
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import FrameType
from typing import Any, Callable

from asyncio import AbstractEventLoop, Task

import orjson
import psutil
from rich.console import Console

console = Console()

EventData = dict[str, Any]


class LoopSentry:
    def __init__(
        self,
        base_dir: str = "sentry_logs",
        threshold: float = 0.1,
        async_threshold: float | None = None,
        capture_args: bool = False,
        detect_async_bottlenecks: bool = False,
    ) -> None:
        self.threshold: float = threshold
        self.async_threshold: float = async_threshold if async_threshold is not None else threshold
        self.capture_args: bool = capture_args
        self.detect_async_bottlenecks: bool = detect_async_bottlenecks

        self.running: bool = False
        self._last_tick: float = 0.0
        self._is_blocking: bool = False
        self._stop_event: threading.Event = threading.Event()
        self._file_lock: threading.RLock = threading.RLock()

        self._segment_start_time: float = 0.0
        self._last_stack_signature: str | None = None

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.log_dir: Path = Path(base_dir) / date_str
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.pid: int = os.getpid()
        self.log_file: Path = self.log_dir / f"sentry_{self.pid}.jsonl"
        self._file_handle = open(self.log_file, "ab")

        self.process: psutil.Process = psutil.Process(self.pid)

        self._original_factory: Callable[..., Task[Any]] | None = None
        self._factory_installed: bool = False
        self._loop: AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.running:
            return
        if self._stop_event.is_set():
            self._stop_event = threading.Event()
        self._is_blocking = False
        self._segment_start_time = 0
        self._last_stack_signature = None
        self._ensure_log_file_open()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError(
                "LoopSentry.start() requires an active asyncio event loop. "
                "Start it from FastAPI lifespan, app startup, or another running async context."
            ) from None

        self._loop = loop
        self.running = True
        self._last_tick = time.time()
        loop.call_soon(self._ticker)
        
        if self.detect_async_bottlenecks:
            self._original_factory = loop.get_task_factory()
            loop.set_task_factory(self._sentry_task_factory)
            self._factory_installed = True
            console.print("[cyan]ℹ Async Bottleneck Detector Enabled[/cyan]")

        self.thread = threading.Thread(target=self._watchdog, daemon=True, name="LoopSentry-Watchdog")
        self.thread.start()
        
        console.print(f"[green]✔ LoopSentry Active.[/green] [dim]PID: {self.pid} | Threshold: {self.threshold}s | Async Threshold: {self.async_threshold}s | Capture Args: {self.capture_args}[/dim]")

    def stop(self) -> None:
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

        thread = getattr(self, "thread", None)
        if thread and thread.is_alive():
            thread.join(timeout=self.threshold * 2)

        # Flush and close log file
        with self._file_lock:
            if self._file_handle and not self._file_handle.closed:
                try:
                    self._file_handle.flush()
                    self._file_handle.close()
                except Exception:
                    pass

        console.print("[yellow]⏹ LoopSentry Stopped.[/yellow]")

    def _safe_repr(self, obj: Any, max_len: int = 150) -> str:
        try:
            s = repr(obj)
            return s[:max_len] + "..." if len(s) > max_len else s
        except:
            return "<unprintable>"

    def _capture_creation_traceback(self) -> list[str]:
        try:
            f = sys._getframe()
            frames = []
            while f:
                co = f.f_code
                filename = co.co_filename
                if "loopsentry/monitor.py" not in filename and ("asyncio/" not in filename or "task_factory" in filename):
                    frames.append(f'  File "{filename}", line {f.f_lineno}, in {co.co_name}\n')
                f = f.f_back
            frames = frames[:10]
            frames.reverse()
            return frames
        except Exception:
            return []

    def _sentry_task_factory(
        self,
        loop: AbstractEventLoop,
        coro: Any,
        context: Any = None,
    ) -> Task[Any]:
        if self._original_factory:
            task = self._original_factory(loop, coro, context)
        else:
            task = Task(coro, loop=loop, context=context)

        setattr(task, "_sentry_start", time.time())
        setattr(task, "_sentry_creation_stack", self._capture_creation_traceback())
        setattr(task, "_sentry_locals", {})
        if self.capture_args:
            try:
                if hasattr(coro, "cr_frame") and coro.cr_frame:
                    raw_locals = coro.cr_frame.f_locals
                    setattr(
                        task,
                        "_sentry_locals",
                        {k: self._safe_repr(v) for k, v in raw_locals.items() if not k.startswith("_")},
                    )
            except:
                pass

        def _on_done(t: Task[Any]) -> None:
            duration = time.time() - getattr(t, "_sentry_start")
            if duration > self.async_threshold:
                coro_obj = t.get_coro()
                coro_name = getattr(coro_obj, "__name__", str(coro_obj))

                exception_info: EventData | None = None
                try:
                    exc = t.exception()
                    if exc:
                        exception_info = {
                            "type": type(exc).__name__,
                            "message": str(exc),
                            "traceback": traceback.format_exception(type(exc), exc, exc.__traceback__),
                        }
                except (asyncio.CancelledError, asyncio.InvalidStateError):
                    pass

                self._write_event(
                    "async_bottleneck",
                    {
                        "task_name": t.get_name(),
                        "coro": coro_name,
                        "info": "Slow Async Task",
                        "stack": getattr(t, "_sentry_creation_stack", []),
                        "locals": [{"func": coro_name, "vars": getattr(t, "_sentry_locals")}] if getattr(t, "_sentry_locals") else [],
                        "exception": exception_info,
                        # sys metrics added by watchdog thread
                    },
                    duration=duration,
                )

        task.add_done_callback(_on_done)
        return task

    def _ticker(self) -> None:
        self._last_tick = time.time()
        if self.running and self._loop:
            self._loop.call_later(self.threshold / 2, self._ticker)

    def _watchdog(self) -> None:
        while self.running and not self._stop_event.is_set():
            self._stop_event.wait(timeout=self.threshold)

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

    def _get_sys_metrics(self) -> EventData:
        metrics: EventData = {
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

    def _capture_state(self) -> EventData:
        data: EventData = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stack": [],
            "locals": [],
            "trigger": "Unknown",
            "sys": self._get_sys_metrics(),
        }
        try:
            main_id = threading.main_thread().ident
            frames: dict[int, FrameType] = sys._current_frames()
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
                                "vars": local_vars,
                            })
                        curr = curr.f_back
                        depth += 1
        except Exception:
            data["stack"] = ["Error capturing stack"]

        return data

    def _ensure_log_file_open(self) -> bool:
        if self._file_handle and not self._file_handle.closed:
            return True
        with self._file_lock:
            if self._file_handle and not self._file_handle.closed:
                return True
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self._file_handle = open(self.log_file, "ab")
            return True

    def _log_internal_warning(self, message: str) -> None:
        console.print(f"[yellow]LoopSentry warning:[/yellow] {message}")
        entry: EventData = {
            "type": "loopsentry_warning",
            "pid": self.pid,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_current": 0.0,
            "warning": message,
        }
        self._emit_entry(entry)

    def _emit_entry(self, entry: EventData) -> None:
        self._file_handle.write(orjson.dumps(entry) + b"\n")
        self._file_handle.flush()

    def _write_event(self, event_type: str, data: EventData, duration: float = 0.0) -> None:
        entry: EventData = {
            "type": event_type,
            "pid": data.get("pid", self.pid),
            "timestamp": data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "duration_current": data.get("duration_current", duration),
            **{k: v for k, v in data.items() if k not in {"pid", "timestamp", "duration_current"}},
        }
        if "sys" not in entry:
            entry["sys"] = self._get_sys_metrics()
        try:
            with self._file_lock:
                if self._file_handle.closed:
                    self._ensure_log_file_open()
                    self._log_internal_warning("log file was closed during event write and has been reopened")
                self._emit_entry(entry)
        except Exception as exc:
            reopened = False
            try:
                with self._file_lock:
                    self._ensure_log_file_open()
                reopened = True
            except Exception:
                pass
            if reopened:
                with self._file_lock:
                    self._log_internal_warning(f"log write failed with {type(exc).__name__}; file reopened and write skipped")
            else:
                console.print(f"[yellow]LoopSentry warning:[/yellow] log write failed with {type(exc).__name__} and reopen also failed")