import argparse
import sys
import shutil
from pathlib import Path
from rich.console import Console
from .analyzer import Analyzer

console = Console()

def main():
    parser = argparse.ArgumentParser(description="LoopSentry: Asyncio Event Loop Monitor")
    subparsers = parser.add_subparsers(dest="command")
    
    subparsers.add_parser("clean", help="Clear logs")
    
    an_parser = subparsers.add_parser("analyze", help="Analyze logs")
    an_parser.add_argument("-d", "--dir", help="Directory to scan")
    an_parser.add_argument("-f", "--file", help="File to scan")

    args = parser.parse_args()

    if args.command == "clean":
        if Path("sentry_logs").exists():
            shutil.rmtree("sentry_logs")
            console.print("[green]✔ Logs cleared.[/green]")
        else:
            console.print("[yellow]No logs found.[/yellow]")

    elif args.command == "analyze":
        target = args.file if args.file else args.dir
        if not target:
            dirs = sorted(Path("sentry_logs").glob("*"))
            if dirs:
                target = dirs[-1]
                console.print(f"[dim]Auto-selecting latest log: {target}[/dim]")
            else:
                console.print("[red]No logs found.[/red]")
                return

        analyzer = Analyzer(target)
        analyzer.run()
        analyzer.interactive_tui()
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()