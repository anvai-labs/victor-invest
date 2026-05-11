#!/usr/bin/env python3
"""
Generate Historical Sector Timeline Visualization with Representative Stocks

Creates an interactive Plotly visualization showing sector multiples over time (2016-2024)
with representative stock bubbles for each sector (shown for the most recent year).

Features:
- X-axis: Fiscal Year
- Y-axis: Multiple value (P/E, P/S, P/B)
- Sector lines: Colored, dashed/dotted for distinction
- Representative stocks: Top stocks per sector shown as bubbles (for 2024)
- 3 separate charts (one per metric)

Usage:
    python3 scripts/generate_historical_timeline_with_stocks.py
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
print("GENERATING HISTORICAL SECTOR TIMELINE VISUALIZATION WITH REPRESENTATIVE STOCKS")
print("=" * 80)

SEC_DB_URL = "postgresql://investigator:investigator@dataserver1.singh.local:5432/sec_database"
engine = create_engine(SEC_DB_URL)

# Fetch sector medians
print("\n📊 Fetching sector median data...")
sector_medians = pd.read_sql(
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

print(f"✓ Found {len(sector_medians)} sector-year records")

# Fetch representative stocks for 2024
print("\n🔍 Fetching representative stocks for 2024...")

representative_stocks = pd.read_sql(
    """
    WITH sector_list AS (
        SELECT DISTINCT group_name
        FROM sector_multiples_history
        WHERE group_type = 'sector'
            AND fiscal_year = 2024
    ),
    symbol_metrics AS (
        SELECT
            s.ticker as symbol,
            s."Sector" as sector,
            s.mktcap as market_cap,
            s.pe_ratio,
            s.ps_ratio,
            s.pb_ratio,
            ROW_NUMBER() OVER (PARTITION BY s."Sector" ORDER BY s.mktcap DESC NULLS LAST) as rank_in_sector
        FROM symbol s
        INNER JOIN sector_list sl ON s."Sector" = sl.group_name
        WHERE s.mktcap > 0
            AND s."Sector" IS NOT NULL
    )
    SELECT sm.symbol, sm.sector, sm.market_cap,
           COALESCE(sm.pe_ratio, 0) as pe_ratio,
           COALESCE(sm.ps_ratio, 0) as ps_ratio,
           COALESCE(sm.pb_ratio, 0) as pb_ratio,
           sm.rank_in_sector
    FROM symbol_metrics sm
    WHERE sm.rank_in_sector <= 10
        AND (sm.pe_ratio > 0 OR sm.ps_ratio > 0 OR sm.pb_ratio > 0)
    ORDER BY sm.sector, sm.rank_in_sector
