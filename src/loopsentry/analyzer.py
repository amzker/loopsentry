import json
import time
import re
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich import box
from rich.prompt import Prompt

console = Console()

class Analyzer:
    def __init__(self, path):
        self.path = Path(path)
        self.blocks = []
        self.stats = {"total_time": 0.0, "count": 0, "crashes": 0}

    def _analyze_heuristics(self, stack_list):
        stack_str = "".join(stack_list).lower()
        if "time.sleep" in stack_str: return "Blocking Sleep"
        if "requests." in stack_str: return "Sync HTTP (requests)"
        if "subprocess.run" in stack_str: return "Sync Subprocess"
        if "while" in stack_str and "sleep" not in stack_str: return "⚠ CPU Loop?"
        return "LOGIC_BLOCK: Review Logic"

    def run(self):
        files = [self.path] if self.path.is_file() else list(self.path.rglob("*.jsonl"))
        
        for f in files:
            with open(f, 'r', encoding="utf-8") as handle:
                current_block = None
                for line in handle:
                    try:
                        entry = json.loads(line)
                        if entry['type'] == 'block_started':
                            if current_block:
                                current_block['total_duration'] = "TRANSITION"
                                current_block['resolved'] = True
                                self.blocks.append(current_block)
                            current_block = entry
                        elif entry['type'] == 'block_resolved' and current_block:
                            current_block['total_duration'] = entry['duration_current']
                            current_block['resolved'] = True
                            current_block['hint'] = self._analyze_heuristics(current_block['stack'])
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

        self.blocks.sort(key=lambda x: x['timestamp'], reverse=True)

    def _parse_location(self, trigger_str):
        match = re.search(r'File "(.*?)", line (\d+)', trigger_str)
        if match:
            # abs path for IDE clickability
            fname = match.group(1)
            lineno = match.group(2)
            return f"{Path(fname).name}:{lineno}", fname
        return "Unknown", ""

    def interactive_tui(self):
        filter_term = ""
        
        while True:
            console.clear()
            title = f"[bold cyan]LoopSentry Analysis[/]"
            if filter_term:
                title += f" [bold yellow](Filter: '{filter_term}')[/]"
            
            console.rule(title)
            
            display_blocks = []
            for idx, b in enumerate(self.blocks):
                b['_id'] = idx + 1
                searchable_text = (b.get('hint', '') + "".join(b['stack']) + b.get('trigger', '')).lower()
                if not filter_term or filter_term in searchable_text:
                    display_blocks.append(b)

            grid = Table.grid(expand=True)
            grid.add_column(justify="center", ratio=1)
            grid.add_column(justify="center", ratio=1)
            grid.add_column(justify="center", ratio=1)
            grid.add_row(
                Panel(f"[bold red]{len(display_blocks)}/{self.stats['count']}[/]", title="Blocks Shown"),
                Panel(f"[bold yellow]{self.stats['total_time']:.2f}s[/]", title="Total Lost Time"),
                Panel(f"[bold magenta]{self.stats['crashes']}[/]", title="Crashes"),
            )
            console.print(grid)
            
            table = Table(title="Event Log", box=box.SIMPLE_HEAD, expand=True)
            table.add_column("ID", style="bold white", width=4, justify="right")
            table.add_column("Time", style="cyan", width=10)
            table.add_column("Dur", style="red", width=10)
            table.add_column("Hint", style="yellow")
            table.add_column("Location", style="blue")

            for b in display_blocks[:100]:
                dur = b['total_duration']
                dur_fmt = f"{dur:.4f}s" if isinstance(dur, float) else "CRASH"
                short_loc, full_path = self._parse_location(b.get('trigger', ''))
                
                table.add_row(str(b['_id']), b['timestamp'][11:19], dur_fmt, b.get('hint', ''), short_loc)
            
            if len(display_blocks) > 15:
                table.add_row("...", "...", "...", "...", f"And {len(display_blocks)-15} more...")

            console.print(table)
            console.print("\n[dim]Commands: [white]<ID>[/] for detail | [white]<text>[/] to search | [white]reset[/] | [white]q[/]uit[/dim]")
            
            choice = Prompt.ask("Action")
            
            if choice.lower() in ('q', 'quit', 'exit'): break
            if choice.lower() in ('reset', 'clean', 'clear'): 
                filter_term = ""
                continue
            
            if choice.isdigit():
                selected_id = int(choice)
                if 1 <= selected_id <= len(self.blocks):
                    self._show_detail(self.blocks[selected_id - 1])
                else:
                    console.print("[red]ID out of range[/red]")
                    time.sleep(0.5)
            else:
                filter_term = choice.lower()

    def _show_detail(self, block):
        console.clear()
        dur = block['total_duration']
        dur_str = f"{dur:.4f}s" if isinstance(dur, float) else "CRASH"
        
        console.rule(f"[bold red]Event Detail - {dur_str}")
        
        info_table = Table(show_header=False, box=None)
        info_table.add_column(style="bold cyan")
        info_table.add_column()
        info_table.add_row("Timestamp:", block['timestamp'])
        info_table.add_row("PID:", str(block['pid']))
        info_table.add_row("Hint:", f"[yellow]{block.get('hint')}[/yellow]")
        
        _, full_path = self._parse_location(block.get('trigger', ''))
        info_table.add_row("Trigger File:", f"file://{full_path}" if full_path else "Unknown")
        
        console.print(Panel(info_table, title="Metadata", border_style="blue"))
        
        stack_code = "".join(block['stack'])
        syntax = Syntax(stack_code, "python", theme="monokai", line_numbers=True, word_wrap=True)
        console.print(Panel(syntax, title="Stack Trace", border_style="red"))
        
        Prompt.ask("\n[dim]Press [bold]Enter[/] to return...[/dim]")

    def render_html(self):
        json_data = json.dumps(self.blocks)
        html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LoopSentry Report</title>
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style> [v-cloak] {{ display: none; }} body {{ background: #0f172a; color: #e2e8f0; }} pre {{ font-family: 'Fira Code', monospace; }} </style>
</head>
<body class="p-6">
    <div id="app" v-cloak class="max-w-7xl mx-auto">
        <h1 class="text-3xl font-bold text-blue-400 mb-8">LoopSentry Report</h1>
        <input v-model="search" placeholder="Filter logs..." class="w-full bg-slate-800 border border-slate-700 rounded p-3 mb-6">
        <div class="space-y-4">
            <div v-for="(b, i) in filteredBlocks" :key="i" class="bg-slate-800 rounded border-l-4 p-4" :class="b.resolved ? 'border-yellow-500' : 'border-red-600'">
                <div class="flex justify-between font-mono text-sm mb-2 cursor-pointer" @click="b.expanded = !b.expanded">
                    <span :class="b.resolved ? 'text-yellow-400' : 'text-red-400'">{{{{ typeof b.total_duration === 'number' ? b.total_duration.toFixed(4) + 's' : b.total_duration }}}}</span>
                    <span class="text-slate-500">{{{{ b.timestamp.split('T')[1].slice(0,8) }}}}</span>
                </div>
                <div class="text-slate-400 text-xs mb-2">{{{{ b.hint }}}}</div>
                <pre v-if="b.expanded" class="bg-black/30 p-2 rounded text-xs text-slate-300 overflow-x-auto">{{{{ b.stack.join('') }}}}</pre>
            </div>
        </div>
    </div>
    <script>
        const {{ createApp }} = Vue;
        createApp({{
            data() {{ return {{ blocks: {json_data}.map(b => ({{...b, expanded: false}})), search: '' }} }},
            computed: {{ filteredBlocks() {{ return this.blocks.filter(b => (b.trigger+b.hint+b.stack.join('')).toLowerCase().includes(this.search.toLowerCase())) }} }}
        }}).mount('#app');
    </script>
</body>
</html>
        """
        with open("loopsentry_report.html", "w", encoding="utf-8") as f: f.write(html_template)
        console.print(f"[green]Report: loopsentry_report.html[/green]")