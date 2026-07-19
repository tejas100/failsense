"""
report.py
----------
Generates a clean HTML report from a FailSense triage result JSON file.

Deliberately kept separate from classify.py: classify.py is the "brain"
(pure classification logic, returns data), this file is the "presentation"
layer (takes that data, renders it). Keeping these separate means the
report format can change without ever touching triage logic, and the
triage logic can be reused for other outputs (Slack message, dashboard,
CI annotation) without duplicating classification code.

Usage:
    python triage/report.py reports/triage_result.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path

CATEGORY_COLORS = {
    "FLAKY_ENVIRONMENT": "#d97706",   # amber
    "PRODUCT_DEFECT": "#dc2626",      # red
    "POSSIBLE_TEST_BUG": "#7c3aed",   # purple
    "UNCLASSIFIED": "#6b7280",        # gray
}

CATEGORY_LABELS = {
    "FLAKY_ENVIRONMENT": "Flaky / Environment",
    "PRODUCT_DEFECT": "Product Defect",
    "POSSIBLE_TEST_BUG": "Possible Test Bug (needs review)",
    "UNCLASSIFIED": "Unclassified (needs manual triage)",
}


def render_html(result):
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    category_rows = ""
    for category, count in result["category_counts"].items():
        pct = round(count / result["total_failed"] * 100, 1) if result["total_failed"] else 0
        color = CATEGORY_COLORS.get(category, "#6b7280")
        label = CATEGORY_LABELS.get(category, category)
        category_rows += f"""
        <div class="category-bar">
            <div class="category-label">{label}</div>
            <div class="bar-track">
                <div class="bar-fill" style="width: {pct}%; background: {color};"></div>
            </div>
            <div class="category-count">{count} ({pct}%)</div>
        </div>"""

    detail_cards = ""
    for c in result["classifications"]:
        color = CATEGORY_COLORS.get(c["category"], "#6b7280")
        label = CATEGORY_LABELS.get(c["category"], c["category"])
        detail_cards += f"""
        <div class="card" style="border-left: 4px solid {color};">
            <div class="card-header">
                <span class="badge" style="background: {color};">{label}</span>
                <span class="confidence">confidence: {c['confidence']}</span>
            </div>
            <div class="card-title">{c['nodeid']}</div>
            <div class="card-reason">{c['reason']}</div>
            <pre class="card-message">{c['message']}</pre>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FailSense Triage Report</title>
<style>
    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        background: #f9fafb;
        color: #111827;
        max-width: 900px;
        margin: 40px auto;
        padding: 0 20px;
    }}
    h1 {{ font-size: 24px; margin-bottom: 4px; }}
    .subtitle {{ color: #6b7280; margin-bottom: 32px; font-size: 14px; }}
    .stats-row {{ display: flex; gap: 16px; margin-bottom: 32px; }}
    .stat-box {{
        flex: 1;
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
    }}
    .stat-number {{ font-size: 28px; font-weight: 700; }}
    .stat-label {{ font-size: 12px; color: #6b7280; text-transform: uppercase; }}
    .category-bar {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }}
    .category-label {{ width: 220px; font-size: 13px; }}
    .bar-track {{ flex: 1; background: #e5e7eb; border-radius: 4px; height: 20px; overflow: hidden; }}
    .bar-fill {{ height: 100%; }}
    .category-count {{ width: 90px; font-size: 13px; color: #6b7280; }}
    .card {{
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
    }}
    .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
    .badge {{ color: white; font-size: 11px; font-weight: 600; padding: 4px 10px; border-radius: 12px; }}
    .confidence {{ font-size: 12px; color: #6b7280; }}
    .card-title {{ font-family: monospace; font-size: 13px; font-weight: 600; margin-bottom: 6px; }}
    .card-reason {{ font-size: 13px; color: #374151; margin-bottom: 10px; }}
    .card-message {{
        background: #1f2937;
        color: #f3f4f6;
        padding: 10px;
        border-radius: 6px;
        font-size: 12px;
        overflow-x: auto;
        white-space: pre-wrap;
    }}
    section {{ margin-bottom: 32px; }}
    h2 {{ font-size: 16px; margin-bottom: 16px; }}
</style>
</head>
<body>
    <h1>FailSense Triage Report</h1>
    <div class="subtitle">Generated {generated_at}</div>

    <div class="stats-row">
        <div class="stat-box">
            <div class="stat-number">{result['total_tests']}</div>
            <div class="stat-label">Total Tests</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">{result['total_failed']}</div>
            <div class="stat-label">Failed</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">{result['pass_rate']}%</div>
            <div class="stat-label">Pass Rate</div>
        </div>
    </div>

    <section>
        <h2>Failure Breakdown</h2>
        {category_rows if result['total_failed'] else '<p style="color:#6b7280;">No failures this run.</p>'}
    </section>

    <section>
        <h2>Details</h2>
        {detail_cards if result['total_failed'] else ''}
    </section>
</body>
</html>"""


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python triage/report.py <path_to_triage_result.json>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        result = json.load(f)

    html = render_html(result)
    output_path = Path("reports/triage_report.html")
    output_path.write_text(html)
    print(f"HTML report written to {output_path}")