import json
import time
import re
import math
import os
from pathlib import Path
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
        self.stats = {"total_time": 0.0, "count": 0, "crashes": 0, "async_slow": 0}
        
        self.page = 1
        self.page_size = 15
        self.sort_by = 'time' 
        self.view_mode = 'list'
        self.filter_term = ""

    def _analyze_heuristics(self, block):
        if block.get('type') == 'async_bottleneck':
            return "🐢 Slow Async Task"

        stack_list = block.get('stack', [])
        stack_str = "".join(stack_list).lower()
        
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
                            
                            # Async Bottleneck
                            if entry['type'] == 'async_bottleneck':
                                entry['total_duration'] = entry['duration_current']
                                entry['resolved'] = True
                                entry['hint'] = self._analyze_heuristics(entry)
                                entry['trigger'] = f"{entry.get('coro')} ({entry.get('task_name')})"
                                self.blocks.append(entry)
                                self.stats['async_slow'] += 1
                                continue

                            # Blocking Events
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

        self._apply_sort()

    def _apply_sort(self):
        if self.sort_by == 'time':
            self.blocks.sort(key=lambda x: x['timestamp'], reverse=True)
        elif self.sort_by == 'duration':
            self.blocks.sort(key=lambda x: x['total_duration'] if isinstance(x['total_duration'], float) else -1, reverse=True)

    def _parse_location(self, trigger_str):
        if not trigger_str: return "Unknown", "", ""
        
        # 1. Standard Stack Trace Trigger (File "...", line X)
        match = re.search(r'File "(.*?)", line (\d+)', trigger_str)
        if match:
            fname = match.group(1)
            lineno = match.group(2)
            short_name = Path(fname).name
            return f"{short_name}:{lineno}", fname, lineno
        
        # 2. Async Bottleneck Trigger: "coro_name (Task-123)"
        # We strip the (Task-123) part so grouping works
        async_match = re.search(r'^(.*?) \(Task-', trigger_str)
        if async_match:
             return async_match.group(1), "", ""

        # 3. Fallback
        return trigger_str[:40], "", ""

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
            console.print("[dim]Cmds: [white]<ID>[/] detail | [white]n[/]ext [white]p[/]rev | [white]g[/]roup | [white]s[/]ort | [white]/<text>[/] search | [white]q[/]uit[/dim]")
            
            choice = Prompt.ask("Action").lower().strip()

            if choice in ('q', 'quit', 'exit'): break
            elif choice == 'n': self.page += 1
            elif choice == 'p': self.page = max(1, self.page - 1)
            elif choice == 'g': self.view_mode = 'group' if self.view_mode == 'list' else 'list'; self.page = 1
            elif choice == 's': self.sort_by = 'duration' if self.sort_by == 'time' else 'time'; self.page = 1
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
        grid.add_row(
            Panel(f"[bold red]{len(blocks)}/{self.stats['count']}[/]", title="Blocks Found"),
            Panel(f"[bold yellow]{self.stats['total_time']:.2f}s[/]", title="Time Lost"),
            Panel(f"[bold blue]{self.stats['async_slow']}[/]", title="Async Slowness"),
        )
        console.print(grid)

        total_pages = math.ceil(len(blocks) / self.page_size)
        if self.page > total_pages: self.page = max(1, total_pages)
        start = (self.page - 1) * self.page_size
        end = start + self.page_size
        page_data = blocks[start:end]

        table = Table(box=box.SIMPLE_HEAD, expand=True)
        table.add_column("ID", style="bold white", width=4, justify="right")
        table.add_column("Time", style="cyan", width=10)
        table.add_column("Dur", style="red", width=10)
        table.add_column("Hint", style="yellow")
        table.add_column("Location", style="blue")

        for b in page_data:
            dur = b['total_duration']
            dur_fmt = f"{dur:.4f}s" if isinstance(dur, float) else str(dur)
            short_loc, _, _ = self._parse_location(b.get('trigger', ''))
            table.add_row(str(b['_id']), b['timestamp'][11:19], dur_fmt, b.get('hint', ''), short_loc)
        
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
        end = start + self.page_size
        
        table = Table(title="Top Offenders", box=box.SIMPLE_HEAD, expand=True)
        table.add_column("Location", style="bold blue")
        table.add_column("Count", justify="right")
        table.add_column("Total", style="red", justify="right")
        table.add_column("Max", style="yellow", justify="right")
        table.add_column("Hint", style="dim")

        for loc, data in sorted_groups[start:end]:
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
        info.add_row("Hint:", f"[yellow]{block.get('hint')}[/yellow]")
        
        if 'task_name' in block:
             info.add_row("Task:", block['task_name'])
             info.add_row("Coroutine:", block.get('coro'))
        
        console.print(Panel(info, title="Metadata", border_style="blue"))
        
        # --- ARGS / LOCALS DISPLAY ---
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

        # --- STACK TRACE ---
        if 'stack' in block:
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