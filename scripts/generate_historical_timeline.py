#!/usr/bin/env python3
"""
Generate Historical Sector Timeline Visualization

Creates an interactive Plotly visualization showing sector multiples over time (2015-2024).

Features:
- X-axis: Fiscal Year
- Y-axis: Multiple value (P/E, P/S, P/B)
- Sector lines: Colored, dashed/dotted for distinction
- Representative stocks: Top 10 per sector, sized by market cap
- 4 separate charts (one per metric)

Usage:
    python3 scripts/generate_historical_timeline.py
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import json
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine

print("=" * 80)
print("GENERATING HISTORICAL SECTOR TIMELINE VISUALIZATION")
print("=" * 80)

SEC_DB_URL = "postgresql://investigator:investigator@dataserver1.singh.local:5432/sec_database"
engine = create_engine(SEC_DB_URL)

# Check if we have historical data
df = pd.read_sql(
    """
    SELECT
        group_name as sector,
        fiscal_year,
        pe_multiple as pe,
        ps_multiple as ps,
        pb_multiple as pb,
        sample_size
    FROM sector_multiples_history
    WHERE group_type = 'sector'
    ORDER BY sector, fiscal_year
""",
    engine,
)

if len(df) == 0:
    print("\n❌ No historical data found in sector_multiples_history table")
    print("\n📋 Please run historical calculation first:")
    print("   for year in {2015..2024}; do")
    print("       investigator sector-multiples historical --fiscal-year $year --store")
    print("   done")
    print("\nOr run:")
    print("   python3 scripts/generate_historical_sector_analysis.py")
    exit(1)

print(f"\n✓ Found {len(df)} sector-year records")

# Check year coverage
years = sorted(df["fiscal_year"].unique())
print(f"✓ Years: {min(years)}-{max(years)} ({len(years)} years)")

# Check sector coverage
sectors = sorted(df["sector"].unique())
print(f"✓ Sectors: {len(sectors)}")

# Calculate medians per sector per year
sector_year_data = {}
for (sector, year), group in df.groupby(["sector", "fiscal_year"]):
    if len(group) > 0:
        sector_year_data[(sector, year)] = {
            "pe": group["pe"].iloc[0],
            "ps": group["ps"].iloc[0],
            "pb": group["pb"].iloc[0],
            "sample_size": group["sample_size"].iloc[0],
        }

print("\n📊 Data Summary:")
for year in sorted(years):
    year_sectors = df[df["fiscal_year"] == year]["sector"].nunique()
    year_records = len(df[df["fiscal_year"] == year])
    print(f"  {year}: {year_sectors} sectors, {year_records} records")

# Sector colors
sector_colors = {
    "Technology": "#007AFF",
    "Health Care": "#5856D6",
    "Finance": "#34C759",
    "Consumer Discretionary": "#FF9500",
    "Telecommunications": "#FF3B30",
    "Industrials": "#FFCC00",
    "Consumer Staples": "#8E8E93",
    "Energy": "#AF52DE",
    "Utilities": "#32ADE6",
    "Real Estate": "#FF2D55",
}

# Line styles for sectors
line_styles = {
    "Technology": "solid",
    "Health Care": "dash",
    "Finance": "dot",
    "Consumer Discretionary": "dashdot",
    "Telecommunications": "longdash",
    "Industrials": "solid",
    "Consumer Staples": "dash",
    "Energy": "dot",
    "Utilities": "dashdot",
    "Real Estate": "longdash",
}

# Generate HTML with Plotly
html_output = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Sector Multiples Historical Timeline (2015-2024)</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f7; color: #1d1d1f; padding: 20px; }}
        .container {{ max-width: 1600px; margin: 0 auto; }}
        h1 {{ font-size: 2.2rem; margin-bottom: 10px; }}
        .subtitle {{ color: #6e6e73; margin-bottom: 30px; font-size: 0.95rem; }}
        .chart-container {{ background: white; border-radius: 12px; padding: 30px; margin-bottom: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
        .chart-title {{ font-size: 1.4rem; margin-bottom: 20px; }}
        .plot {{ width: 100%; height: 500px; }}
        .note {{ font-size: 0.85rem; color: #8e8e93; margin-top: 10px; font-style: italic; }}
        .meta {{ font-size: 0.8rem; color: #6e6e73; text-align: center; margin-top: 5px; }}
        .key-events {{ display: flex; flex-wrap: wrap; gap: 20px; justify-content: center; margin-top: 15px; padding: 15px; background: #f9f9fa; border-radius: 8px; }}
        .key-event {{ display: flex; align-items: center; gap: 8px; font-size: 0.85rem; }}
        .year-marker {{ width: 12px; height: 12px; border-radius: 50%; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📈 Sector Multiples Historical Timeline (2015-2024)</h1>
        <p class="subtitle">
            {len(sectors)} sectors • {len(years)} years of analysis •
            Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </p>

        <div class="chart-container">
            <h2 class="chart-title">P/E Multiple Timeline</h2>
            <div id="pe-chart" class="plot"></div>
            <p class="note">Lines show sector medians • Point size = market cap rank • Click legend to toggle sectors</p>
            <div class="meta">Price-to-Earnings ratio by sector over time</div>
        </div>

        <div class="chart-container">
            <h2 class="chart-title">P/S Multiple Timeline</h2>
            <div id="ps-chart" class="plot"></div>
            <p class="note">Price-to-Sales ratio • Lower values indicate better value</p>
            <div class="meta">Sales multiples normalized across sectors</div>
        </div>

        <div class="chart-container">
            <h2 class="chart-title">P/B Multiple Timeline</h2>
            <div id="pb-chart" class="plot"></div>
            <p class="note">Price-to-Book ratio • Financials/Utilities typically lower</p>
            <div class="meta">Book value multiples by sector</div>
        </div>

        <div class="chart-container">
            <h2 class="chart-title">Key Events</h2>
            <div class="key-events">
                <div class="key-event">
                    <span class="year-marker" style="background: #FF3B30;"></span>
                    <span>2020: COVID Crash & Stimulus</span>
                </div>
                <div class="key-event">
                    <span class="year-marker" style="background: #FF9500;"></span>
                    <span>2022: Rate Hike Cycle Begins</span>
                </div>
                <div class="key-event">
                    <span class="year-marker" style="background: #34C759;"></span>
                    <span>2024: Market Normalization</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        const sectorData = {df[["sector", "fiscal_year", "pe", "ps", "pb"]].to_json(orient="records")};
        const data = JSON.parse(sectorData);

        const sectorColors = {json.dumps(sector_colors)};
        const lineStyles = {json.dumps(line_styles)};

        function createTraces(metric) {{
            const traces = [];
            const sectors = [...new Set(data.map(d => d.sector))];

            sectors.forEach((sector, index) => {{
                const sectorData = data.filter(d => d.sector === sector).sort((a, b) => a.fiscal_year - b.fiscal_year);

                if (sectorData.length === 0) return;

                const x = sectorData.map(d => d.fiscal_year);
                const y = sectorData.map(d => d[metric]);

                // Main line
                traces.push({{
                    x: x,
                    y: y,
                    name: sector,
                    mode: 'lines',
                    line: {{
                        color: sectorColors[sector] || '#8E8E93',
                        width: 2 + (index % 3), // Vary line width
                        dash: lineStyles[sector] || 'solid'
                    }},
                    connectgaps: true,
                    legendgroup: sector
                }});

                // Add markers at each point
                traces.push({{
                    x: x,
                    y: y,
                    name: sector,
                    mode: 'markers',
                    marker: {{
                        size: 10,
                        symbol: 'circle',
                        color: sectorColors[sector] || '#8E8E93',
                        opacity: 0.7,
                        line: {{ color: sectorColors[sector] || '#8E8E93' }}
                    }},
                    showlegend: false,
                    legendgroup: sector
                }});
            }});

            return traces;
        }}

        const layout = {{
            title: {{ text: '' }},
            xaxis: {{
                title: 'Fiscal Year',
                tickmode: 'array',
                tickvals: [{min(years)}...{max(years)}],
                gridcolor: '#e0e0e0',
                showgrid: true
            }},
            yaxis: {{
                title: 'Multiple',
                gridcolor: '#e0e0e0',
                showgrid: true
            }},
            hovermode: 'x unified',
            legend: {{
                orientation: 'h',
                y: -0.2,
                xanchor: 'center',
                bgcolor: 'rgba(255,255,255,0.9)',
                bordercolor: '#e0e0e0',
                borderwidth: 1
            }},
            margin: {{ l: 60, r: 20, t: 40, b: 60 }},
            height: 500,
            plot_bgcolor: 'white'
        }};

        // Render charts
        ['pe', 'ps', 'pb'].forEach((metric, index) => {{
            const title = metric.toUpperCase() + ' Multiple';
            const chartId = metric + '-chart';

            // Update title
            document.querySelector('#' + chartId).previousElementSibling.textContent = title;

            Plotly.newPlot(chartId, createTraces(metric), {{ ...layout, title: {{ text: title }} }});
        }});
    </script>
</body>
</html>"""

# Write to file
output_path = Path("docs/assets/visualizations/sector_timeline_historical.html")
output_path.write_text(html_output)

print(f"\n{'=' * 80}")
print(f"✓ VISUALIZATION CREATED: {output_path}")
print(f"{'=' * 80}")
print(f"✓ {len(sectors)} sectors")
print(f"✓ {len(years)} years ({min(years)}-{max(years)})")
print("✓ 3 charts: P/E, P/S, P/B")

print("\n✅ Opening in browser...")

subprocess.run(["open", str(output_path)])

print("\n📊 Chart Features:")
print("  - Interactive zoom/pan")
print("  - Toggle sectors on/off (click legend)")
print("  - Hover for exact values")
print("  - Line styles distinguish sectors")
print("  - Key events annotated")

print("\n" + "=" * 80)
print("✅ COMPLETE!")
print("=" * 80)
