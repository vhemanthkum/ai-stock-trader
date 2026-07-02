"""
Common utility helpers.
"""

import io
import sys
import logging
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

# Fix Windows encoding issues — force UTF-8 output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

console = Console(force_terminal=True)


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the engine."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(name)-20s | %(levelname)-5s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def print_header() -> None:
    """Print the engine header."""
    header = Text()
    header.append("╔══════════════════════════════════════════════════════════╗\n", style="bold cyan")
    header.append("║     Indian Stock AI Council Engine                      ║\n", style="bold cyan")
    header.append("║     6-Agent Multi-Model Analysis System                 ║\n", style="bold cyan")
    header.append(f"║     {datetime.now().strftime('%B %d, %Y — %I:%M %p IST'):<53}║\n", style="bold cyan")
    header.append("╚══════════════════════════════════════════════════════════╝", style="bold cyan")
    console.print(header)


def print_macro_status(macro: dict, mmi: float, vix: float) -> None:
    """Print macro regime status."""
    regime = macro.get("regime", "N/A")
    score = macro.get("sentiment_score", 0)

    # Color code
    if regime == "Bull":
        regime_color = "green"
    elif regime == "Bear":
        regime_color = "red"
    else:
        regime_color = "yellow"

    table = Table(title="📊 Market Regime", show_header=False, border_style="dim")
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")

    table.add_row("Regime", f"[bold {regime_color}]{regime}[/]")
    table.add_row("Sentiment", f"{score}/100")
    table.add_row("India VIX", f"{'🟢' if vix < 17 else '🟡' if vix < 22 else '🔴'} {vix}")
    table.add_row("MMI Score", f"{mmi}")

    console.print(table)


def print_stock_result(result: dict) -> None:
    """Print a single stock's council call."""
    action = result.get("action", "N/A")
    ticker = result.get("ticker", "N/A").replace(".NS", "")
    confidence = result.get("confidence", 0)

    # Color code action
    if action == "BUY":
        action_str = f"[bold green]✅ BUY[/]"
        border = "green"
    elif action == "AVOID":
        action_str = f"[bold red]❌ AVOID[/]"
        border = "red"
    else:
        action_str = f"[bold yellow]⏸ HOLD[/]"
        border = "yellow"

    content = f"""
{action_str}  [bold]{ticker}[/]  |  Confidence: [bold]{confidence}%[/]

Entry: ₹{result.get('entry_range_low', 0):,.2f} – ₹{result.get('entry_range_high', 0):,.2f}
SL: {result.get('stop_loss_pct', 0)}%  |  T1: ₹{result.get('target_1', 0):,.2f}  |  T2: ₹{result.get('target_2', 0):,.2f}
Position Mult: {result.get('position_multiplier', 1.0)}×

[dim]{result.get('reasoning', 'No reasoning provided')}[/dim]
"""

    console.print(Panel(content, border_style=border, title=f"[bold]{ticker}[/]"))


def print_summary_table(results: list[dict]) -> None:
    """Print ranked summary table of all stock calls."""
    table = Table(title="📋 Daily Picks — Ranked by Confidence", border_style="cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("Ticker", style="bold", width=12)
    table.add_column("Action", width=8)
    table.add_column("Conf.", justify="right", width=6)
    table.add_column("Entry Range", justify="right", width=20)
    table.add_column("SL%", justify="right", width=6)
    table.add_column("Target 1", justify="right", width=12)
    table.add_column("Target 2", justify="right", width=12)
    table.add_column("Mult", justify="right", width=5)

    for i, r in enumerate(results, 1):
        action = r.get("action", "N/A")
        if action == "BUY":
            action_str = "[green]BUY[/]"
        elif action == "AVOID":
            action_str = "[red]AVOID[/]"
        else:
            action_str = "[yellow]HOLD[/]"

        table.add_row(
            str(i),
            r.get("ticker", "N/A").replace(".NS", ""),
            action_str,
            f"{r.get('confidence', 0)}%",
            f"₹{r.get('entry_range_low', 0):,.0f}–₹{r.get('entry_range_high', 0):,.0f}",
            f"{r.get('stop_loss_pct', 0)}%",
            f"₹{r.get('target_1', 0):,.0f}",
            f"₹{r.get('target_2', 0):,.0f}",
            f"{r.get('position_multiplier', 1.0)}×",
        )

    console.print(table)
