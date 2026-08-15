# Copyright 2025 Vijaykumar Singh <singhvjd@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Render an :class:`AnalystReport` to institutional-style markdown."""

from __future__ import annotations


from victor_invest.reporting.schema import AnalystReport


def _money(value: float | None) -> str:
    return f"${value:,.2f}" if isinstance(value, (int, float)) else "—"


def _pct(value: float | None) -> str:
    return f"{value:+.1f}%" if isinstance(value, (int, float)) else "—"


def _num(value: float | None, digits: int = 2) -> str:
    return f"{value:,.{digits}f}" if isinstance(value, (int, float)) else "—"


def render_markdown(report: AnalystReport) -> str:
    r = report
    lines: list[str] = []
    add = lines.append

    add(f"# {r.symbol} — Equity Research Note")
    if r.as_of:
        add(f"_As of {r.as_of}_")
    add("")

    # Rating snapshot
    rb = r.rating
    add("## Rating")
    add("")
    add("| Metric | Value |")
    add("| --- | --- |")
    add(f"| Recommendation | **{rb.action}** ({rb.confidence}) |")
    add(f"| Composite score | {_num(rb.composite_score, 1)}/100 |")
    add(f"| Current price | {_money(rb.current_price)} |")
    add(f"| Price target | {_money(rb.price_target)} |")
    add(f"| Upside to target | {_pct(rb.upside_pct)} |")
    add("")
    add(f"_Methodology: {rb.methodology}_")
    add("")

    if r.thesis:
        add("## Investment Thesis")
        add("")
        add(r.thesis)
        add("")

    # Valuation
    v = r.valuation
    add("## Valuation")
    add("")
    add("| Model | Fair value | Upside | Weight |")
    add("| --- | --- | --- | --- |")
    for m in v.models:
        weight = f"{m.weight:.0f}%" if isinstance(m.weight, (int, float)) else "—"
        add(f"| {m.model.upper()} | {_money(m.fair_value)} | {_pct(m.upside_pct)} | {weight} |")
    add(f"| **Blended** | **{_money(v.blended_fair_value)}** | **{_pct(v.consensus_upside_pct)}** | — |")
    add("")
    add(
        f"- Fair-value range: {_money(v.fair_value_low)} – {_money(v.fair_value_high)}  "
        f"\n- Margin of safety: {_pct(v.margin_of_safety_pct)}  "
        f"\n- Tier: {v.tier_classification or '—'}  "
        f"\n- Model agreement: {_num(v.model_agreement_score, 1)}"
    )
    if v.methodology:
        meth = v.methodology
        bits = []
        if meth.get("wacc") is not None:
            bits.append(f"WACC {meth['wacc'] * 100:.1f}%" if meth["wacc"] < 1 else f"WACC {meth['wacc']:.1f}%")
        if meth.get("terminal_growth_rate") is not None:
            tg = meth["terminal_growth_rate"]
            bits.append(f"terminal growth {tg * 100:.1f}%" if tg < 1 else f"terminal growth {tg:.1f}%")
        if meth.get("target_pe") is not None:
            bits.append(f"target P/E {meth['target_pe']:.1f}")
        if meth.get("target_ps") is not None:
            bits.append(f"target P/S {meth['target_ps']:.1f}")
        if meth.get("target_ev_ebitda") is not None:
            bits.append(f"target EV/EBITDA {meth['target_ev_ebitda']:.1f}")
        if bits:
            add(f"- Key assumptions: {', '.join(bits)}")
    add("")

    # Scenarios
    sc = r.scenarios
    if sc.scenarios:
        add("## Scenario Analysis")
        add("")
        add("| Scenario | Probability | Price target | Return |")
        add("| --- | --- | --- | --- |")
        for s in sc.scenarios:
            add(f"| {s.name} | {s.probability:.0%} | {_money(s.price_target)} | {_pct(s.return_pct)} |")
        add(
            f"| **Prob-weighted** | 100% | **{_money(sc.probability_weighted_target)}** "
            f"| **{_pct(sc.probability_weighted_return_pct)}** |"
        )
        add("")

    # Technical setup
    t = r.technical
    add("## Technical Setup")
    add("")
    add(
        f"- Bias: {t.overall_bias or '—'} | Strategic trend: {t.strategic_trend or '—'} "
        f"| Tactical: {t.tactical_signal or '—'}"
    )
    add("")
    add("| Indicator | Value | Indicator | Value |")
    add("| --- | --- | --- | --- |")
    add(f"| RSI(14) | {_num(t.rsi_14, 1)} | MACD | {_num(t.macd)} |")
    add(f"| MACD signal | {_num(t.macd_signal)} | MACD hist | {_num(t.macd_histogram)} |")
    add(f"| Stoch %K | {_num(t.stoch_k, 1)} | Stoch %D | {_num(t.stoch_d, 1)} |")
    add(f"| SMA 20 | {_money(t.sma_20)} | SMA 50 | {_money(t.sma_50)} |")
    add(f"| SMA 200 | {_money(t.sma_200)} | ATR(14) | {_num(t.atr_14)} |")
    add(f"| Bollinger upper | {_money(t.bb_upper)} | Bollinger lower | {_money(t.bb_lower)} |")
    add(f"| VWAP | {_money(t.vwap)} | OBV | {_num(t.obv, 0)} |")
    add("")
    add("**Key levels**")
    add("")
    add(f"- Support: {_money(t.support_1)} | Resistance: {_money(t.resistance_1)} | Pivot: {_money(t.pivot_point)}")
    add(f"- 52-week range: {_money(t.low_52w)} – {_money(t.high_52w)}")
    add(f"- Fibonacci: 38.2% {_money(t.fib_38_2)} | 50% {_money(t.fib_50_0)} | 61.8% {_money(t.fib_61_8)}")
    add("")

    # Quality flags
    q = r.quality
    add("## Financial-Health Screens")
    add("")
    add("| Screen | Score | Interpretation |")
    add("| --- | --- | --- |")
    add(f"| Altman Z | {_num(q.altman_z)} | {q.altman_interpretation or '—'} |")
    add(f"| Piotroski F | {_num(q.piotroski_f, 0)} | {q.piotroski_interpretation or '—'} |")
    add(f"| Beneish M | {_num(q.beneish_m)} | {q.beneish_interpretation or '—'} |")
    add("")

    if r.score_breakdown:
        add("## Score Breakdown")
        add("")
        for key, val in r.score_breakdown.items():
            label = key.replace("_", " ").title()
            add(f"- {label}: {_num(val, 0) if isinstance(val, (int, float)) else val}")
        add("")

    if r.catalysts:
        add("## Catalysts")
        add("")
        for c in r.catalysts:
            add(f"- {c}")
        add("")

    if r.risks:
        add("## Risks")
        add("")
        for risk in r.risks:
            tag = f" _({risk.severity})_" if risk.severity else ""
            cat = f"**{risk.category}**: " if risk.category else ""
            add(f"- {cat}{risk.description}{tag}")
        add("")

    if r.fundamental_commentary:
        add("## Fundamental Commentary")
        add("")
        add(r.fundamental_commentary)
        add("")

    if r.technical_commentary:
        add("## Technical Commentary")
        add("")
        add(r.technical_commentary)
        add("")

    if r.warnings:
        add("## Data Warnings")
        add("")
        for w in r.warnings:
            add(f"- {w}")
        add("")

    # Provenance footer
    p = r.provenance
    if p:
        add("---")
        add("")
        add(
            "_Provenance_: "
            + ", ".join(
                filter(
                    None,
                    [
                        f"generated {p.generated_at}",
                        f"code {p.code_sha}" if p.code_sha else None,
                        f"config {p.config_version}" if p.config_version else None,
                        f"data as-of {p.data_as_of}" if p.data_as_of else None,
                        f"mode {p.workflow_mode}" if p.workflow_mode else None,
                        f"synthesis {p.synthesis_method}" if p.synthesis_method else None,
                        f"{p.llm_provider}/{p.llm_model}" if p.llm_provider else None,
                    ],
                )
            )
        )
    return "\n".join(lines)
