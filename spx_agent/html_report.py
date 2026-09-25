"""
Renders the SPX analysis report dict (see report_data.build_report) into a
single self-contained HTML file -- no external CSS/JS, opens directly in a
browser. Includes an inline SVG sparkline of recent closes (no plotting
library dependency at render time).
"""
from __future__ import annotations

import base64
from typing import Dict, List

from spx_agent.chart import render_intraday_levels_chart, render_levels_chart


def _img_data_uri(png_bytes: bytes) -> str:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _sparkline_svg(bars: List[Dict], width: int = 760, height: int = 160) -> str:
    if not bars:
        return ""
    closes = [b["close"] for b in bars]
    lo, hi = min(closes), max(closes)
    span = (hi - lo) or 1.0
    pad = 8
    n = len(closes)
    step = (width - 2 * pad) / max(n - 1, 1)

    points = []
    for i, c in enumerate(closes):
        x = pad + i * step
        y = height - pad - ((c - lo) / span) * (height - 2 * pad)
        points.append(f"{x:.1f},{y:.1f}")
    polyline = " ".join(points)

    up = closes[-1] >= closes[0]
    color = "#1e9e5a" if up else "#c0392b"

    first_date = bars[0]["date"]
    last_date = bars[-1]["date"]

    return f'''
    <svg viewBox="0 0 {width} {height}" width="100%" height="{height}" preserveAspectRatio="none"
         style="background:var(--panel-bg);border-radius:8px;">
      <polyline fill="none" stroke="{color}" stroke-width="2" points="{polyline}" />
      <text x="{pad}" y="{height - 4}" font-size="11" fill="var(--muted)">{first_date}</text>
      <text x="{width - pad}" y="{height - 4}" font-size="11" fill="var(--muted)" text-anchor="end">{last_date}</text>
      <text x="{pad}" y="14" font-size="11" fill="var(--muted)">{hi:.0f}</text>
      <text x="{pad}" y="{height - 14}" font-size="11" fill="var(--muted)">{lo:.0f}</text>
    </svg>
    '''


def _levels_table(swing_levels: Dict, timeframe_labels: Dict[str, str]) -> str:
    rows = []
    for key, label in timeframe_labels.items():
        sw = swing_levels.get(key, {"highs": [], "lows": []})
        highs = ", ".join(f"{h:,.2f}" for h in sw["highs"]) or "-"
        lows = ", ".join(f"{l:,.2f}" for l in sw["lows"]) or "-"
        rows.append(f"<tr><td>{label}</td><td>{highs}</td><td>{lows}</td></tr>")
    return "\n".join(rows)


def _seasonality_table(seasonality: Dict) -> str:
    rows = []
    current_num = seasonality["current_month_num"]
    for m in range(1, 13):
        stats = seasonality["by_month"].get(m)
        if not stats:
            continue
        cls = ' class="current-month"' if m == current_num else ""
        rows.append(
            f"<tr{cls}><td>{stats['month']}</td><td>{stats['years_observed']}</td>"
            f"<td>{stats['avg_return_pct']:+.2f}%</td><td>{stats['win_rate_pct']:.0f}%</td>"
            f"<td>{stats['avg_range_pct']:.2f}%</td>"
            f"<td>{stats['best_pct']:+.2f}%</td><td>{stats['worst_pct']:+.2f}%</td></tr>"
        )
    return "\n".join(rows)


def _votes_list(votes) -> str:
    items = []
    for score, reason in votes:
        cls = "vote-bull" if score > 0 else ("vote-bear" if score < 0 else "vote-neutral")
        label = "Bullish" if score > 0 else ("Bearish" if score < 0 else "Neutral")
        items.append(f'<li class="{cls}">{reason}: <strong>{label}</strong></li>')
    return "\n".join(items)


def _zones_list(zones: List[Dict]) -> str:
    if not zones:
        return "-"
    return ", ".join(f"{z['level']:,.0f} ({z['touches']}x)" for z in zones)