""",
    engine,
)

print(f"✓ Found {len(representative_stocks)} representative stocks")
print(f"✓ Sectors with stocks: {representative_stocks['sector'].nunique()}")

# Prepare data for visualization
years = sorted(sector_medians["fiscal_year"].unique())
sectors_list = sorted(sector_medians["sector"].unique())

# Sector colors
sector_colors = {
    "Technology": "#007AFF",
    "Health Care": "#5856D6",
    "Healthcare": "#5856D6",
    "Finance": "#34C759",
    "Financials": "#34C759",
    "Consumer Discretionary": "#FF9500",
    "Telecommunications": "#FF3B30",
    "Communication Services": "#FF3B30",
    "Industrials": "#FFCC00",
    "Consumer Staples": "#8E8E93",
    "Energy": "#AF52DE",
    "Utilities": "#32ADE6",
    "Real Estate": "#FF2D55",
    "Electronic Components": "#007AFF",
    "Computer Manufacturing": "#007AFF",
    "Interactive Media": "#007AFF",
}

# Line styles for sectors
line_styles = {
    "Technology": "solid",
    "Health Care": "dash",
    "Healthcare": "dash",
    "Finance": "dot",
    "Financials": "dot",
    "Consumer Discretionary": "dashdot",
    "Telecommunications": "longdash",
    "Communication Services": "longdash",
    "Industrials": "solid",
    "Consumer Staples": "dash",
    "Energy": "dot",
    "Utilities": "dashdot",
    "Real Estate": "longdash",
    "Electronic Components": "solid",
    "Computer Manufacturing": "dash",
    "Interactive Media": "dot",
}

print("\n📊 Final Data Summary:")
print(f"  Years: {min(years)}-{max(years)} ({len(years)} years)")
print(f"  Sectors: {len(sectors_list)}")
print(f"  Representative stocks (2024): {len(representative_stocks)}")

# Generate HTML with Plotly
html_output = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Sector Multiples Historical Timeline with Representative Stocks (2016-2024)</title>
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
        .plot {{ width: 100%; height: 600px; }}
        .note {{ font-size: 0.85rem; color: #8e8e93; margin-top: 10px; font-style: italic; }}
        .meta {{ font-size: 0.8rem; color: #6e6e73; text-align: center; margin-top: 5px; }}
        .key-events {{ display: flex; flex-wrap: wrap; gap: 20px; justify-content: center; margin-top: 15px; padding: 15px; background: #f9f9fa; border-radius: 8px; }}
        .key-event {{ display: flex; align-items: center; gap: 8px; font-size: 0.85rem; }}
        .year-marker {{ width: 12px; height: 12px; border-radius: 50%; }}
        .legend-info {{ font-size: 0.8rem; color: #6e6e73; margin-top: 15px; padding: 10px; background: #f9f9fa; border-radius: 8px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📈 Sector Multiples Historical Timeline with Representative Stocks</h1>
        <p class="subtitle">
            {len(sectors_list)} sectors • {len(years)} years • {len(representative_stocks)} representative stocks (2024) •
            Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </p>

        <div class="chart-container">
            <h2 class="chart-title">P/E Multiple Timeline</h2>
            <div id="pe-chart" class="plot"></div>
            <p class="note">Lines show sector medians over time • Bubbles show top 10 stocks by market cap (2024) • Click legend to toggle</p>
            <div class="meta">Price-to-Earnings ratio by sector over time</div>
        </div>

        <div class="chart-container">
            <h2 class="chart-title">P/S Multiple Timeline</h2>
            <div id="ps-chart" class="plot"></div>
            <p class="note">Sales multiples normalized across sectors</p>
            <div class="meta">Price-to-Sales ratio by sector over time</div>
        </div>

        <div class="chart-container">
            <h2 class="chart-title">P/B Multiple Timeline</h2>
            <div id="pb-chart" class="plot"></div>
            <p class="note">Book value multiples by sector</p>
            <div class="meta">Price-to-Book ratio by sector over time</div>
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
            <div class="legend-info">
                <strong>Visualization Features:</strong><br>
                • <strong>Lines:</strong> Show sector median multiples over time (2016-2024)<br>
                • <strong>Bubbles:</strong> Show top 10 stocks by market cap for each sector in 2024<br>
                • <strong>Bubble Size:</strong> Proportional to market cap<br>
                • <strong>Hover:</strong> Shows stock symbol and exact values<br>
                • <strong>Click Legend:</strong> Toggle sectors on/off
            </div>
        </div>
    </div>

    <script>
        // Sector medians data
        const sectorData = {sector_medians[["sector", "fiscal_year", "pe", "ps", "pb"]].to_json(orient="records")};
        const medians = JSON.parse(sectorData);

        // Representative stocks data (2024 only)
        const stocksData = {representative_stocks[["symbol", "sector", "market_cap", "pe_ratio", "ps_ratio", "pb_ratio"]].to_json(orient="records")};
        const stocks = JSON.parse(stocksData);

        const sectorColors = {json.dumps(sector_colors)};
        const lineStyles = {json.dumps(line_styles)};

        function createTraces(metric) {{
            const traces = [];
            const sectors = [...new Set(medians.map(d => d.sector))];

            // Map ratio names
            const metricMap = {{
                'pe': 'pe_ratio',
                'ps': 'ps_ratio',
                'pb': 'pb_ratio'
            }};
            const stockMetric = metricMap[metric];

            sectors.forEach((sector) => {{
                const sectorMedianData = medians.filter(d => d.sector === sector).sort((a, b) => a.fiscal_year - b.fiscal_year);

                if (sectorMedianData.length === 0) return;

                const x = sectorMedianData.map(d => d.fiscal_year);
                const y = sectorMedianData.map(d => d[metric]);

                const color = sectorColors[sector] || '#8E8E93';
                const dash = lineStyles[sector] || 'solid';

                // Main median line
                traces.push({{
                    x: x,
                    y: y,
                    name: sector,
                    mode: 'lines',
                    line: {{
                        color: color,
                        width: 3,
                        dash: dash
                    }},
                    connectgaps: true,
                    legendgroup: sector,
                    hovertemplate: `<b>${{sector}}</b><br>Fiscal Year: %{{x}}<br>${{metric.toUpperCase()}}: %{{y:.2f}}x<extra></extra>`
                }});

                // Representative stock bubbles for 2024
                const sectorStocks = stocks.filter(s => s.sector === sector && s[stockMetric] > 0);

                sectorStocks.forEach(stock => {{
                    // Calculate size based on market cap (log scale)
                    const minMarketCap = 1e9; // $1B
                    const maxMarketCap = 3e12; // $3T
                    const marketCap = Math.max(minMarketCap, stock.market_cap);
                    const normalizedSize = Math.max(8, Math.min(40, 8 + 32 * (Math.log(marketCap) - Math.log(minMarketCap)) / (Math.log(maxMarketCap) - Math.log(minMarketCap))));

                    traces.push({{
                        x: [2024],
                        y: [stock[stockMetric]],
                        name: sector,
                        mode: 'markers',
                        marker: {{
                            size: normalizedSize,
                            symbol: 'circle',
                            color: color,
                            opacity: 0.6,
                            line: {{
                                color: color,
                                width: 1
                            }}
                        }},
                        text: [stock.symbol],
                        hovertemplate: `<b>${{stock.symbol}}</b> (${{sector}})<br>Fiscal Year: 2024<br>${{metric.toUpperCase()}}: %{{y:.2f}}x<br>Market Cap: ${{(stock.market_cap / 1e9).toFixed(1)}}B<extra></extra>`,
                        showlegend: false,
                        legendgroup: sector
                    }});
                }});
            }});

            return traces;
        }}

        const layout = {{
            title: {{ text: '' }},
            xaxis: {{
                title: 'Fiscal Year',
                tickmode: 'linear',
                dtick: 1,
                gridcolor: '#e0e0e0',
                showgrid: true
            }},
            yaxis: {{
                title: 'Multiple',
                gridcolor: '#e0e0e0',
                showgrid: true
            }},
            hovermode: 'closest',
            legend: {{
                orientation: 'h',
                y: -0.15,
                xanchor: 'center',
                bgcolor: 'rgba(255,255,255,0.9)',
                bordercolor: '#e0e0e0',
                borderwidth: 1
            }},
            margin: {{ l: 60, r: 20, t: 40, b: 80 }},
            height: 600,
            plot_bgcolor: 'white'
        }};

        // Render charts
        ['pe', 'ps', 'pb'].forEach(metric => {{
            const chartId = metric + '-chart';
            Plotly.newPlot(chartId, createTraces(metric), layout, {{ responsive: true }});
        }});
    </script>
</body>
</html>"""

# Write to file
output_path = Path("docs/assets/visualizations/sector_timeline_historical_with_stocks.html")
output_path.write_text(html_output)

print(f"\n{'=' * 80}")
print(f"✓ VISUALIZATION CREATED: {output_path}")
print(f"{'=' * 80}")
print(f"✓ {len(sectors_list)} sectors")
print(f"✓ {len(years)} years ({min(years)}-{max(years)})")
print("✓ 3 charts: P/E, P/S, P/B")
print(f"✓ {len(representative_stocks)} representative stock bubbles")

print("\n✅ Opening in browser...")

subprocess.run(["open", str(output_path)])

print("\n📊 Chart Features:")
print("  - Interactive zoom/pan")
print("  - Toggle sectors on/off (click legend)")
print("  - Hover for exact values and stock symbols")
print("  - Bubble size represents market cap")
print("  - Line styles distinguish sectors")
print("  - Key events annotated")

print("\n" + "=" * 80)
print("✅ COMPLETE!")
print("=" * 80)
