#!/usr/bin/env python3
"""Generate sector multiples timeline reports from existing data.

This script reads the sector_trends_data.json file and generates
individual timeline reports for each sector showing P/S and P/B
multiples from 2015-2024.
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple


def load_sector_data(
    filepath: str = "/Users/vijaysingh/code/victor-invest/docs/assets/sector_trends_data.json",
) -> Dict:
    """Load sector multiples data from JSON file."""
    with open(filepath, "r") as f:
        data = json.load(f)
    return data


def calculate_change(start: float, end: float) -> Tuple[float, str]:
    """Calculate percentage change and return status."""
    if start is None or end is None:
        return 0.0, "N/A"
    if start == 0:
        return 0.0, "N/A"
    change_pct = ((end - start) / start) * 100
    status = (
        "SWELLING" if change_pct > 5 else "SHRINKING" if change_pct < -5 else "STABLE"
    )
    return change_pct, status


def calculate_volatility(values: List[float]) -> float:
    """Calculate the max swing (volatility) as percentage."""
    valid_values = [v for v in values if v is not None and v > 0]
    if len(valid_values) < 2:
        return 0.0
    min_val = min(valid_values)
    max_val = max(valid_values)
    if min_val == 0:
        return 0.0
    swing_pct = ((max_val - min_val) / min_val) * 100
    return swing_pct


def generate_sector_report(
    sector_name: str, sector_data: Dict, years: List[int]
) -> str:
    """Generate a formatted report for a single sector."""

    ps_values = sector_data.get("ps", [])
    pb_values = sector_data.get("pb", [])
    pe_values = sector_data.get("pe", [])

    # Zip data with years
    yearly_data = list(zip(years, ps_values, pb_values, pe_values))

    report_lines = [
        f"# {sector_name} Sector Multiples Timeline (2015-2024)",
        "",
        "## Timeline Overview",
        "",
        "This report tracks valuation multiples (P/S, P/B) for the "
        f"{sector_name} sector from fiscal year 2016 to 2025.",
        "",
    ]

    # Build the table
    report_lines.extend(
        [
            "## Multiples by Year",
            "",
            "| Year | P/S Multiple | P/B Multiple | P/E Multiple |",
            "|------|--------------|--------------|--------------|",
        ]
    )

    for year, ps, pb, pe in yearly_data:
        ps_str = f"{ps:.2f}x" if ps is not None else "N/A"
        pb_str = f"{pb:.2f}x" if pb is not None else "N/A"
        pe_str = f"{pe:.2f}x" if pe is not None else "N/A"
        report_lines.append(f"| {year} | {ps_str} | {pb_str} | {pe_str} |")

    report_lines.extend(["", "## Trend Analysis", ""])

    # P/S Analysis
    ps_start = ps_values[0] if ps_values and ps_values[0] is not None else None
    ps_end = ps_values[-1] if ps_values and ps_values[-1] is not None else None
    ps_change, ps_status = calculate_change(ps_start, ps_end)
    ps_volatility = calculate_volatility(ps_values)

    if ps_start and ps_end:
        report_lines.extend(
            [
                "### P/S Multiple Trend",
                "",
                f"- **2016**: {ps_start:.2f}x",
                f"- **2025**: {ps_end:.2f}x",
                f"- **Change**: {ps_change:+.1f}% ({ps_status})",
                f"- **Volatility**: {ps_volatility:.1f}% max swing",
                "",
            ]
        )
    else:
        report_lines.extend(
            [
                "### P/S Multiple Trend",
                "",
                "Insufficient data for P/S trend analysis.",
                "",
            ]
        )

    # P/B Analysis
    pb_start = pb_values[0] if pb_values and pb_values[0] is not None else None
    pb_end = pb_values[-1] if pb_values and pb_values[-1] is not None else None
    pb_change, pb_status = calculate_change(pb_start, pb_end)
    pb_volatility = calculate_volatility(pb_values)

    if pb_start and pb_end:
        report_lines.extend(
            [
                "### P/B Multiple Trend",
                "",
                f"- **2016**: {pb_start:.2f}x",
                f"- **2025**: {pb_end:.2f}x",
                f"- **Change**: {pb_change:+.1f}% ({pb_status})",
                f"- **Volatility**: {pb_volatility:.1f}% max swing",
                "",
            ]
        )
    else:
        report_lines.extend(
            [
                "### P/B Multiple Trend",
                "",
                "Insufficient data for P/B trend analysis.",
                "",
            ]
        )

    # Key Insights
    report_lines.extend(
        [
            "## Key Insights",
            "",
        ]
    )

    if ps_volatility > 50:
        report_lines.append(
            f"- **High Volatility**: P/S multiple experienced extreme volatility ({ps_volatility:.1f}% swing)"
        )
    elif ps_volatility > 30:
        report_lines.append(
            f"- **Moderate Volatility**: P/S multiple showed significant swings ({ps_volatility:.1f}% swing)"
        )
    else:
        report_lines.append(
            f"- **Stable**: P/S multiple remained relatively stable ({ps_volatility:.1f}% swing)"
        )

    if ps_status == "SWELLING":
        report_lines.append(
            "- **Expanding**: Sector multiples expanded over the period, suggesting increasing market sentiment"
        )
    elif ps_status == "SHRINKING":
        report_lines.append(
            "- **Contracting**: Sector multiples contracted over the period, suggesting normalization or declining sentiment"
        )
    else:
        report_lines.append(
            "- **Stable**: Sector multiples remained relatively flat over the period"
        )

    report_lines.append("")
    return "\n".join(report_lines)


def main():
    """Main entry point."""
    # Load data
    data = load_sector_data()
    years = data.get("years", [])
    sectors = data.get("sectors", {})

    # Output directory
    output_dir = Path("/tmp")
    output_dir.mkdir(exist_ok=True)

    # Generate report for each sector
    summaries = []

    for sector_name, sector_data in sectors.items():
        # Skip certain sectors
        if sector_name in ["Unknown", "Miscellaneous"]:
            continue

        # Generate report
        report = generate_sector_report(sector_name, sector_data, years)

        # Save to file
        safe_name = sector_name.replace(" ", "_").replace("/", "_")
        output_path = output_dir / f"sector_timeline_{safe_name}.txt"
        with open(output_path, "w") as f:
            f.write(report)

        print(f"Generated: {output_path}")

        # Collect summary data
        ps_values = sector_data.get("ps", [])

        ps_start = ps_values[0] if ps_values else None
        ps_end = ps_values[-1] if ps_values else None
        ps_change, ps_status = calculate_change(ps_start, ps_end)
        ps_volatility = calculate_volatility(ps_values)

        summaries.append(
            {
                "sector": sector_name,
                "ps_2016": ps_start,
                "ps_2024": ps_values[-2]
                if len(ps_values) > 1
                else None,  # 2024 is second to last
                "ps_2025": ps_end,
                "ps_change": ps_change,
                "ps_status": ps_status,
                "ps_volatility": ps_volatility,
            }
        )

    # Generate overall summary
    generate_summary_report(summaries, output_dir)

    print(f"\nAll reports saved to {output_dir}")


def generate_summary_report(summaries: List[Dict], output_dir: Path):
    """Generate an overall summary report."""

    report_lines = [
        "# Sector Multiples Timeline Summary (2016-2025)",
        "",
        "## Overview",
        "",
        "This summary aggregates the valuation multiple trends across all major sectors",
        "from fiscal year 2016 to 2025.",
        "",
        "## P/E Trends by Sector (2016 → 2024)",
        "",
        "Note: P/E data is not available in the current dataset.",
        "",
        "## P/S Trends by Sector (2016 → 2024)",
        "",
        "| Sector | 2016 P/S | 2024 P/S | 2025 P/S | Change | Status | Volatility |",
        "|--------|----------|----------|----------|--------|--------|------------|",
    ]

    for s in sorted(summaries, key=lambda x: x.get("ps_2024") or 0, reverse=True):
        sector = s["sector"]
        ps_2016 = f"{s['ps_2016']:.2f}x" if s["ps_2016"] else "N/A"
        ps_2024 = f"{s['ps_2024']:.2f}x" if s["ps_2024"] else "N/A"
        ps_2025 = f"{s['ps_2025']:.2f}x" if s["ps_2025"] else "N/A"
        change = f"{s['ps_change']:+.1f}%" if s["ps_change"] else "N/A"
        status = s.get("ps_status", "N/A")
        vol = f"{s['ps_volatility']:.1f}%" if s["ps_volatility"] else "N/A"
        report_lines.append(
            f"| {sector} | {ps_2016} | {ps_2024} | {ps_2025} | {change} | {status} | {vol} |"
        )

    # Identify trends
    expanding = [s["sector"] for s in summaries if s.get("ps_status") == "SWELLING"]
    contracting = [s["sector"] for s in summaries if s.get("ps_status") == "SHRINKING"]
    stable = [s["sector"] for s in summaries if s.get("ps_status") == "STABLE"]

    high_volatility = [s["sector"] for s in summaries if s.get("ps_volatility", 0) > 50]
    top_ps = sorted(summaries, key=lambda x: x.get("ps_2024") or 0, reverse=True)[:3]

    report_lines.extend(
        [
            "",
            "## Sector Classification",
            "",
            "### Expanding Sectors (Swelling)",
            "",
        ]
    )

    if expanding:
        for s in expanding:
            report_lines.append(f"- **{s}**: Multiples expanded over the period")
    else:
        report_lines.append("- None (most sectors contracted or stabilized)")

    report_lines.extend(
        [
            "",
            "### Contracting Sectors (Shrinking)",
            "",
        ]
    )

    if contracting:
        for s in contracting:
            report_lines.append(f"- **{s}**: Multiples contracted over the period")
    else:
        report_lines.append("- None")

    report_lines.extend(
        [
            "",
            "### Stable Sectors",
            "",
        ]
    )

    if stable:
        for s in stable:
            report_lines.append(f"- **{s}**: Multiples remained relatively stable")
    else:
        report_lines.append("- None")

    report_lines.extend(
        [
            "",
            "## Top 3 Sectors by P/S Multiple (2024)",
            "",
        ]
    )

    for i, s in enumerate(top_ps, 1):
        report_lines.append(f"{i}. **{s['sector']}**: {s['ps_2024']:.2f}x")

    report_lines.extend(
        [
            "",
            "## Sectors with Extreme Volatility (>50% swing)",
            "",
        ]
    )

    if high_volatility:
        for s in high_volatility:
            vol = next(x["ps_volatility"] for x in summaries if x["sector"] == s)
            report_lines.append(f"- **{s}**: {vol:.1f}% max swing")
    else:
        report_lines.append("- None (all sectors showed moderate or low volatility)")

    report_lines.extend(
        [
            "",
            "## Key Takeaways",
            "",
        ]
    )

    # Determine overall market sentiment
    expanding_count = len(expanding)
    contracting_count = len(contracting)

    if contracting_count > expanding_count * 2:
        report_lines.append(
            "- **Market-Wide Contraction**: Most sectors experienced valuation compression, suggesting a broad market re-rating"
        )
    elif expanding_count > contracting_count * 2:
        report_lines.append(
            "- **Market-Wide Expansion**: Most sectors experienced valuation expansion, suggesting broad bullish sentiment"
        )
    else:
        report_lines.append(
            "- **Mixed Market**: Sectors showed divergent trends, suggesting stock-picking environment"
        )

    if high_volatility:
        report_lines.append(
            f"- **High Volatility Environment**: {len(high_volatility)} sectors experienced extreme swings, indicating macro uncertainty"
        )
    else:
        report_lines.append(
            "- **Moderate Volatility**: Most sectors showed reasonable volatility, indicating stable market conditions"
        )

    report_lines.append("")

    # Write summary report
    summary_path = output_dir / "sector_timeline_summary.txt"
    with open(summary_path, "w") as f:
        f.write("\n".join(report_lines))

    print(f"\nSummary report saved to: {summary_path}")


if __name__ == "__main__":
    main()
