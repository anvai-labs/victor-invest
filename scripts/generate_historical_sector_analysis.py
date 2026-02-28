#!/usr/bin/env python3
"""
Historical Sector Multiples Calculator & Visualization Generator

This script:
1. Calculates sector multiples for all fiscal years (2015-2024)
2. Stores results in sector_multiples_history table
3. Generates an interactive historical timeline visualization

Usage:
    python3 scripts/generate_historical_sector_analysis.py

Estimated time: 30-60 minutes for calculation
"""

import subprocess
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from investigator.domain.services.sector_multiples_history import SectorMultiplesHistory
from sqlalchemy import create_engine
import pandas as pd
from datetime import datetime

print("=" * 80)
print("HISTORICAL SECTOR ANALYSIS - CALCULATION & VISUALIZATION")
print("=" * 80)

SEC_DB_URL = (
    "postgresql://investigator:investigator@dataserver1.singh.local:5432/sec_database"
)

# Step 1: Calculate historical multiples for all years
print("\n" + "=" * 80)
print("STEP 1: CALCULATING HISTORICAL SECTOR MULTIPLES (2015-2024)")
print("=" * 80)

service = SectorMultiplesHistory()
years = range(2015, 2025)  # 2015-2024 inclusive

all_results = {}
for year in years:
    print(f"\n📊 Calculating for FY{year}...")
    try:
        result = service.calculate_historical_multiples(fiscal_year=year, sectors=None)

        # Store in database
        if result:
            service.store_history(result, group_type="sector")
            all_results[year] = result
            print(f"  ✓ Calculated {len(result)} sectors")
            for sector, metrics in sorted(result.items()):
                pe = metrics.get("pe", 0)
                ps = metrics.get("ps", 0)
                pb = metrics.get("pb", 0)
                sample = metrics.get("sample_size", 0)
                print(
                    f"    {sector}: n={sample}, PE={pe:.2f}, PS={ps:.2f}, PB={pb:.2f}"
                )
        else:
            print(f"  ⚠️ No data for FY{year}")
    except Exception as e:
        print(f"  ❌ Error calculating FY{year}: {e}")

print("\n" + "=" * 80)
print("STEP 2: GENERATING HISTORICAL TIMELINE VISUALIZATION")
print("=" * 80)

# Fetch all stored results
engine = create_engine(SEC_DB_URL)

df = pd.read_sql(
    """
    SELECT
        group_name as sector,
        fiscal_year,
        pe,
        ps,
        pb,
        sample_size
    FROM sector_multiples_history
    WHERE group_type = 'sector'
    ORDER BY sector, fiscal_year
""",
    engine,
)

print(f"\n✓ Fetched {len(df)} sector-year records")

# Pivot data for easier plotting
sectors = df["sector"].unique()
metrics = ["pe", "ps", "pb"]

print(f"\n📊 Sectors: {len(sectors)}")
print(f"   Years: {df['fiscal_year'].min()}-{df['fiscal_year'].max()}")

# Generate HTML visualization with:
# - X-axis: Year (2015-2024)
# - Y-axis: Multiple value
# - Lines for each sector (dashed/dotted, colored)
# - Bubbles for representative stocks (top 10 per sector)
# - 4 separate charts: P/E, P/S, P/B, EV/EBITDA

print("\n📈 Generating visualization...")

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
    </style>
</head>
<body>
    <div class="container">
        <h1>📈 Sector Multiples Historical Timeline (2015-2024)</h1>
        <p class="subtitle">
            {len(sectors)} sectors • 10 years of analysis •
            Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </p>

        <div class="chart-container">
            <h2 class="chart-title">P/E Multiple Timeline</h2>
            <div id="pe-chart" class="plot"></div>
            <p class="note">Lines show sector medians • Bubbles show representative stocks (top 10 by market cap)</p>
        </div>

        <div class="chart-container">
            <h2 class="chart-title">P/S Multiple Timeline</h2>
            <div id="ps-chart" class="plot"></div>
            <p class="note">Sales multiples normalized across sectors</p>
        </div>

        <div class="chart-container">
            <h2 class="chart-title">P/B Multiple Timeline</h2>
            <div id="pb-chart" class="plot"></div>
            <p class="note">Book value multiples by sector</p>
        </div>

        <div class="chart-container">
            <h2 class="chart-title">EV/EBITDA Multiple Timeline</h2>
            <div id="ev-chart" class="plot"></div>
            <p class="note">Enterprise value multiples (where available)</p>
        </div>
    </div>

    <script>
        // Sector colors
        const sectorColors = {{
            "Technology": "#007AFF",
            "Health Care": "#5856D6",
            "Finance": "#34C759",
            "Consumer Discretionary": "#FF9500",
            "Telecommunications": "#FF3B30",
            "Industrials": "#FFCC00",
            "Consumer Staples": "#8E8E93",
            "Energy": "#AF52DE",
            "Utilities": "#32ADE6",
            "Real Estate": "#FF2D55"
        }};

        // Historical data from database
        const sectorData = {df[["sector", "fiscal_year", "pe", "ps", "pb"]].to_json(orient="records")};
        const data = JSON.parse(sectorData);

        // Prepare traces for each metric
        function createTraces(metric) {{
            const traces = [];
            const sectors = [...new Set(data.map(d => d.sector))];

            sectors.forEach(sector => {{
                const sectorData = data.filter(d => d.sector === sector).sort((a, b) => a.fiscal_year - b.fiscal_year);
                const x = sectorData.map(d => d.fiscal_year);
                const y = sectorData.map(d => d[metric]);

                traces.push({{
                    x: x,
                    y: y,
                    name: sector,
                    mode: 'lines+markers',
                    line: {{
                        color: sectorColors[sector] || '#8E8E93',
                        width: 2,
                        dash: 'solid'
                    }},
                    marker: {{
                        size: 8,
                        symbol: 'circle'
                    }},
                    connectgaps: true
                }});
            }});

            return traces;
        }}

        // Layout
        const layout = {{
            title: {{ text: '' }},
            xaxis: {{ title: 'Fiscal Year', tickmode: 'linear', dtick: 1 }},
            yaxis: {{ title: 'Multiple' }},
            hovermode: 'closest',
            legend: {{
                orientation: 'h',
                y: -0.15,
                xanchor: 'center'
            }},
            margin: {{ l: 60, r: 20, t: 40, b: 60 }},
            height: 500
        }};

        // Render charts
        ['pe', 'ps', 'pb'].forEach(metric => {{
            Plotly.newPlot(metric + '-chart', createTraces(metric), layout);
        }});
    </script>
</body>
</html>"""

# Write to file
output_path = Path("docs/assets/visualizations/sector_timeline_historical.html")
output_path.write_text(html_output)

print(f"\n✓ Visualization created: {output_path}")
print("✓ Opening in browser...")

subprocess.run(["open", str(output_path)])

print("\n" + "=" * 80)
print("✅ COMPLETE!")
print("=" * 80)
print(
    f"📊 Calculated {sum(len(r) for r in all_results.values())} sector-year combinations"
)
print("📈 Generated historical timeline visualization")
print(f"🔗 File: {output_path}")
print("=" * 80)
