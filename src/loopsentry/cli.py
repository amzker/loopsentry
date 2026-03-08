import argparse
import sys
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
from rich.console import Console
from .analyzer import Analyzer

console = Console()

def _get_version():
    try:
        return version("loopsentry")
    except PackageNotFoundError:
        return "dev"

def main():
    parser = argparse.ArgumentParser(
        description="LoopSentry: Asyncio Event Loop Blocker Detector & Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  loopsentry analyze                     # Auto-select latest logs, interactive TUI
  loopsentry analyze -d sentry_logs/     # Analyze specific directory
  loopsentry analyze -d . --html         # Generate standalone HTML report
  loopsentry analyze -d . --csv          # Generate CSV report
  loopsentry analyze --sort duration     # Start TUI sorted by duration
"""
    )
    parser.add_argument("-V", "--version", action="version", version=f"loopsentry {_get_version()}")
    subparsers = parser.add_subparsers(dest="command")
    
    an_parser = subparsers.add_parser("analyze", help="Analyze captured logs")
    an_parser.add_argument("-d", "--dir", help="Directory to scan")
    an_parser.add_argument("-f", "--file", help="Specific .jsonl file to scan")
    an_parser.add_argument("--html", action="store_true", help="Generate standalone HTML report")
    an_parser.add_argument("--csv", action="store_true", help="Generate CSV report")
    an_parser.add_argument("--sort", choices=["time", "duration", "cpu", "memory", "type"],
                           default="time", help="Sort events by column (default: time)")
    an_parser.add_argument("-o", "--output", help="Output file path for HTML/CSV")

    args = parser.parse_args()

    if args.command == "analyze":
        target = args.file if args.file else args.dir
        if not target:
            log_base = Path("sentry_logs")
            if log_base.exists():
                dirs = sorted(log_base.glob("*"))
                if dirs:
                    target = dirs[-1]
                    console.print(f"[dim]Auto-selecting latest log: {target}[/dim]")
                else:
                    console.print("[red]No logs found in sentry_logs/[/red]")
                    return
            else:
                console.print("[red]No sentry_logs/ directory found.[/red]")
                return

        analyzer = Analyzer(target)
        analyzer.sort_by = args.sort
        analyzer.run()

        if not analyzer.blocks:
            console.print("[yellow]No events found in logs.[/yellow]")
            return

        if args.html:
            analyzer.render_html(args.output)
        elif args.csv:
            analyzer.render_csv(args.output)
        else:
            analyzer.interactive_tui()
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()