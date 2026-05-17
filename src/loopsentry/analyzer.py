from __future__ import annotations

import csv
import math
from datetime import datetime
from pathlib import Path
import re
from typing import Any, Sequence
from .report_html import generate_html
from .stack_frames import analyze_stack_for_user_code, classify_path, parse_stack_line
import orjson
from rich.console import Console
from rich import box
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

console = Console()

Block = dict[str, Any]


class Analyzer:
    def __init__(self, path: str | Path, project_roots: Sequence[str] | None = None) -> None:
        self.path: Path = Path(path)
        self.project_roots: tuple[str, ...] = tuple(project_roots or ())
        self.blocks: list[Block] = []
        self.stats: dict[str, float | int] = {
            "total_time": 0.0,
            "async_total_time": 0.0,
            "count": 0,
            "crashes": 0,
            "async_slow": 0,
            "max_cpu": 0.0,
            "max_cpu_avg": 0.0,
            "max_cpu_total": 0.0,
            "max_cpu_single_core": 0.0,
            "cpu_core_count": 0,
            "max_mem": 0.0,
            "avg_duration": 0.0,
        }
        self.page: int = 1
        self.page_size: int = 15
        self.sort_by: str = "time"
        self.view_mode: str = "list"
        self.filter_term: str = ""

    def _analyze_heuristics(self, block: Block) -> str:
        if block.get("type") == "async_bottleneck":
            return "🐢 Slow Async Task"
        stack_str = "".join(block.get("stack", [])).lower()
        if "time.sleep" in stack_str: return "Blocking Sleep"
        if "requests." in stack_str: return "Sync HTTP (requests)"
        if "subprocess.run" in stack_str: return "Sync Subprocess"
        if "lock" in stack_str or "acquire" in stack_str: return "🔒 Resource Lock"
        if "while" in stack_str and "sleep" not in stack_str: return "⚠ CPU Loop?"
        return "Logic Block"

    def run(self) -> None:
        files = [self.path] if self.path.is_file() else list(self.path.rglob("*.jsonl"))
        for f in files:
            try:
                with open(f, 'r', encoding="utf-8") as handle:
                    current_block: Block | None = None
                    for line in handle:
                        try:
                            entry: Block = orjson.loads(line)
                            if entry["type"] == "async_bottleneck":
                                entry["total_duration"] = entry["duration_current"]
                                entry["resolved"] = True
                                entry["hint"] = self._analyze_heuristics(entry)
                                entry["trigger"] = f"{entry.get('coro')} ({entry.get('task_name')})"
                                self.blocks.append(entry)
                                self.stats["async_slow"] += 1
                                if isinstance(entry["duration_current"], (int, float)):
                                    self.stats["async_total_time"] += entry["duration_current"]
                                self._update_sys_stats(entry)
                                continue
                            if entry["type"] == "block_started":
                                if current_block:
                                    current_block["total_duration"] = "TRANSITION"
                                    current_block["resolved"] = True
                                    current_block["hint"] = self._analyze_heuristics(current_block)
                                    self.blocks.append(current_block)
                                current_block = entry
                            elif entry["type"] == "block_resolved" and current_block:
                                current_block["total_duration"] = entry["duration_current"]
                                current_block["resolved"] = True
                                current_block["hint"] = self._analyze_heuristics(current_block)
                                self.blocks.append(current_block)
                                self._update_sys_stats(current_block)
                                if isinstance(entry["duration_current"], float):
                                    self.stats["total_time"] += entry["duration_current"]
                                self.stats["count"] += 1
                                current_block = None
                        except Exception:
                            continue
                    if current_block:
                        current_block["total_duration"] = "CRASH"
                        current_block["resolved"] = False
                        current_block["hint"] = "Crash/Kill"
                        self.blocks.append(current_block)
                        self.stats["crashes"] += 1
            except Exception as e:
                console.print(f"[red]Error reading {f}: {e}[/red]")

        if self.stats["count"] > 0:
            self.stats["avg_duration"] = self.stats["total_time"] / self.stats["count"]
        self._apply_sort()
        self._enrich_user_stack()

    def _enrich_user_stack(self) -> None:
        roots: list[str] = []
        for r in self.project_roots:
            try:
                roots.append(str(Path(r).expanduser().resolve()))
            except OSError:
                roots.append(str(Path(r).expanduser()))
        roots_t = tuple(roots)
        for b in self.blocks:
            info = analyze_stack_for_user_code(b.get("stack") or [], roots_t)
            b["user_frames"] = info["user_frames"]
            b["user_location"] = info["user_location"]
            b["blocking_location"] = info["blocking_location"]
            b["blocking_file"] = info["blocking_file"]
            if not b["user_location"]:
                loc, _, _ = self._parse_location(b.get("trigger", ""))
                b["user_location"] = loc if loc else "Unknown"

    def _update_sys_stats(self, block: Block) -> None:
        sys_data = block.get("sys", {})
        cpu = sys_data.get("cpu_percent", 0)
        per_core = sys_data.get("cpu_per_core", [])
        mem = sys_data.get("memory_mb", 0)
        if cpu > self.stats["max_cpu"]:
            self.stats["max_cpu"] = cpu
        if cpu > self.stats["max_cpu_avg"]:
            self.stats["max_cpu_avg"] = cpu
        if isinstance(per_core, list) and per_core:
            total_cpu = float(sum(per_core))
            single_core = float(max(per_core))
            if len(per_core) > self.stats["cpu_core_count"]:
                self.stats["cpu_core_count"] = len(per_core)
            if total_cpu > self.stats["max_cpu_total"]:
                self.stats["max_cpu_total"] = total_cpu
            if single_core > self.stats["max_cpu_single_core"]:
                self.stats["max_cpu_single_core"] = single_core
        if mem > self.stats["max_mem"]: self.stats["max_mem"] = mem

    def _apply_sort(self) -> None:
        if self.sort_by == "time":
            self.blocks.sort(key=lambda x: x["timestamp"], reverse=True)
        elif self.sort_by == "duration":
            self.blocks.sort(key=lambda x: x["total_duration"] if isinstance(x["total_duration"], float) else -1, reverse=True)
        elif self.sort_by == "cpu":
            self.blocks.sort(key=lambda x: x.get("sys", {}).get("cpu_percent", 0), reverse=True)
        elif self.sort_by == "memory":
            self.blocks.sort(key=lambda x: x.get("sys", {}).get("memory_mb", 0), reverse=True)
        elif self.sort_by == "type":
            self.blocks.sort(key=lambda x: x.get("type", ""))

    def _parse_location(self, trigger_str: str) -> tuple[str, str, str]:
        if not trigger_str: return "Unknown", "", ""
        match = re.search(r'File "(.*?)", line (\d+)', trigger_str)
        if match:
            fname = match.group(1)
            lineno = match.group(2)
            short_name = Path(fname).name
            return f"{short_name}:{lineno}", fname, lineno
        async_match = re.search(r'^(.*?) \(Task-', trigger_str)
        if async_match:
             return async_match.group(1), "", ""
        return trigger_str[:40], "", ""

    def interactive_tui(self) -> None:
        while True:
            console.clear()
            self._apply_sort()
            title = f"[bold cyan]LoopSentry[/] | View: [bold yellow]{self.view_mode.upper()}[/] | Sort: [bold yellow]{self.sort_by.upper()}[/]"
            if self.filter_term: title += f" | Filter: '{self.filter_term}'"
            console.rule(title)
            display_blocks = []
            for idx, b in enumerate(self.blocks):
                b['_id'] = idx + 1
                searchable = (
                    b.get('hint', '')
                    + "".join(b.get('stack', []))
                    + b.get('trigger', '')
                    + (b.get('user_location') or '')
                    + (b.get('blocking_location') or '')
                ).lower()
                if not self.filter_term or self.filter_term in searchable:
                    display_blocks.append(b)
            if self.view_mode == 'list':
                self._render_list_view(display_blocks)
            else:
                self._render_group_view(display_blocks)
            console.print(f"\n[dim]Pg {self.page}/{max(1, math.ceil(len(display_blocks)/self.page_size))}[/dim]")
            console.print("[dim]Cmds: [white]<ID>[/] detail | [white]n[/]ext [white]p[/]rev | [white]g[/]roup | [white]s[/]ort:(time|duration|cpu|memory|type) | [white]/<text>[/] search | [white]q[/]uit[/dim]")
            choice = Prompt.ask("Action").lower().strip()
            if choice in ('q', 'quit', 'exit'): break
            elif choice == 'n': self.page += 1
            elif choice == 'p': self.page = max(1, self.page - 1)
            elif choice == 'g': self.view_mode = 'group' if self.view_mode == 'list' else 'list'; self.page = 1
            elif choice.startswith('s:'):
                val = choice[2:].strip()
                if val in ('time', 'duration', 'cpu', 'memory', 'type'):
                    self.sort_by = val; self.page = 1
            elif choice == 's':
                cycle = ['time', 'duration', 'cpu', 'memory', 'type']
                idx = cycle.index(self.sort_by) if self.sort_by in cycle else -1
                self.sort_by = cycle[(idx + 1) % len(cycle)]; self.page = 1
            elif choice.startswith("/"): self.filter_term = choice[1:]; self.page = 1
            elif choice in ('reset', 'clear'): self.filter_term = ""; self.page = 1
            elif choice.isdigit():
                if self.view_mode == 'list':
                    selected_id = int(choice)
                    target = next((b for b in self.blocks if b.get('_id') == selected_id), None)
                    if target: self._show_detail(target)

    def _render_list_view(self, blocks: list[Block]) -> None:
        grid = Table.grid(expand=True)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_row(
            Panel(f"[bold red]{len(blocks)}/{self.stats['count']}[/]", title="Blocks"),
            Panel(f"[bold yellow]{self.stats['total_time']:.2f}s[/]", title="Time Lost"),
            Panel(f"[bold blue]{self.stats['async_slow']}[/]", title="Async Slow"),
            Panel(f"[bold magenta]{self.stats['crashes']}[/]", title="Crashes"),
        )
        console.print(grid)
        total_pages = math.ceil(len(blocks) / self.page_size)
        if self.page > total_pages: self.page = max(1, total_pages)
        start = (self.page - 1) * self.page_size
        page_data = blocks[start:start + self.page_size]
        table = Table(box=box.SIMPLE_HEAD, expand=True)
        table.add_column("ID", style="bold white", width=4, justify="right")
        table.add_column("Type", style="magenta", width=8)
        table.add_column("Time", style="cyan", width=10)
        table.add_column("Dur", style="red", width=10)
        table.add_column("CPU%", style="green", width=6)
        table.add_column("Mem", style="blue", width=8)
        table.add_column("Hint", style="yellow")
        table.add_column("Location", style="blue")
        for b in page_data:
            dur = b['total_duration']
            dur_fmt = f"{dur:.4f}s" if isinstance(dur, float) else str(dur)
            app_loc = b.get("user_location") or ""
            if not app_loc or app_loc == "Unknown":
                app_loc, _, _ = self._parse_location(b.get('trigger', ''))
            sys_d = b.get('sys', {})
            evt_type = "ASYNC" if b.get('type') == 'async_bottleneck' else "BLOCK"
            table.add_row(
                str(b['_id']), evt_type, b['timestamp'][11:19], dur_fmt,
                f"{sys_d.get('cpu_percent', 0):.0f}", f"{sys_d.get('memory_mb', 0):.0f}MB",
                b.get('hint', ''), app_loc
            )
        console.print(table)

    def _render_group_view(self, blocks: list[Block]) -> None:
        groups: dict[str, dict[str, float | int | str]] = {}
        for b in blocks:
            loc = b.get("user_location") or ""
            if not loc or loc == "Unknown":
                loc, _, _ = self._parse_location(b.get('trigger', ''))
            if loc not in groups: groups[loc] = {"count": 0, "total": 0.0, "max": 0.0, "hint": b.get('hint', '')}
            groups[loc]["count"] += 1
            if isinstance(b['total_duration'], float):
                groups[loc]["total"] += b['total_duration']
                groups[loc]["max"] = max(groups[loc]["max"], b['total_duration'])
        sorted_groups = sorted(groups.items(), key=lambda x: x[1]['total'], reverse=True)
        total_pages = math.ceil(len(sorted_groups) / self.page_size)
        if self.page > total_pages: self.page = max(1, total_pages)
        start = (self.page - 1) * self.page_size
        table = Table(title="Top Offenders", box=box.SIMPLE_HEAD, expand=True)
        table.add_column("Location", style="bold blue")
        table.add_column("Count", justify="right")
        table.add_column("Total", style="red", justify="right")
        table.add_column("Max", style="yellow", justify="right")
        table.add_column("Hint", style="dim")
        for loc, data in sorted_groups[start:start + self.page_size]:
            table.add_row(loc, str(data['count']), f"{data['total']:.2f}s", f"{data['max']:.2f}s", data['hint'])
        console.print(table)

    def _show_detail(self, block: Block) -> None:
        console.clear()
        dur = block['total_duration']
        dur_str = f"{dur:.4f}s" if isinstance(dur, float) else str(dur)
        console.rule(f"[bold red]Event Detail - {dur_str}")
        info = Table(show_header=False, box=None)
        info.add_column(style="bold cyan"); info.add_column()
        info.add_row("Timestamp:", block['timestamp'])
        info.add_row("PID:", str(block['pid']))
        info.add_row("Type:", block.get('type', 'unknown'))
        info.add_row("Hint:", f"[yellow]{block.get('hint')}[/yellow]")
        bl = block.get("blocking_location")
        ul = block.get("user_location")
        if bl:
            info.add_row("Blocking (innermost):", bl)
        if ul and ul != bl:
            info.add_row("Your code (nearest):", f"[bold cyan]{ul}[/bold cyan]")
        sys_d = block.get('sys', {})
        info.add_row("CPU:", f"{sys_d.get('cpu_percent', 0)}%")
        info.add_row("Memory:", f"{sys_d.get('memory_mb', 0):.1f} MB")
        info.add_row("Threads:", str(sys_d.get('thread_count', '?')))
        gc_counts = sys_d.get('gc_counts')
        if gc_counts:
            info.add_row("GC Counts:", f"Gen0={gc_counts[0]} Gen1={gc_counts[1]} Gen2={gc_counts[2]}")
        per_core = sys_d.get('cpu_per_core', [])
        if per_core:
            info.add_row("Total Cores:", str(len(per_core)))
            core_str = " ".join(f"[{'red' if c>80 else 'yellow' if c>40 else 'green'}]{i}:{c:.0f}%[/]" for i, c in enumerate(per_core))
            info.add_row("Per Core:", core_str)
        if 'task_name' in block:
             info.add_row("Task:", block['task_name'])
             info.add_row("Coroutine:", block.get('coro'))
        console.print(Panel(info, title="Metadata", border_style="blue"))
        # Exception info
        exc = block.get('exception')
        if exc:
            exc_text = Text()
            exc_text.append(f"{exc['type']}: {exc['message']}\n", style="bold red")
            if exc.get('traceback'):
                for line in exc['traceback']:
                    exc_text.append(line, style="red")
            console.print(Panel(exc_text, title="Exception", border_style="red"))
        # Locals
        if 'locals' in block and block['locals']:
            locals_text = Text()
            for frame_data in block['locals']:
                fname = frame_data.get('func', 'Unknown')
                line_info = f" ({frame_data['file']}:{frame_data['line']})" if 'file' in frame_data else ""
                locals_text.append(f"{fname}{line_info}\n", style="bold green")
                if 'vars' in frame_data:
                    for k, v in frame_data['vars'].items():
                        locals_text.append(f"  {k} = ", style="cyan")
                        locals_text.append(f"{v}\n", style="white")
                locals_text.append("\n")
            console.print(Panel(locals_text, title="Captured Variables", border_style="yellow"))
        uf = block.get("user_frames") or []
        if uf:
            user_txt = Text()
            for fr in uf:
                fn = fr.get("func") or "?"
                user_txt.append(f"  {fn}  {fr.get('short', '')}\n", style="bold cyan")
                user_txt.append(f"    {fr.get('file', '')}\n", style="dim")
            console.print(Panel(user_txt, title="Your code (nearest frames)", border_style="cyan"))
        # Stack Trace
        if 'stack' in block and block['stack']:
            stack_lines = block.get('stack', [])
            roots = tuple(
                str(Path(r).expanduser().resolve())
                for r in self.project_roots
            )
            rich_stack = Text()
            culprit_index = -1
            processed = []
            for i, frame in enumerate(stack_lines):
                parsed = parse_stack_line(frame)
                is_user = False
                is_lib = True
                if parsed:
                    kind = classify_path(parsed[0], roots)
                    is_user = kind == "user"
                    is_lib = kind in ("stdlib", "third_party", "instrumentation", "synthetic") or (
                        "asyncio/" in frame or "\\asyncio\\" in frame
                    )
                else:
                    is_lib = any(
                        x in frame for x in ["site-packages", "dist-packages", "lib/python", "asyncio/"]
                    )
                    is_user = not is_lib
                processed.append({"text": frame, "is_lib": is_lib, "is_user": is_user})
                if is_user:
                    culprit_index = i
            if culprit_index == -1 and processed:
                culprit_index = len(processed) - 1
            for i, p in enumerate(processed):
                txt = p['text'].strip("\n")
                if i == culprit_index:
                    rich_stack.append(">>> " + txt + "\n", style="bold red")
                elif p['is_lib']:
                    rich_stack.append(txt + "\n", style="dim white")
                else:
                    rich_stack.append(txt + "\n", style="bold cyan")
            console.print(Panel(rich_stack, title="Full stack trace", border_style="red"))
        Prompt.ask("\n[dim]Press [bold]Enter[/] to return...[/dim]")

    def render_csv(self, output_path: str | None = None) -> str:
        if not output_path:
            output_path = f"loopsentry_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "ID", "Type", "Timestamp", "Duration(s)", "Hint",
                "UserLocation", "BlockingLocation",
                "CPU%", "Memory(MB)", "Threads", "GC_Gen0", "GC_Gen1", "GC_Gen2",
                "Task", "Coroutine", "Resolved", "Trigger",
            ])
            for i, b in enumerate(self.blocks):
                dur = b['total_duration']
                dur_val = f"{dur:.6f}" if isinstance(dur, float) else str(dur)
                user_loc = b.get("user_location") or ""
                block_loc = b.get("blocking_location") or ""
                if not user_loc or user_loc == "Unknown":
                    user_loc, _, _ = self._parse_location(b.get('trigger', ''))
                if not block_loc:
                    _, fn, ln = self._parse_location(b.get('trigger', ''))
                    block_loc = f"{Path(fn).name}:{ln}" if fn and ln else user_loc
                sys_d = b.get('sys', {})
                gc_c = sys_d.get('gc_counts', [0, 0, 0])
                evt_type = "async_bottleneck" if b.get('type') == 'async_bottleneck' else "block"
                writer.writerow([
                    i + 1, evt_type, b['timestamp'], dur_val, b.get('hint', ''),
                    user_loc, block_loc,
                    sys_d.get('cpu_percent', 0), round(sys_d.get('memory_mb', 0), 2),
                    sys_d.get('thread_count', 0),
                    gc_c[0] if len(gc_c) > 0 else 0,
                    gc_c[1] if len(gc_c) > 1 else 0,
                    gc_c[2] if len(gc_c) > 2 else 0,
                    b.get('task_name', ''), b.get('coro', ''),
                    b.get('resolved', ''), b.get('trigger', '')[:100]
                ])
        console.print(f"[bold green]✨ CSV report saved: {output_path}[/bold green]")
        return output_path

    def render_html(self, output_path: str | None = None) -> str:
        if not output_path:
            output_path = f"loopsentry_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

        html = generate_html(self.blocks, self.stats)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        console.print(f"[bold green]✨ HTML report saved: {output_path}[/bold green]")
        return output_path

    def _get_culprit_frame_text(self, block: Block) -> str:
        stack = block.get("stack") or []
        if not stack:
            return ""
        roots_list: list[str] = []
        for r in self.project_roots:
            try:
                roots_list.append(str(Path(r).expanduser().resolve()))
            except OSError:
                roots_list.append(str(Path(r).expanduser()))
        roots = tuple(roots_list)
        culprit_idx = -1
        for i, line in enumerate(stack):
            parsed = parse_stack_line(line)
            if parsed:
                file, _, _ = parsed
                kind = classify_path(file, roots)
                if kind == "user":
                    culprit_idx = i
        if culprit_idx == -1 and stack:
            for i, line in enumerate(stack):
                parsed = parse_stack_line(line)
                if parsed:
                    file, _, _ = parsed
                    kind = classify_path(file, roots)
                    if kind not in ("stdlib", "third_party", "instrumentation", "synthetic"):
                        culprit_idx = i
        if culprit_idx == -1 and stack:
            culprit_idx = len(stack) - 1
        
        if culprit_idx != -1:
            return stack[culprit_idx].strip()
        return ""

    def _get_culprit_key(self, b: Block) -> str:
        k = self._get_culprit_frame_text(b)
        if k:
            return k.strip()
        return str(b.get("trigger") or b.get("coro") or b.get("user_location") or "Unknown").strip()

    def print_summary(self) -> None:
        groups: dict[str, dict[str, Any]] = {}
        for b in self.blocks:
            key = self._get_culprit_key(b)
            if key not in groups:
                groups[key] = {
                    "count": 0,
                    "sample": b,
                    "total_duration": 0.0,
                    "max_duration": 0.0,
                }
            groups[key]["count"] += 1
            dur = b.get("total_duration")
            if isinstance(dur, (int, float)):
                groups[key]["total_duration"] += dur
                groups[key]["max_duration"] = max(groups[key]["max_duration"], dur)
        
        sorted_groups = sorted(groups.items(), key=lambda x: x[1]["count"], reverse=True)

        console.print(Panel(
            f"[bold cyan]LoopSentry Culprit Digest[/]\n"
            f"[dim]Total Events: {len(self.blocks)} | Unique Culprits: {len(sorted_groups)}[/dim]",
            border_style="cyan"
        ))

        table = Table(box=box.HEAVY_EDGE, expand=True)
        table.add_column("Rank", style="dim", justify="right", width=5)
        table.add_column("Type", style="bold magenta", width=8)
        table.add_column("Count", justify="right", style="cyan", width=6)
        table.add_column("Location", style="bold blue", overflow="fold")
        table.add_column("Blocking", style="red", overflow="fold")
        table.add_column("Hint", style="yellow")
        table.add_column("Culprit Frame Preview", style="green", overflow="fold")

        for idx, (key, data) in enumerate(sorted_groups):
            b = data["sample"]
            evt_type = "ASYNC" if b.get("type") == "async_bottleneck" else "BLOCK"
            if b.get("total_duration") == "CRASH":
                evt_type = "CRASH"
            
            frame_line = key.split("\n")[-1].strip() if "\n" in key else key.strip()

            table.add_row(
                str(idx + 1),
                evt_type,
                str(data["count"]),
                b.get("user_location") or "Unknown",
                b.get("blocking_location") or "Unknown",
                b.get("hint") or "—",
                frame_line
            )
        
        console.print(table)

    def render_summary_csv(self, output_path: str | None = None) -> str:
        if not output_path:
            output_path = f"loopsentry_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        groups: dict[str, dict[str, Any]] = {}
        for b in self.blocks:
            key = self._get_culprit_key(b)
            if key not in groups:
                groups[key] = {
                    "count": 0,
                    "sample": b,
                    "total_duration": 0.0,
                    "max_duration": 0.0,
                }
            groups[key]["count"] += 1
            dur = b.get("total_duration")
            if isinstance(dur, (int, float)):
                groups[key]["total_duration"] += dur
                groups[key]["max_duration"] = max(groups[key]["max_duration"], dur)
        
        sorted_groups = sorted(groups.items(), key=lambda x: x[1]["count"], reverse=True)

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Rank", "Type", "Count", "Location", "BlockingLocation", "Hint", "CulpritFrame"
            ])
            for idx, (key, data) in enumerate(sorted_groups):
                b = data["sample"]
                evt_type = "async_bottleneck" if b.get("type") == "async_bottleneck" else "block"
                if b.get("total_duration") == "CRASH":
                    evt_type = "crash"
                writer.writerow([
                    idx + 1,
                    evt_type,
                    data["count"],
                    b.get("user_location") or "Unknown",
                    b.get("blocking_location") or "Unknown",
                    b.get("hint") or "—",
                    key.strip()
                ])
        
        console.print(f"[bold green]✨ Culprit summary CSV saved: {output_path}[/bold green]")
        return output_path