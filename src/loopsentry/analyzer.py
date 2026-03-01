import json
import csv
import time
import re
import math
import os
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.prompt import Prompt

console = Console()

class Analyzer:
    def __init__(self, path):
        self.path = Path(path)
        self.blocks = []
        self.stats = {"total_time": 0.0, "count": 0, "crashes": 0, "async_slow": 0,
                      "max_cpu": 0.0, "max_mem": 0.0, "avg_duration": 0.0}
        self.page = 1
        self.page_size = 15
        self.sort_by = 'time'
        self.view_mode = 'list'
        self.filter_term = ""

    def _analyze_heuristics(self, block):
        if block.get('type') == 'async_bottleneck':
            return "🐢 Slow Async Task"
        stack_str = "".join(block.get('stack', [])).lower()
        if "time.sleep" in stack_str: return "Blocking Sleep"
        if "requests." in stack_str: return "Sync HTTP (requests)"
        if "subprocess.run" in stack_str: return "Sync Subprocess"
        if "lock" in stack_str or "acquire" in stack_str: return "🔒 Resource Lock"
        if "while" in stack_str and "sleep" not in stack_str: return "⚠ CPU Loop?"
        return "Logic Block"

    def run(self):
        files = [self.path] if self.path.is_file() else list(self.path.rglob("*.jsonl"))
        for f in files:
            try:
                with open(f, 'r', encoding="utf-8") as handle:
                    current_block = None
                    for line in handle:
                        try:
                            entry = json.loads(line)
                            if entry['type'] == 'async_bottleneck':
                                entry['total_duration'] = entry['duration_current']
                                entry['resolved'] = True
                                entry['hint'] = self._analyze_heuristics(entry)
                                entry['trigger'] = f"{entry.get('coro')} ({entry.get('task_name')})"
                                self.blocks.append(entry)
                                self.stats['async_slow'] += 1
                                self._update_sys_stats(entry)
                                continue
                            if entry['type'] == 'block_started':
                                if current_block:
                                    current_block['total_duration'] = "TRANSITION"
                                    current_block['resolved'] = True
                                    self.blocks.append(current_block)
                                current_block = entry
                            elif entry['type'] == 'block_resolved' and current_block:
                                current_block['total_duration'] = entry['duration_current']
                                current_block['resolved'] = True
                                current_block['hint'] = self._analyze_heuristics(current_block)
                                self.blocks.append(current_block)
                                self._update_sys_stats(current_block)
                                if isinstance(entry['duration_current'], float):
                                    self.stats['total_time'] += entry['duration_current']
                                self.stats['count'] += 1
                                current_block = None
                        except Exception:
                            continue
                    if current_block:
                        current_block['total_duration'] = "CRASH"
                        current_block['resolved'] = False
                        current_block['hint'] = "Crash/Kill"
                        self.blocks.append(current_block)
                        self.stats['crashes'] += 1
            except Exception as e:
                console.print(f"[red]Error reading {f}: {e}[/red]")

        total_events = self.stats['count'] + self.stats['async_slow']
        if total_events > 0:
            self.stats['avg_duration'] = self.stats['total_time'] / total_events
        self._apply_sort()

    def _update_sys_stats(self, block):
        sys_data = block.get('sys', {})
        cpu = sys_data.get('cpu_percent', 0)
        mem = sys_data.get('memory_mb', 0)
        if cpu > self.stats['max_cpu']: self.stats['max_cpu'] = cpu
        if mem > self.stats['max_mem']: self.stats['max_mem'] = mem

    def _apply_sort(self):
        if self.sort_by == 'time':
            self.blocks.sort(key=lambda x: x['timestamp'], reverse=True)
        elif self.sort_by == 'duration':
            self.blocks.sort(key=lambda x: x['total_duration'] if isinstance(x['total_duration'], float) else -1, reverse=True)
        elif self.sort_by == 'cpu':
            self.blocks.sort(key=lambda x: x.get('sys', {}).get('cpu_percent', 0), reverse=True)
        elif self.sort_by == 'memory':
            self.blocks.sort(key=lambda x: x.get('sys', {}).get('memory_mb', 0), reverse=True)
        elif self.sort_by == 'type':
            self.blocks.sort(key=lambda x: x.get('type', ''))

    def _parse_location(self, trigger_str):
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

    # ── Interactive TUI ──────────────────────────────────────────────
    def interactive_tui(self):
        while True:
            console.clear()
            self._apply_sort()
            title = f"[bold cyan]LoopSentry[/] | View: [bold yellow]{self.view_mode.upper()}[/] | Sort: [bold yellow]{self.sort_by.upper()}[/]"
            if self.filter_term: title += f" | Filter: '{self.filter_term}'"
            console.rule(title)
            display_blocks = []
            for idx, b in enumerate(self.blocks):
                b['_id'] = idx + 1
                searchable = (b.get('hint', '') + "".join(b.get('stack', [])) + b.get('trigger', '')).lower()
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

    def _render_list_view(self, blocks):
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
            short_loc, _, _ = self._parse_location(b.get('trigger', ''))
            sys_d = b.get('sys', {})
            evt_type = "ASYNC" if b.get('type') == 'async_bottleneck' else "BLOCK"
            table.add_row(
                str(b['_id']), evt_type, b['timestamp'][11:19], dur_fmt,
                f"{sys_d.get('cpu_percent', 0):.0f}", f"{sys_d.get('memory_mb', 0):.0f}MB",
                b.get('hint', ''), short_loc
            )
        console.print(table)

    def _render_group_view(self, blocks):
        groups = {}
        for b in blocks:
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

    def _show_detail(self, block):
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
        sys_d = block.get('sys', {})
        info.add_row("CPU:", f"{sys_d.get('cpu_percent', 0)}%")
        info.add_row("Memory:", f"{sys_d.get('memory_mb', 0):.1f} MB")
        info.add_row("Threads:", str(sys_d.get('thread_count', '?')))
        gc_counts = sys_d.get('gc_counts')
        if gc_counts:
            info.add_row("GC Counts:", f"Gen0={gc_counts[0]} Gen1={gc_counts[1]} Gen2={gc_counts[2]}")
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
        # Stack Trace
        if 'stack' in block and block['stack']:
            stack_lines = block.get('stack', [])
            rich_stack = Text()
            culprit_index = -1
            processed = []
            for i, frame in enumerate(stack_lines):
                is_lib = any(x in frame for x in ["site-packages", "dist-packages", "lib/python", "asyncio/"])
                processed.append({"text": frame, "is_lib": is_lib})
                if not is_lib: culprit_index = i
            if culprit_index == -1 and processed: culprit_index = len(processed) - 1
            for i, p in enumerate(processed):
                txt = p['text'].strip("\n")
                if i == culprit_index:
                    rich_stack.append(">>> " + txt + "\n", style="bold red")
                elif p['is_lib']:
                    rich_stack.append(txt + "\n", style="dim white")
                else:
                    rich_stack.append(txt + "\n", style="bold cyan")
            console.print(Panel(rich_stack, title="Smart Stack Trace", border_style="red"))
        Prompt.ask("\n[dim]Press [bold]Enter[/] to return...[/dim]")

    # ── CSV Export ────────────────────────────────────────────────────
    def render_csv(self, output_path=None):
        if not output_path:
            output_path = f"loopsentry_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "Type", "Timestamp", "Duration(s)", "Hint", "Location",
                             "CPU%", "Memory(MB)", "Threads", "GC_Gen0", "GC_Gen1", "GC_Gen2",
                             "Task", "Coroutine", "Resolved", "Trigger"])
            for i, b in enumerate(self.blocks):
                dur = b['total_duration']
                dur_val = f"{dur:.6f}" if isinstance(dur, float) else str(dur)
                loc, _, _ = self._parse_location(b.get('trigger', ''))
                sys_d = b.get('sys', {})
                gc_c = sys_d.get('gc_counts', [0, 0, 0])
                evt_type = "async_bottleneck" if b.get('type') == 'async_bottleneck' else "block"
                writer.writerow([
                    i + 1, evt_type, b['timestamp'], dur_val, b.get('hint', ''), loc,
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

    # ── HTML Report ──────────────────────────────────────────────────
    def render_html(self, output_path=None):
        if not output_path:
            output_path = f"loopsentry_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        from .report_html import generate_html
        html = generate_html(self.blocks, self.stats)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        console.print(f"[bold green]✨ HTML report saved: {output_path}[/bold green]")
        return output_path