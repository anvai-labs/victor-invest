#!/usr/bin/env python3
"""
Generate Historical Sector Timeline Visualization with Representative Stocks
Simple, robust version using Plotly Python API
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import create_engine

print("=" * 80)
print("GENERATING SECTOR TIMELINE VISUALIZATION (Plotly Python)")
print("=" * 80)

SEC_DB_URL = "postgresql://investigator:investigator@dataserver1.singh.local:5432/sec_database"
engine = create_engine(SEC_DB_URL)

# Fetch sector medians
print("\n📊 Fetching data...")
sector_medians = pd.read_sql(
    """
    SELECT
        group_name as sector,
        fiscal_year,
        pe_multiple as pe,
        ps_multiple as ps,
        pb_multiple as pb
    FROM sector_multiples_history
    WHERE group_type = 'sector'
    ORDER BY sector, fiscal_year
""",
    engine,
)

print(f"✓ Found {len(sector_medians)} sector-year records")

# Fetch representative stocks for 2024
stocks = pd.read_sql(
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
            ROW_NUMBER() OVER (PARTITION BY s."Sector" ORDER BY s.mktcap DESC) as rank_in_sector
        FROM symbol s
        INNER JOIN sector_list sl ON s."Sector" = sl.group_name
        WHERE s.mktcap > 0
            AND s."Sector" IS NOT NULL
    )
    SELECT sm.symbol, sm.sector, sm.market_cap,
           sm.pe_ratio, sm.ps_ratio, sm.pb_ratio
    FROM symbol_metrics sm
    WHERE sm.rank_in_sector <= 10
        AND (sm.pe_ratio > 0 OR sm.ps_ratio > 0 OR sm.pb_ratio > 0)
    ORDER BY sm.sector, sm.rank_in_sector
""",
    engine,
)

print(f"✓ Found {len(stocks)} representative stocks")

# Sector colors
sector_colors = {
    "Technology": "blue",
    "Healthcare": "purple",
    "Financials": "green",
    "Consumer Discretionary": "orange",
    "Communication Services": "red",
    "Industrials": "yellow",
    "Consumer Staples": "gray",
    "Energy": "purple",
    "Utilities": "lightblue",
    "Real Estate": "pink",
}

# Create figure with subplots
fig = make_subplots(
    rows=1,
    cols=3,
    subplot_titles=("P/E Multiple", "P/S Multiple", "P/B Multiple"),
    horizontal_spacing=0.1,
)

# Add traces for each sector
metrics = ["pe", "ps", "pb"]
metric_names = ["P/E", "P/S", "P/B"]

for sector in sector_medians["sector"].unique():
    sector_data = sector_medians[sector_medians["sector"] == sector].sort_values("fiscal_year")
    color = sector_colors.get(sector, "gray")

    for i, metric in enumerate(metrics):
        # Add median line
        fig.add_trace(
            go.Scatter(
                x=sector_data["fiscal_year"],
                y=sector_data[metric],
                mode="lines+markers",
                name=sector,
                line=dict(color=color, width=2),
                marker=dict(size=6),
                legendgroup=sector,
                hovertemplate=f"<b>{sector}</b><br>Year: %{{x}}<br>{metric_names[i]}: %{{y:.2f}}x<extra></extra>",
            ),
            row=1,
            col=i + 1,
        )

# Add stock bubbles for 2024
for sector in stocks["sector"].unique():
    sector_stocks = stocks[stocks["sector"] == sector]
    color = sector_colors.get(sector, "gray")

    for _, stock in sector_stocks.iterrows():
        # Size based on market cap (log scale)
        size = max(10, min(30, 10 + 20 * (stock["market_cap"] / 3e12)))

        for i, metric in enumerate(metrics):
            stock_metric = metric + "_ratio"
            if pd.notna(stock[stock_metric]) and stock[stock_metric] > 0:
                fig.add_trace(
                    go.Scatter(
                        x=[2024],
                        y=[stock[stock_metric]],
                        mode="markers",
                        name=f"{sector} stocks",
                        marker=dict(
                            size=size,
                            color=color,
                            opacity=0.5,
                            line=dict(color=color, width=1),
                        ),
                        legendgroup=sector,
                        showlegend=False,
                        hovertemplate=f"<b>{stock['symbol']}</b><br>{sector}<br>Year: 2024<br>{metric_names[i]}: %{{y:.2f}}x<br>MCap: ${{stock['market_cap']/1e9:.0f}}B<extra></extra>",
                    ),
                    row=1,
                    col=i + 1,
                )

# Update layout
fig.update_xaxes(title_text="Fiscal Year")
fig.update_yaxes(title_text="Multiple")

fig.update_layout(
    title_text="Sector Multiples Historical Timeline with Representative Stocks (2016-2024)",
    title_x=0.5,
    height=600,
    hovermode="closest",
    legend=dict(orientation="h", y=-0.15, xanchor="center"),
)

# Save to HTML
output_path = Path("docs/assets/visualizations/sector_timeline_plotly.html")
fig.write_html(output_path)

print(f"\n✅ Saved to: {output_path}")
print("✅ Opening in browser...")

subprocess.run(["open", str(output_path)])

print("\n" + "=" * 80)
print("✅ COMPLETE!")
print("=" * 80)