def _sessions_table(sessions: List[Dict]) -> str:
    rows = []
    for s in sessions:
        cls = "vote-bull" if s["up_day"] else "vote-bear"
        arrow = "▲" if s["up_day"] else "▼"
        rows.append(
            f"<tr><td>{s['date']}</td><td>{s['open']:,.0f}</td><td>{s['high']:,.0f}</td>"
            f"<td>{s['low']:,.0f}</td><td>{s['close']:,.0f}</td><td>{s['vwap']:,.0f}</td>"
            f"<td>{s['or_high']:,.0f} / {s['or_low']:,.0f}</td><td>{s['range_pts']:,.0f}</td>"
            f"<td class=\"{cls}\">{arrow}</td></tr>"
        )
    return "\n".join(rows)


def _level_narrative_table(entries: List[Dict]) -> str:
    rows = []
    for e in entries:
        cls = "vote-bear" if e["kind"] == "resistance" else "vote-bull"
        kind_label = "Resistance" if e["kind"] == "resistance" else "Support"
        rows.append(
            f"<tr><td>{e['level']:,.0f}</td><td class=\"{cls}\"><strong>{kind_label}</strong></td>"
            f"<td>{e['label']}</td><td>{e['reason']}</td></tr>"
        )
    return "\n".join(rows)


def _scenarios_html(scenarios: List[Dict]) -> str:
    items = []
    for s in scenarios:
        items.append(
            f'<div class="scenario"><div class="scenario-cond">{s["condition"]}</div>'
            f'<div class="scenario-read">{s["read"]}</div></div>'
        )
    return "\n".join(items)


_STRENGTH_BADGES = {
    "strong": ("Strong", "badge-strong"),
    "weak": ("Weak", "badge-weak"),
    "mixed": ("Mixed", "badge-mixed"),
    "limited": ("Limited data", "badge-limited"),
    "untested": ("Untested", "badge-untested"),
}


def _price_grid_table(rows: List[Dict]) -> str:
    out = []
    for r in rows:
        cls = "vote-bear" if r["kind"] == "resistance" else "vote-bull"
        kind_label = "Resistance" if r["kind"] == "resistance" else "Support"
        held = f"{r['held_pct']:.0f}%" if r["held_pct"] is not None else "-"
        broke = f"{r['broke_pct']:.0f}%" if r["broke_pct"] is not None else "-"
        fwd = f"{r['avg_forward_5d_move_pts']:+.1f}" if r["avg_forward_5d_move_pts"] is not None else "-"
        badge_label, badge_cls = _STRENGTH_BADGES.get(r.get("strength", "mixed"), ("Mixed", "badge-mixed"))
        row_cls = " grid-row-strong" if r.get("strength") == "strong" else ""
        why_cell = r["note"]
        if r.get("next_day_note"):
            why_cell += f'<div class="next-day-note">{r["next_day_note"]}</div>'
        out.append(
            f"<tr class=\"{row_cls.strip()}\"><td>{r['level']:,.0f}</td><td>{r['distance_pts']:+.0f}</td>"
            f"<td class=\"{cls}\"><strong>{kind_label}</strong></td>"
            f"<td><span class=\"badge {badge_cls}\">{badge_label}</span></td>"
            f"<td>{r['touches']}</td>"
            f"<td>{held}</td><td>{broke}</td><td>{fwd}</td><td>{why_cell}</td></tr>"
        )
    return "\n".join(out)


def _recent_levels_table(levels: List[Dict]) -> str:
    rows = []
    for lv in levels:
        cls = "vote-bear" if lv["kind"] == "resistance" else "vote-bull"
        kind_label = "Resistance" if lv["kind"] == "resistance" else "Support"
        rows.append(
            f"<tr><td>{lv['level']:,.0f}</td><td class=\"{cls}\"><strong>{kind_label}</strong></td>"
            f"<td>{lv['date']}</td><td>{lv['action']}</td></tr>"
        )
    return "\n".join(rows)


def _gex_strikes_table(rows: List[Dict], kind: str) -> str:
    out = []
    for r in rows:
        cls = "vote-bull" if kind == "positive" else "vote-bear"
        out.append(
            f"<tr><td>{r['strike']:,.0f}</td><td class=\"{cls}\"><strong>{r['net_gex'] / 1e9:+.2f}B</strong></td>"
            f"<td>{r['call_oi']:,.0f}</td><td>{r['put_oi']:,.0f}</td></tr>"
        )
    return "\n".join(out)


