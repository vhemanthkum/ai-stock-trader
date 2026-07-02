"""
HTML report generator.

Produces beautiful dark-mode HTML reports with:
- Market regime status
- Sector rankings
- Per-stock council calls with vote breakdowns
- Signal bars, confidence scores
- Position sizing recommendations
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Template

from config import REPORTS_DIR

logger = logging.getLogger(__name__)


def generate_html_report(
    market_data: dict,
    macro: dict,
    sector: dict,
    results: list[dict],
    metadata: dict | None = None,
) -> str:
    """
    Generate a complete HTML daily report.
    
    Returns the path to the saved HTML file.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%B %d, %Y — %I:%M %p IST")

    # Load template
    template_path = Path(__file__).parent / "templates" / "daily_report.html"
    if template_path.exists():
        template_str = template_path.read_text(encoding="utf-8")
    else:
        template_str = _get_fallback_template()

    template = Template(template_str)

    html = template.render(
        date=today,
        timestamp=timestamp,
        market=market_data,
        macro=macro,
        sector=sector,
        results=results,
        metadata=metadata or {},
        buy_count=sum(1 for r in results if r.get("action") == "BUY"),
        hold_count=sum(1 for r in results if r.get("action") == "HOLD"),
        avoid_count=sum(1 for r in results if r.get("action") == "AVOID"),
    )

    # Save to file
    report_path = REPORTS_DIR / f"council_report_{today}.html"
    report_path.write_text(html, encoding="utf-8")

    # Also save JSON data
    json_path = REPORTS_DIR / f"council_data_{today}.json"
    json_path.write_text(json.dumps({
        "date": today,
        "market": market_data,
        "macro": macro,
        "sector": sector,
        "results": results,
        "metadata": metadata or {},
    }, indent=2, default=str))

    logger.info(f"Report saved: {report_path}")
    return str(report_path)


def _get_fallback_template() -> str:
    """Inline fallback template if the file is missing."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Council Report — {{ date }}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 2rem; }
        .container { max-width: 900px; margin: 0 auto; }
        h1 { color: #60a5fa; margin-bottom: 0.5rem; }
        .subtitle { color: #888; margin-bottom: 2rem; }
        .card { background: #1a1a2e; border: 1px solid #2a2a3e; border-radius: 12px; padding: 1.5rem; margin-bottom: 1rem; }
        .badge { display: inline-block; padding: 4px 12px; border-radius: 8px; font-size: 12px; font-weight: 600; }
        .badge-buy { background: #064e3b; color: #34d399; }
        .badge-hold { background: #78350f; color: #fbbf24; }
        .badge-avoid { background: #7f1d1d; color: #f87171; }
        .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 2rem; }
        .metric { text-align: center; padding: 1rem; background: #1a1a2e; border-radius: 12px; border: 1px solid #2a2a3e; }
        .metric-val { font-size: 24px; font-weight: 700; }
        .metric-label { font-size: 11px; color: #888; margin-top: 4px; text-transform: uppercase; }
        table { width: 100%; border-collapse: collapse; }
        th { text-align: left; padding: 10px; color: #888; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid #2a2a3e; }
        td { padding: 10px; border-bottom: 1px solid #1a1a2e; }
        .confidence-bar { height: 6px; border-radius: 3px; background: #2a2a3e; }
        .confidence-fill { height: 100%; border-radius: 3px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🏛️ AI Council Report</h1>
        <p class="subtitle">{{ timestamp }}</p>

        <div class="grid">
            <div class="metric">
                <div class="metric-val" style="color: {{ '#34d399' if macro.get('regime') == 'Bull' else '#f87171' if macro.get('regime') == 'Bear' else '#fbbf24' }}">{{ macro.get('regime', 'N/A') }}</div>
                <div class="metric-label">Market Regime</div>
            </div>
            <div class="metric">
                <div class="metric-val" style="color: #60a5fa;">{{ market.get('india_vix', 'N/A') }}</div>
                <div class="metric-label">India VIX</div>
            </div>
            <div class="metric">
                <div class="metric-val" style="color: #a78bfa;">{{ macro.get('sentiment_score', 'N/A') }}/100</div>
                <div class="metric-label">Sentiment Score</div>
            </div>
        </div>

        <div class="grid">
            <div class="metric">
                <div class="metric-val" style="color: #34d399;">{{ buy_count }}</div>
                <div class="metric-label">BUY Calls</div>
            </div>
            <div class="metric">
                <div class="metric-val" style="color: #fbbf24;">{{ hold_count }}</div>
                <div class="metric-label">HOLD Calls</div>
            </div>
            <div class="metric">
                <div class="metric-val" style="color: #f87171;">{{ avoid_count }}</div>
                <div class="metric-label">AVOID Calls</div>
            </div>
        </div>

        <div class="card">
            <h3 style="margin-bottom: 1rem; color: #60a5fa;">📋 Stock Recommendations</h3>
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Ticker</th>
                        <th>Action</th>
                        <th>Confidence</th>
                        <th>Entry Range</th>
                        <th>SL%</th>
                        <th>Target 1</th>
                        <th>Target 2</th>
                    </tr>
                </thead>
                <tbody>
                    {% for r in results %}
                    <tr>
                        <td>{{ loop.index }}</td>
                        <td style="font-weight: 600;">{{ r.ticker | replace('.NS', '') }}</td>
                        <td>
                            <span class="badge badge-{{ r.action | lower }}">{{ r.action }}</span>
                        </td>
                        <td>
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <div class="confidence-bar" style="width: 60px;">
                                    <div class="confidence-fill" style="width: {{ r.confidence }}%; background: {{ '#34d399' if r.confidence > 70 else '#fbbf24' if r.confidence > 40 else '#f87171' }};"></div>
                                </div>
                                <span>{{ r.confidence }}%</span>
                            </div>
                        </td>
                        <td>₹{{ "%.0f" | format(r.entry_range_low) }}–₹{{ "%.0f" | format(r.entry_range_high) }}</td>
                        <td>{{ r.stop_loss_pct }}%</td>
                        <td>₹{{ "%.0f" | format(r.target_1) }}</td>
                        <td>₹{{ "%.0f" | format(r.target_2) }}</td>
                    </tr>
                    <tr>
                        <td colspan="8" style="color: #888; font-size: 12px; padding: 4px 10px 16px;">
                            {{ r.reasoning }}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="card" style="font-size: 12px; color: #666;">
            <strong>⚠️ Disclaimer:</strong> This is an AI-generated analysis for educational purposes.
            Every BUY call is a suggestion requiring your own sanity check before acting.
            AI confidence scores are NOT calibrated probabilities.
        </div>
    </div>
</body>
</html>"""
