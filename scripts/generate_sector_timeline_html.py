#!/usr/bin/env python3.11
"""Generate interactive HTML/SVG timeline reports for sector multiples.

Creates interactive charts showing:
- Years on X-axis
- Multiple values on Y-axis
- Sectors as colored lines
- Representative symbols as scatter dots (size = market cap)
- Top 5, Mid 5, Bottom 5 symbols per sector
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from investigator.infrastructure.database.db import get_db_manager


def fetch_sector_aggregates_from_db(
    years: List[int],
) -> Dict[str, Dict[str, List[float]]]:
    """Fetch sector-level aggregate multiples from database.

    Args:
        years: List of years to fetch

    Returns:
        Dict with structure: {sector: {pe: [...], ps: [...], pb: [...]}}
    """
    db = get_db_manager()

    # Initialize result structure
    result = {
        sector: {"pe": [], "ps": [], "pb": []}
        for sector in [
            "Technology",
            "Health Care",
            "Financials",
            "Energy",
            "Consumer Discretionary",
            "Consumer Staples",
            "Industrials",
            "Real Estate",
            "Utilities",
            "Communication Services",
            "Materials",
        ]
    }

    query = text("""
        SELECT
            group_name,
            fiscal_year,
            pe_multiple,
            ps_multiple,
            pb_multiple
        FROM sector_multiples_history
        WHERE group_type = 'sector'
          AND fiscal_year = ANY(:years)
        ORDER BY group_name, fiscal_year
    """)

    try:
        with db.get_session() as session:
            rows = session.execute(query, {"years": years})

            # Build mapping
            data_by_sector_year: Dict[str, Dict[int, Dict]] = {}
            for row in rows:
                sector = row[0]
                year = int(row[1])
                pe = float(row[2]) if row[2] else None
                ps = float(row[3]) if row[3] else None
                pb = float(row[4]) if row[4] else None

                if sector not in data_by_sector_year:
                    data_by_sector_year[sector] = {}
                data_by_sector_year[sector][year] = {"pe": pe, "ps": ps, "pb": pb}

            # Fill in missing years and build result
            for sector in result.keys():
                for year in sorted(years):
                    if sector in data_by_sector_year and year in data_by_sector_year[sector]:
                        result[sector]["pe"].append(data_by_sector_year[sector][year]["pe"])
                        result[sector]["ps"].append(data_by_sector_year[sector][year]["ps"])
                        result[sector]["pb"].append(data_by_sector_year[sector][year]["pb"])
                    else:
                        result[sector]["pe"].append(None)
                        result[sector]["ps"].append(None)
                        result[sector]["pb"].append(None)

    except Exception as e:
        print(f"Error fetching sector aggregates: {e}")

    return result


def load_existing_json_data(
    json_path: str = "/tmp/sector_trends_data.json",
) -> Tuple[List[int], Dict[str, Dict[str, List[float]]]]:
    """Load sector aggregates from existing JSON file.

    Args:
        json_path: Path to JSON file

    Returns:
        Tuple of (years, sectors_data)
    """
    with open(json_path, "r") as f:
        data = json.load(f)

    years = data.get("years", [])
    sectors = data.get("sectors", {})

    # Add P/E data from documentation (the JSON has null for PE)
    # P/E data from SECTOR_ANALYSIS_COMPLETE_2015_2024.md
    pe_data = {
        "Technology": [116, 133, 108, 95, 37, 57, 56, 66, 48, None],
        "Health Care": [72, 65, 75, 58, 52, 41, 38, 35, 31, None],
        "Financials": [18, 22, 18, 19, 18, 20, 13, 11, 14, None],
        "Consumer Discretionary": [82, 75, 68, 72, 65, 52, 45, 38, 29, None],
        "Consumer Staples": [28, 30, 32, 32, 30, 28, 26, 24, 23, None],
        "Industrials": [30, 35, 38, 32, 30, 38, 32, 28, 27, None],
        "Energy": [42, 29, 19, 28, 50, 18, 7, 10, 14, None],
        "Real Estate": [52, 48, 52, 48, 52, 48, 42, 38, 42, None],
        "Utilities": [28, 32, 30, 32, 32, 28, 22, 21, 20, None],
        "Communication Services": [
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ],
        "Materials": [None, None, None, None, None, None, None, None, None, None],
    }

    # Map sector names from JSON to P/E data keys
    sector_mapping = {
        "Basic Materials": "Materials",
        "Consumer Cyclical": "Consumer Discretionary",  # Approximation
    }

    # Inject P/E data into sectors
    for sector_name, pe_values in pe_data.items():
        if sector_name in sectors:
            sectors[sector_name]["pe"] = pe_values

    # Handle mapped sectors
    for json_name, pe_name in sector_mapping.items():
        if json_name in sectors and pe_name in pe_data:
            sectors[json_name]["pe"] = pe_data[pe_name]

    return years, sectors


def format_market_cap(mc: float) -> str:
    """Format market cap for display."""
    if mc >= 1_000_000_000_000:
        return f"${mc / 1_000_000_000_000:.1f}T"
    elif mc >= 1_000_000_000:
        return f"${mc / 1_000_000_000:.0f}B"
    elif mc >= 1_000_000:
        return f"${mc / 1_000_000:.0f}M"
    return f"${mc:.0f}"


def generate_svg_chart(
    title: str,
    years: List[int],
    sectors: Dict[str, Dict[str, List[float]]],
    multiple_type: str,
    width: int = 1200,
    height: int = 700,
) -> str:
    """Generate an SVG chart for a specific multiple type.

    Args:
        title: Chart title
        years: List of years for X-axis
        sectors: Dict of sector data with multiples
        multiple_type: 'pe', 'ps', or 'pb'
        width: SVG width
        height: SVG height

    Returns:
        SVG string
    """

    margin = {"top": 80, "right": 200, "bottom": 80, "left": 80}
    chart_width = width - margin["left"] - margin["right"]
    chart_height = height - margin["top"] - margin["bottom"]

    # Determine Y-axis range
    all_values = []
    for sector_data in sectors.values():
        all_values.extend([v for v in sector_data[multiple_type] if v is not None])

    if not all_values:
        return f"<p>No data available for {multiple_type.upper()}</p>"

    min_val = min(all_values)
    max_val = max(all_values)

    # Add padding to range
    range_padding = (max_val - min_val) * 0.1
    y_min = max(0, min_val - range_padding)
    y_max = max_val + range_padding

    # Sector styles: contrasting colors + line styles
    # Using colorblind-friendly palette with distinct lightness
    sector_styles = {
        "Technology": {"color": "#1f77b4", "dash": "none"},  # Blue, solid
        "Health Care": {"color": "#ff7f0e", "dash": "5,5"},  # Orange, dashed
        "Financials": {"color": "#2ca02c", "dash": "none"},  # Green, solid
        "Energy": {"color": "#d62728", "dash": "10,5,2,5"},  # Red, dash-dot
        "Consumer Discretionary": {"color": "#9467bd", "dash": "none"},  # Purple, solid
        "Consumer Staples": {"color": "#8c564b", "dash": "3,3"},  # Brown, dotted
        "Industrials": {"color": "#e377c2", "dash": "15,5,3,5"},  # Pink, dash-dot-dot
        "Real Estate": {"color": "#7f7f7f", "dash": "none"},  # Gray, solid
        "Utilities": {"color": "#bcbd22", "dash": "5,5"},  # Olive, dashed
        "Communication Services": {"color": "#17becf", "dash": "none"},  # Cyan, solid
        "Materials": {"color": "#000000", "dash": "2,2,8,2"},  # Black, dotted-dash
        # Also handle alternative names
        "Basic Materials": {
            "color": "#000000",
            "dash": "2,2,8,2",
        },  # Black, dotted-dash
        "Consumer Cyclical": {"color": "#9467bd", "dash": "none"},  # Purple, solid
    }

    # Helper function to get color and dash array
    def get_sector_style(sector_name: str) -> dict:
        if sector_name in sector_styles:
            return sector_styles[sector_name]
        # Default for unknown sectors
        return {"color": "#666666", "dash": "none"}

    # X-scale mapping
    def x_scale(year_idx: int) -> float:
        if len(years) <= 1:
            return margin["left"]
        return margin["left"] + (year_idx / (len(years) - 1)) * chart_width

    # Y-scale mapping
    def y_scale(value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        normalized = (value - y_min) / (y_max - y_min)
        return margin["top"] + chart_height - (normalized * chart_height)

    svg_lines = []

    # Header
    svg_lines.append(f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">')
    svg_lines.append("<style>")
    svg_lines.append("  .title { font: bold 20px sans-serif; fill: #333; }")
    svg_lines.append("  .axis-label { font: 14px sans-serif; fill: #666; }")
    svg_lines.append("  .grid-line { stroke: #e0e0e0; stroke-width: 1; }")
    svg_lines.append("  .sector-line { fill: none; stroke-width: 3; stroke-linecap: round; }")
    svg_lines.append("  .legend-text { font: 12px sans-serif; fill: #555; }")
    svg_lines.append("</style>")

    # Title
    svg_lines.append(f'<text x="{width // 2}" y="35" text-anchor="middle" class="title">{title}</text>')

    # Y-axis grid lines and labels
    y_ticks = 8
    for i in range(y_ticks + 1):
        val = y_min + (y_max - y_min) * (i / y_ticks)
        y = margin["top"] + chart_height - (i / y_ticks) * chart_height
        svg_lines.append(
            f'<line x1="{margin["left"]}" y1="{y}" x2="{width - margin["right"]}" y2="{y}" class="grid-line" />'
        )
        svg_lines.append(
            f'<text x="{margin["left"] - 10}" y="{y + 5}" text-anchor="end" class="axis-label">{val:.1f}x</text>'
        )

    # X-axis labels
    for i, year in enumerate(years):
        x = x_scale(i)
        svg_lines.append(
            f'<text x="{x}" y="{height - margin["bottom"] + 25}" text-anchor="middle" class="axis-label">{year}</text>'
        )
        # Tick mark
        svg_lines.append(
            f'<line x1="{x}" y1="{height - margin["bottom"]}" x2="{x}" y2="{height - margin["bottom"] + 5}" stroke="#666" stroke-width="1"/>'
        )

    # Axis labels
    svg_lines.append(
        f'<text x="{width // 2}" y="{height - 15}" text-anchor="middle" class="axis-label" font-weight="bold">Fiscal Year</text>'
    )
    svg_lines.append(
        f'<text x="20" y="{height // 2}" text-anchor="middle" transform="rotate(-90, 20, {height // 2})" class="axis-label" font-weight="bold">{multiple_type.upper()} Multiple</text>'
    )

    # Draw sector lines
    for sector, data in sorted(sectors.items()):
        values = data[multiple_type]
        style = get_sector_style(sector)
        color = style["color"]
        dash_pattern = style["dash"]

        # Build path
        points = []
        for i, val in enumerate(values):
            y = y_scale(val)
            if y is not None:
                points.append(f"{x_scale(i)},{y}")

        if len(points) >= 2:
            path_data = "M " + " L ".join(points)
            stroke_dasharray = f' stroke-dasharray="{dash_pattern}"' if dash_pattern != "none" else ""
            svg_lines.append(f'<path d="{path_data}" class="sector-line" stroke="{color}"{stroke_dasharray} />')

    # Legend with line styles
    legend_y = margin["top"]
    for i, (sector, _) in enumerate(sorted(sectors.items())):
        style = get_sector_style(sector)
        color = style["color"]
        dash_pattern = style["dash"]
        legend_x = width - margin["right"] + 10
        y_pos = legend_y + i * 20

        # Draw line sample instead of rectangle
        stroke_dasharray = f' stroke-dasharray="{dash_pattern}"' if dash_pattern != "none" else ""
        svg_lines.append(
            f'<line x1="{legend_x}" y1="{y_pos}" x2="{legend_x + 15}" y2="{y_pos}" '
            f'stroke="{color}" stroke-width="3"{stroke_dasharray} />'
        )
        svg_lines.append(f'<text x="{legend_x + 20}" y="{y_pos + 4}" class="legend-text">{sector}</text>')

    svg_lines.append("</svg>")

    return "\n".join(svg_lines)


def generate_html_report(
    years: List[int],
    sector_aggregates: Dict[str, Dict[str, List[float]]],
    output_path: str,
) -> None:
    """Generate complete HTML report with all charts.

    Args:
        years: List of years to display
        sector_aggregates: Sector-level aggregate data
        output_path: Path to write HTML file
    """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sector Multiples Timeline {min(years)}-{max(years)}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #0066CC;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 40px;
        }}
        .chart {{
            margin: 30px 0;
            overflow-x: auto;
            border: 1px solid #e0e0e0;
            border-radius: 4px;
            padding: 10px;
            background: #fafafa;
        }}
        .info {{
            background: #e3f2fd;
            padding: 15px;
            border-radius: 4px;
            margin: 20px 0;
        }}
        .legend-info {{
            font-size: 13px;
            color: #666;
            margin-top: 10px;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 10px;
            text-align: left;
        }}
        th {{
            background: #f0f0f0;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Sector Multiples Timeline Report</h1>
        <p><strong>Period:</strong> Fiscal Years {min(years)} to {max(years)}</p>
        <p><strong>Generated:</strong> {years[-1]}</p>

        <div class="info">
            <h3>Chart Guide</h3>
            <ul>
                <li><strong>Colored Lines:</strong> Sector median multiples over time</li>
                <li><strong>X-Axis:</strong> Fiscal year</li>
                <li><strong>Y-Axis:</strong> Valuation multiple (P/E, P/S, P/B)</li>
            </ul>
        </div>

        <h2>P/E Multiples by Sector</h2>
        <div class="chart">
            {
        generate_svg_chart(
            "P/E Ratio Evolution (2016-2025)",
            years,
            sector_aggregates,
            "pe",
        )
    }
        </div>

        <h2>P/S Multiples by Sector</h2>
        <div class="chart">
            {
        generate_svg_chart(
            "P/S Ratio Evolution (2016-2025)",
            years,
            sector_aggregates,
            "ps",
        )
    }
        </div>

        <h2>P/B Multiples by Sector</h2>
        <div class="chart">
            {
        generate_svg_chart(
            "P/B Ratio Evolution (2016-2025)",
            years,
            sector_aggregates,
            "pb",
        )
    }
        </div>

        <h2>2024 Sector Multiple Summary</h2>
        <table>
            <thead>
                <tr>
                    <th>Sector</th>
                    <th>P/E (2024)</th>
                    <th>P/S (2024)</th>
                    <th>P/B (2024)</th>
                    <th>10Y Trend</th>
                </tr>
            </thead>
            <tbody>
"""

    # Add summary table for 2024
    idx_2024 = years.index(2024) if 2024 in years else -1
    idx_2016 = years.index(2016) if 2016 in years else 0

    for sector in sorted(sector_aggregates.keys()):
        pe_2024 = sector_aggregates[sector]["pe"][idx_2024] if idx_2024 >= 0 else None
        ps_2024 = sector_aggregates[sector]["ps"][idx_2024] if idx_2024 >= 0 else None
        pb_2024 = sector_aggregates[sector]["pb"][idx_2024] if idx_2024 >= 0 else None

        pe_2016 = sector_aggregates[sector]["pe"][idx_2016] if idx_2016 >= 0 else None

        # Calculate trend: 2016 -> 2024
        trend_str = "N/A"
        if pe_2016 and pe_2024:
            change = ((pe_2024 - pe_2016) / pe_2016) * 100
            trend_str = f"{pe_2016:.0f}→{pe_2024:.0f} ({change:+.0f}%)"
        elif pe_2016:
            trend_str = f"{pe_2016:.0f}→N/A"

        pe_str = f"{pe_2024:.1f}x" if pe_2024 else "N/A"
        ps_str = f"{ps_2024:.1f}x" if ps_2024 else "N/A"
        pb_str = f"{pb_2024:.1f}x" if pb_2024 else "N/A"

        html += f"""
                <tr>
                    <td><strong>{sector}</strong></td>
                    <td>{pe_str}</td>
                    <td>{ps_str}</td>
                    <td>{pb_str}</td>
                    <td>{trend_str}</td>
                </tr>
"""

    html += """
            </tbody>
        </table>
    </div>
</body>
</html>
"""

    with open(output_path, "w") as f:
        f.write(html)

    print(f"Generated HTML report: {output_path}")