def _setups_html(setups: List[Dict], cls: str) -> str:
    items = []
    for s in setups:
        items.append(
            f'<div class="setup {cls}"><div class="setup-trigger">{s["trigger"]}</div>'
            f'<div class="setup-read">{s["read"]}</div></div>'
        )
    return "\n".join(items)


def _primary_badge(side: Dict) -> str:
    if side.get("primary"):
        return '<span class="badge badge-strong" style="margin-left:8px;">PRIMARY</span>'
    return '<span class="badge badge-mixed" style="margin-left:8px;">COUNTER-TREND</span>'


def _entry_exit_card(side: Dict, cls: str) -> str:
    rr1 = f"{side['reward_risk_ratio']:.2f}" if side["reward_risk_ratio"] is not None else "-"
    rr2 = f"{side['reward_risk_ratio2']:.2f}" if side.get("reward_risk_ratio2") is not None else "-"
    return f'''
    <div class="setup {cls}">
      <div class="grid">
        <div class="stat"><div class="label">Entry</div><div class="value">{side['entry']:,.1f}</div></div>
        <div class="stat"><div class="label">Target 1 (near-term)</div><div class="value">{side['target1']:,.1f}</div></div>
        <div class="stat"><div class="label">Target 2 (tomorrow's swing)</div><div class="value">{side['target2']:,.1f}</div></div>
        <div class="stat"><div class="label">Stop</div><div class="value">{side['stop']:,.1f}</div></div>
        <div class="stat"><div class="label">R:R (T1 / T2)</div><div class="value">{rr1}R / {rr2}R</div></div>
      </div>
      <div class="setup-read" style="margin-top:8px;"><strong>Entry:</strong> {side['entry_reason']}. <strong>Target 1:</strong> {side['target1_reason']} <strong>Target 2:</strong> {side['target2_reason']}</div>
      <div class="setup-read" style="margin-top:4px;font-style:italic;">{side.get('quality_note', '')}</div>
    </div>
    '''