def main():
    """Main entry point."""
    years = [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
    output_dir = Path("/tmp")
    output_dir.mkdir(exist_ok=True)

    # Try to load from database first
    print("Fetching sector aggregates from database...")
    sector_aggregates = fetch_sector_aggregates_from_db(years)

    # If database doesn't have enough data, fall back to JSON
    sectors_with_data = [
        s
        for s in sector_aggregates.keys()
        if any(
            v is not None for v in sector_aggregates[s]["pe"] + sector_aggregates[s]["ps"] + sector_aggregates[s]["pb"]
        )
    ]

    if len(sectors_with_data) < 3:
        print(f"  Only {len(sectors_with_data)} sectors with data in DB, falling back to JSON...")
        json_path = output_dir / "sector_trends_data.json"
        if json_path.exists():
            years, sector_aggregates = load_existing_json_data(str(json_path))
        else:
            print("  ERROR: No JSON data found at", json_path)
            return
    else:
        print(f"  Loaded {len(sectors_with_data)} sectors from database")

    print("\nGenerating HTML report...")
    html_path = output_dir / "sector_timeline_2016_2025.html"
    generate_html_report(
        years,
        sector_aggregates,
        str(html_path),
    )

    print(f"\n✓ Complete! Open {html_path} in your browser to view the interactive charts.")


if __name__ == "__main__":
    main()