def _time_profile_svg(profile: List[Dict], width: int = 760, height: int = 140) -> str:
    if not profile:
        return ""
    values = [p["avg_range_pts"] for p in profile]
    max_v = max(values) or 1.0
    pad = 6
    n = len(values)
    bar_w = (width - 2 * pad) / n

    bars_svg = []
    for i, p in enumerate(profile):
        h = (p["avg_range_pts"] / max_v) * (height - 24)
        x = pad + i * bar_w
        y = height - 18 - h
        bars_svg.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w * 0.7:.1f}" height="{h:.1f}" fill="var(--accent)" />'
        )
    label_idx = list(range(0, n, max(1, n // 8)))
    labels = "".join(
        f'<text x="{pad + i * bar_w:.1f}" y="{height - 4}" font-size="9" fill="var(--muted)">{profile[i]["time"]}</text>'
        for i in label_idx
    )
    return f'''
    <svg viewBox="0 0 {width} {height}" width="100%" height="{height}" preserveAspectRatio="none"
         style="background:var(--panel-bg);border-radius:8px;">
      {''.join(bars_svg)}
      {labels}
    </svg>
    '''


def render_html_report(report: Dict) -> str:
    symbol = report.get("symbol", "SPX")
    display_name = report.get("display_name", symbol)

    levels = report["levels"]
    tech = report["technicals"]
    season = report["seasonality"]
    proj = report["projection"]

    lean_cls = "lean-green" if "Green" in proj["directional_lean"] or "green" in proj["directional_lean"] else (
        "lean-red" if "Red" in proj["directional_lean"] or "red" in proj["directional_lean"] else "lean-neutral"
    )

    timeframe_labels = {"5y": "5 Year", "1y": "1 Year", "3m": "3 Month", "1m": "1 Month", "1w": "1 Week"}

    ma = levels["moving_averages"]
    round_levels = ", ".join(f"{r:,.0f}" for r in levels["round_number_levels"])

    intraday_bars_raw = report.get("intraday_bars")
    if intraday_bars_raw:
        chart_png = render_intraday_levels_chart(intraday_bars_raw, report["level_narrative"], proj,
                                                  grid_rows=report["price_grid"]["rows"], sessions=5, symbol=symbol)
        chart_title = "Levels Chart &mdash; Last 5 Sessions (15-Min Candles)"
        chart_alt = f"{symbol} 15-minute candlestick chart with key support/resistance levels"
    else:
        chart_png = render_levels_chart(report["recent_bars"], report["level_narrative"], proj,
                                         grid_rows=report["price_grid"]["rows"],
                                         recent_levels=report["recent_session_levels"]["levels"],
                                         recent_lookback=report["recent_session_levels"]["lookback"],
                                         symbol=symbol)
        chart_title = "Levels Chart &mdash; Last 60 Sessions"
        chart_alt = f"{symbol} daily candlestick chart with key support/resistance levels"
    chart_uri = _img_data_uri(chart_png)

    intraday = report.get("intraday")
    intraday_html = ""
    if intraday:
        last = intraday["last_session"]
        intraday_html = f"""
  <div class="panel">
    <h2>Day-Trading Levels (15-Min Candles, Last {intraday['sessions_used']} Sessions)</h2>
    <div class="subtitle" style="margin-bottom:14px;">
      {intraday['date_range'][0]} &rarr; {intraday['date_range'][1]} &middot; {intraday['bars_used']} 15-minute bars
    </div>
    <div class="grid">
      <div class="stat"><div class="label">Last Session VWAP</div><div class="value">{last['vwap']:,.0f}</div></div>
      <div class="stat"><div class="label">Opening Range (30m) H/L</div><div class="value">{last['or_high']:,.0f} / {last['or_low']:,.0f}</div></div>
      <div class="stat"><div class="label">Last Session H/L</div><div class="value">{last['high']:,.0f} / {last['low']:,.0f}</div></div>
      <div class="stat"><div class="label">Nearest Resistance</div><div class="value">{intraday['nearest_resistance']:,.0f}</div></div>
      <div class="stat"><div class="label">Nearest Support</div><div class="value">{intraday['nearest_support']:,.0f}</div></div>
      <div class="stat"><div class="label">Median Session Range</div><div class="value">{intraday['median_session_range_pts']:,.0f} pts</div></div>
    </div>

    <h2 style="margin-top:20px;">Confluence Zones (15-min touches, last {intraday['sessions_used']} sessions)</h2>
    <table>
      <tbody>
        <tr><td style="width:120px;color:var(--muted);">Resistance</td><td>{_zones_list(intraday['resistance_zones'])}</td></tr>
        <tr><td style="color:var(--muted);">Support</td><td>{_zones_list(intraday['support_zones'])}</td></tr>
      </tbody>
    </table>

    <h2 style="margin-top:20px;">Recent Sessions</h2>
    <div class="overflow-x">
    <table>
      <thead><tr><th>Date</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>VWAP</th><th>OR (30m) H/L</th><th>Range</th><th></th></tr></thead>
      <tbody>
        {_sessions_table(intraday['sessions'])}
      </tbody>
    </table>
    </div>

    <h2 style="margin-top:20px;">Intraday Volatility by Time of Day</h2>
    <div class="subtitle" style="margin-bottom:8px;">Average 15-min bar range (points), across all sessions in the window &mdash; shows when the day tends to move most.</div>
    {_time_profile_svg(intraday['time_of_day_profile'])}
  </div>
"""

    gex = report.get("gex")
    gex_html = ""
    if gex:
        regime_cls = "lean-red" if "Negative" in gex["regime"] else "lean-green"
        flip_display = f"{gex['zero_gamma_flip']:,.0f}" if gex["zero_gamma_flip"] else "n/a"
        gex_html = f"""
  <div class="panel">
    <h2>Gamma Exposure (GEX)</h2>
    <div class="subtitle" style="margin-bottom:10px;">
      Live ^SPX options chain, {len(gex['expiries_used'])} expiries out to {gex['expiries_used'][-1]} &mdash;
      dealer gamma exposure per strike, estimated from open interest + implied volatility via Black-Scholes gamma.
    </div>
    <div class="lean-box {regime_cls}">
      <div>
        <div class="label" style="color:var(--muted);font-size:0.75rem;text-transform:uppercase;">Regime</div>
        <div class="lean-title" style="font-size:1.05rem;">{gex['regime']}</div>
      </div>
      <div class="stat">
        <div class="label">Total Net GEX</div>
        <div class="value">{gex['total_net_gex'] / 1e9:+.1f}B</div>
      </div>
      <div class="stat">
        <div class="label">Zero-Gamma Flip</div>
        <div class="value">{flip_display}</div>
      </div>
    </div>
    <div class="trade-cols" style="margin-top:14px;">
      <div>
        <div style="font-weight:700;color:var(--green);margin-bottom:6px;">Top Positive GEX Strikes (pin-prone)</div>
        <div class="overflow-x">
        <table>
          <thead><tr><th>Strike</th><th>Net GEX</th><th>Call OI</th><th>Put OI</th></tr></thead>
          <tbody>{_gex_strikes_table(gex['top_positive_gex_strikes'], 'positive')}</tbody>
        </table>
        </div>
      </div>
      <div>
        <div style="font-weight:700;color:var(--red);margin-bottom:6px;">Top Negative GEX Strikes (vol-amplifying)</div>
        <div class="overflow-x">
        <table>
          <thead><tr><th>Strike</th><th>Net GEX</th><th>Call OI</th><th>Put OI</th></tr></thead>
          <tbody>{_gex_strikes_table(gex['top_negative_gex_strikes'], 'negative')}</tbody>
        </table>
        </div>
      </div>
    </div>
    <div class="caveat">{gex['assumption_note']}</div>
  </div>
"""

    live = report.get("live_quote")
    live_quote_html = ""
    if live:
        move_since_close = live["price"] - levels["last_close"]
        move_cls = "vote-bull" if move_since_close >= 0 else "vote-bear"
        live_quote_html = f'''
  <div class="live-quote-banner">
    <span class="live-dot"></span>
    <strong>{live['price']:,.2f}</strong>
    <span class="{move_cls}">({move_since_close:+.2f} since last close)</span>
    <span class="live-meta">as of {live['last_bar_time']} &middot; {live['staleness_display']} &middot; {live['note']}</span>
  </div>
'''

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{display_name} Historical Analysis</title>
<style>
  :root {{
    --bg: #f7f8fa; --panel-bg: #ffffff; --text: #1a1d23; --muted: #6b7280;
    --border: #e5e7eb; --accent: #2563eb;
    --green: #1e9e5a; --green-bg: #e7f7ee;
    --red: #c0392b; --red-bg: #fdecea;
    --neutral: #6b7280; --neutral-bg: #eef0f2;
    --strong-row-bg: #eafaf0;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #14161a; --panel-bg: #1d2026; --text: #e8eaed; --muted: #9aa0a8;
      --border: #2c3038; --accent: #5b9bff;
      --green: #34c77b; --green-bg: #123322;
      --red: #ff6b5e; --red-bg: #3a1a17;
      --neutral: #9aa0a8; --neutral-bg: #262a31;
      --strong-row-bg: #16301f;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
          margin: 0; padding: 24px 16px 48px; }}
  .wrap {{ max-width: 980px; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 4px; }}
  .subtitle {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 24px; }}
  .panel {{ background: var(--panel-bg); border: 1px solid var(--border); border-radius: 10px;
            padding: 18px 20px; margin-bottom: 20px; }}
  .panel h2 {{ font-size: 1.05rem; margin: 0 0 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--muted); font-weight: 600; font-size: 0.78rem; text-transform: uppercase; }}
  tr.current-month {{ background: var(--neutral-bg); font-weight: 600; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; }}
  .stat {{ background: var(--neutral-bg); border-radius: 8px; padding: 10px 14px; }}
  .stat .label {{ color: var(--muted); font-size: 0.75rem; text-transform: uppercase; }}
  .stat .value {{ font-size: 1.25rem; font-weight: 700; }}
  .lean-box {{ display: flex; flex-wrap: wrap; gap: 20px; align-items: center; padding: 16px 20px; border-radius: 10px; }}
  .lean-green {{ background: var(--green-bg); border: 1px solid var(--green); }}
  .lean-red {{ background: var(--red-bg); border: 1px solid var(--red); }}
  .lean-neutral {{ background: var(--neutral-bg); border: 1px solid var(--border); }}
  .lean-title {{ font-size: 1.3rem; font-weight: 800; }}
  .lean-green .lean-title {{ color: var(--green); }}
  .lean-red .lean-title {{ color: var(--red); }}
  .caveat {{ color: var(--muted); font-size: 0.8rem; margin-top: 10px; }}
  ul.votes {{ list-style: none; padding: 0; margin: 8px 0 0; font-size: 0.85rem; }}
  ul.votes li {{ padding: 3px 0; }}
  .vote-bull strong {{ color: var(--green); }}
  .vote-bear strong {{ color: var(--red); }}
  .vote-neutral strong {{ color: var(--muted); }}
  .overflow-x {{ overflow-x: auto; }}
  .scenario {{ padding: 10px 0; border-bottom: 1px solid var(--border); }}
  .scenario:last-child {{ border-bottom: none; }}
  .scenario-cond {{ font-weight: 700; margin-bottom: 4px; }}
  .scenario-read {{ color: var(--muted); font-size: 0.88rem; line-height: 1.4; }}
  .chart-img {{ width: 100%; height: auto; border-radius: 8px; display: block; }}
  .setup {{ border-radius: 8px; padding: 10px 14px; margin-bottom: 10px; }}
  .setup:last-child {{ margin-bottom: 0; }}
  .setup-calls {{ background: var(--green-bg); border: 1px solid var(--green); }}
  .setup-puts {{ background: var(--red-bg); border: 1px solid var(--red); }}
  .setup-trigger {{ font-weight: 700; margin-bottom: 3px; }}
  .setup-read {{ font-size: 0.85rem; color: var(--muted); line-height: 1.4; }}
  .trade-cols {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-top: 10px; }}
  .badge {{ display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 0.7rem; font-weight: 700;
            text-transform: uppercase; letter-spacing: 0.02em; white-space: nowrap; }}
  .badge-strong {{ background: var(--green-bg); color: var(--green); border: 1px solid var(--green); }}
  .badge-weak {{ background: var(--red-bg); color: var(--red); border: 1px solid var(--red); }}
  .badge-mixed {{ background: var(--neutral-bg); color: var(--muted); border: 1px solid var(--border); }}
  .badge-limited {{ background: var(--neutral-bg); color: var(--muted); border: 1px dashed var(--border); }}
  .badge-untested {{ background: var(--neutral-bg); color: var(--muted); border: 1px dashed var(--border); }}
  tr.grid-row-strong {{ background: var(--strong-row-bg); }}
  .live-quote-banner {{ display: flex; flex-wrap: wrap; align-items: center; gap: 10px; background: var(--panel-bg);
                          border: 1px solid var(--border); border-radius: 8px; padding: 10px 16px; margin-bottom: 20px;
                          font-size: 0.95rem; }}
  .live-dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--green); flex-shrink: 0;
               animation: live-pulse 2s ease-in-out infinite; }}
  @keyframes live-pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.35; }} }}
  .live-meta {{ color: var(--muted); font-size: 0.8rem; margin-left: auto; }}
  .next-day-note {{ margin-top: 4px; padding-top: 4px; border-top: 1px dashed var(--border); color: var(--muted); font-size: 0.82rem; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{display_name} Historical Analysis</h1>
  <div class="subtitle">
    {report['bars_used']} daily bars &middot; {report['history_start']} &rarr; {report['history_end']}
    &middot; Last close ({levels['as_of']}): <strong>{levels['last_close']:,.2f}</strong>
    &middot; Historical statistics only, not financial advice.
  </div>
{live_quote_html}
  <div class="panel">
    <h2>Tomorrow's Session &mdash; Statistical Lean</h2>
    <div class="lean-box {lean_cls}">
      <div>
        <div class="label" style="color:var(--muted);font-size:0.75rem;text-transform:uppercase;">Lean</div>
        <div class="lean-title">{proj['directional_lean']}</div>
      </div>
      <div class="stat">
        <div class="label">Projected Range (ATR-based)</div>
        <div class="value">{proj['projected_low']:,.0f} &ndash; {proj['projected_high']:,.0f}</div>
      </div>
      <div class="stat">
        <div class="label">Expected Move</div>
        <div class="value">&plusmn;{proj['expected_move_points']:,.1f} pts</div>
      </div>
      <div class="stat">
        <div class="label">Fixed &plusmn;{proj['fixed_band_points']:,.0f}pt Band</div>
        <div class="value">{proj['fixed_band_low']:,.0f} &ndash; {proj['fixed_band_high']:,.0f}</div>
      </div>
      <div class="stat">
        <div class="label">ATR(14)</div>
        <div class="value">{proj['atr14_points']:,.1f} pts</div>
      </div>
      <div class="stat">
        <div class="label">60d Up-Day Rate</div>
        <div class="value">{proj['recent_60d_up_day_pct']:.0f}%</div>
      </div>
    </div>
    <div class="caveat">{proj['caveat']}</div>
  </div>

  <div class="panel">
    <h2>{chart_title}</h2>
    <img class="chart-img" src="{chart_uri}" alt="{chart_alt}">
  </div>

  <div class="panel">
    <h2>Price Grid &mdash; Every {report['price_grid']['step_pts']:,.0f} Points From Current Price</h2>
    <div class="subtitle" style="margin-bottom:8px;">
      {report['price_grid']['levels_per_side']} levels each side of {report['price_grid']['last_close']:,.2f}, with each level's actual 5-year touch history &mdash;
      how many times {symbol} has traded there, whether it held or broke, the average close 5 sessions later, and (in the last column)
      what happened the very next session plus the average RSI at the time of each touch, as a rough "why" for the outcome.
    </div>
    <div class="overflow-x">
    <table>
      <thead><tr><th>Level</th><th>Distance</th><th>Type</th><th>Strength</th><th>Touches (5y)</th><th>Held</th><th>Broke</th><th>Avg 5d Fwd Move</th><th>What it means / next session</th></tr></thead>
      <tbody>
        {_price_grid_table(report['price_grid']['rows'])}
      </tbody>
    </table>
    </div>
  </div>

  <div class="panel">
    <h2>Last {report['recent_session_levels']['lookback']} Sessions &mdash; Support &amp; Resistance</h2>
    <div class="subtitle" style="margin-bottom:8px;">
      {report['recent_session_levels']['date_range'][0]} &rarr; {report['recent_session_levels']['date_range'][1]} &mdash;
      what price actually did after touching each level (also marked on the chart above, shaded region).
    </div>
    <div class="overflow-x">
    <table>
      <thead><tr><th>Level</th><th>Type</th><th>Date</th><th>What happened</th></tr></thead>
      <tbody>
        {_recent_levels_table(report['recent_session_levels']['levels'])}
      </tbody>
    </table>
    </div>
  </div>

  <div class="panel">
    <h2>Tomorrow's Trade Levels &mdash; Calls vs. Puts</h2>
    <div class="subtitle" style="margin-bottom:8px;">{report['trade_plan']['bias_note']}</div>
    <div class="trade-cols">
      <div>
        <div style="font-weight:700;color:var(--green);margin-bottom:6px;">CALLS &mdash; watch for strength</div>
        {_setups_html(report['trade_plan']['calls_setups'], 'setup-calls')}
      </div>
      <div>
        <div style="font-weight:700;color:var(--red);margin-bottom:6px;">PUTS &mdash; watch for weakness</div>
        {_setups_html(report['trade_plan']['puts_setups'], 'setup-puts')}
      </div>
    </div>
    <div class="caveat">{report['trade_plan']['caveat']}</div>
  </div>

  <div class="panel">
    <h2>Entry &amp; Exit Plan &mdash; &plusmn;{report['entry_exit_plan']['target_points_requested']:,.0f} Point Target</h2>
    <div class="subtitle" style="margin-bottom:8px;">
      Entry/target/stop built from the levels above (Target 1 capped at the next real level if it's closer than the requested
      {report['entry_exit_plan']['target_points_requested']:,.0f} points; Target 2 is tomorrow's statistically projected extreme; stop is {report['entry_exit_plan']['stop_distance_pts']:,.1f} pts, from ATR).
      {report['entry_exit_plan']['lean_note']}
      {(report['entry_exit_plan']['point_value_note'] or '')}
    </div>
    <div class="trade-cols">
      <div>
        <div style="font-weight:700;color:var(--green);margin-bottom:6px;">LONG{_primary_badge(report['entry_exit_plan']['long'])}</div>
        {_entry_exit_card(report['entry_exit_plan']['long'], 'setup-calls')}
      </div>
      <div>
        <div style="font-weight:700;color:var(--red);margin-bottom:6px;">SHORT{_primary_badge(report['entry_exit_plan']['short'])}</div>
        {_entry_exit_card(report['entry_exit_plan']['short'], 'setup-puts')}
      </div>
    </div>
    <div class="caveat">{report['entry_exit_plan']['caveat']}</div>
  </div>

  <div class="panel">
    <h2>If Tomorrow Opens At...</h2>
    <div class="subtitle" style="margin-bottom:4px;">What to watch depending on where the open lands relative to today's key levels.</div>
    {_scenarios_html(report['open_scenarios'])}
  </div>
{intraday_html}
{gex_html}
  <div class="panel">
    <h2>Last 90 Sessions</h2>
    {_sparkline_svg(report['recent_bars'])}
  </div>

  <div class="panel">
    <h2>Key Levels</h2>
    <div class="overflow-x">
    <table>
      <thead><tr><th>Timeframe</th><th>Resistance (swing highs)</th><th>Support (swing lows)</th></tr></thead>
      <tbody>
        {_levels_table(levels['swing_levels'], timeframe_labels)}
      </tbody>
    </table>
    </div>
    <div class="grid" style="margin-top:16px;">
      <div class="stat"><div class="label">Prior Day H/L</div><div class="value">{levels['prior_day']['high']:,.0f} / {levels['prior_day']['low']:,.0f}</div></div>
      <div class="stat"><div class="label">Prior Week H/L</div><div class="value">{levels['prior_week']['high']:,.0f} / {levels['prior_week']['low']:,.0f}</div></div>
      <div class="stat"><div class="label">Prior Month H/L</div><div class="value">{levels['prior_month']['high']:,.0f} / {levels['prior_month']['low']:,.0f}</div></div>
      <div class="stat"><div class="label">5Y Range</div><div class="value">{levels['range_5y']['high']:,.0f} / {levels['range_5y']['low']:,.0f}</div></div>
      <div class="stat"><div class="label">SMA 20/50/100/200</div><div class="value" style="font-size:0.95rem;">{ma['sma20']:,.0f} / {ma['sma50']:,.0f} / {ma['sma100']:,.0f} / {ma['sma200']:,.0f}</div></div>
      <div class="stat"><div class="label">Round-Number Levels</div><div class="value" style="font-size:0.95rem;">{round_levels}</div></div>
    </div>
  </div>

  <div class="panel">
    <h2>Level Explanations &mdash; Why Each Level Matters</h2>
    <div class="overflow-x">
    <table>
      <thead><tr><th>Level</th><th>Type</th><th>Source</th><th>Why</th></tr></thead>
      <tbody>
        {_level_narrative_table(report['level_narrative'])}
      </tbody>
    </table>
    </div>
  </div>

  <div class="panel">
    <h2>Technicals &amp; Trend Bias &mdash; {tech['trend_bias']}</h2>
    <div class="grid">
      <div class="stat"><div class="label">RSI (14)</div><div class="value">{tech['rsi14']:.1f}</div></div>
      <div class="stat"><div class="label">ADX (14)</div><div class="value">{tech['adx14']:.1f}</div></div>
      <div class="stat"><div class="label">DI+ / DI-</div><div class="value">{tech['plus_di']:.1f} / {tech['minus_di']:.1f}</div></div>
      <div class="stat"><div class="label">MACD Histogram</div><div class="value">{tech['macd_hist']:+.2f}</div></div>
      <div class="stat"><div class="label">ATR (14)</div><div class="value">{tech['atr14']:.1f} pts</div></div>
    </div>
    <ul class="votes">
      {_votes_list(tech['votes'])}
    </ul>
  </div>

  <div class="panel">
    <h2>Monthly Seasonality (5-Year History)</h2>
    <div class="overflow-x">
    <table>
      <thead><tr><th>Month</th><th>Years</th><th>Avg Return</th><th>Win Rate</th><th>Avg Range</th><th>Best</th><th>Worst</th></tr></thead>
      <tbody>
        {_seasonality_table(season)}
      </tbody>
    </table>
    </div>
  </div>

</div>
</body>
</html>
"""
