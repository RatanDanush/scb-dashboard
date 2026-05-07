# html_generator.py
# Generates the complete HTML snapshot (weekly or daily) from data + stories.
# Output matches the quality and structure of stanc_weekly_w18_v2.html

from datetime import datetime

# ── SVG helpers ───────────────────────────────────────────────────────────────

X5 = [90, 210, 330, 424, 510]   # fixed x positions for 5-day charts

def _clamp(y, top, bottom):
    return max(top + 1, min(bottom - 1, y))

def _y(val, val_min, val_max, y_bottom, y_top):
    """Map a data value to SVG y coordinate."""
    r = val_max - val_min if val_max != val_min else 0.001
    return _clamp(y_bottom - ((val - val_min) / r) * (y_bottom - y_top),
                  y_top, y_bottom)

def svg_line_points(values, x_pos, val_min, val_max, y_bottom, y_top):
    """Return SVG polyline points string, forward-filling None values."""
    last = next((v for v in values if v is not None), (val_min + val_max) / 2)
    pts = []
    for x, v in zip(x_pos, values):
        if v is not None:
            last = v
        pts.append(f"{x},{_y(last, val_min, val_max, y_bottom, y_top):.0f}")
    return " ".join(pts)

def svg_dots(values, x_pos, val_min, val_max, y_bottom, y_top,
             color, closed_idx=None):
    """Return SVG circle elements for data points."""
    last = next((v for v in values if v is not None), (val_min + val_max) / 2)
    out = []
    for i, (x, v) in enumerate(zip(x_pos, values)):
        if v is not None:
            last = v
        y = _y(last, val_min, val_max, y_bottom, y_top)
        op = ' opacity=".3"' if i == closed_idx else ''
        out.append(f'<circle cx="{x}" cy="{y:.0f}" r="3" fill="{color}"{op}/>')
    return "\n    ".join(out)

def svg_val_label(val, x, val_min, val_max, y_bottom, y_top,
                  color, fmt="{:.2f}%", dy=-7):
    """Label the last data point on a chart."""
    y = _y(val, val_min, val_max, y_bottom, y_top) + dy
    return (f'<text x="{x}" y="{y:.0f}" text-anchor="middle" '
            f'font-family="Arial" font-size="8" fill="{color}" '
            f'font-weight="bold">{fmt.format(val)}</text>')

def build_inr_perf_chart(inr_vs_usd, inr_vs_eur, inr_vs_gbp, day_labels):
    """Build the INR weekly performance SVG sparkline."""
    all_vals = [v for v in (inr_vs_usd + inr_vs_eur + inr_vs_gbp) if v is not None]
    if not all_vals:
        return '<svg viewBox="0 0 560 105" xmlns="http://www.w3.org/2000/svg" style="width:100%;display:block;"><text x="280" y="52" text-anchor="middle" font-family="Arial" font-size="12" fill="#aaa">Chart data unavailable</text></svg>'

    pad   = 0.15
    vmin  = min(all_vals) - pad
    vmax  = max(all_vals) + pad
    # Ensure zero is visible
    vmin  = min(vmin, -0.05)
    vmax  = max(vmax, 0.05)

    YB, YT = 82, 22   # y_bottom, y_top
    zero_y = _y(0, vmin, vmax, YB, YT)

    # Zero line labels
    top_label  = f"+{vmax:.1f}%"
    zero_label = "0%"
    bot_label  = f"{vmin:.1f}%"

    pts_usd = svg_line_points(inr_vs_usd, X5, vmin, vmax, YB, YT)
    pts_eur = svg_line_points(inr_vs_eur, X5, vmin, vmax, YB, YT)
    pts_gbp = svg_line_points(inr_vs_gbp, X5, vmin, vmax, YB, YT)

    dots_usd = svg_dots(inr_vs_usd, X5, vmin, vmax, YB, YT, "#c0392b")
    dots_eur = svg_dots(inr_vs_eur, X5, vmin, vmax, YB, YT, "#1a5fa8")
    dots_gbp = svg_dots(inr_vs_gbp, X5, vmin, vmax, YB, YT, "#2e7d32")

    # Final labels
    last_usd = next((v for v in reversed(inr_vs_usd) if v is not None), 0)
    last_eur = next((v for v in reversed(inr_vs_eur) if v is not None), 0)
    last_gbp = next((v for v in reversed(inr_vs_gbp) if v is not None), 0)

    # Day labels
    day_svg = ""
    for x, lbl in zip(X5, day_labels):
        day_svg += f'<text x="{x}" y="100" text-anchor="middle" font-family="Arial" font-size="8" fill="#8a9aaa">{lbl}</text>\n    '

    return f'''<svg viewBox="0 0 560 105" xmlns="http://www.w3.org/2000/svg" style="width:100%;display:block;">
    <line x1="52" y1="{YT}" x2="538" y2="{YT}" stroke="#ebebeb" stroke-width="1"/>
    <line x1="52" y1="{zero_y:.0f}" x2="538" y2="{zero_y:.0f}" stroke="#ccc" stroke-width="1" stroke-dasharray="3,3"/>
    <line x1="52" y1="{YB}" x2="538" y2="{YB}" stroke="#ebebeb" stroke-width="1"/>
    <text x="50" y="{YT+3}" text-anchor="end" font-family="Arial" font-size="8" fill="#9ab">{top_label}</text>
    <text x="50" y="{zero_y+3:.0f}" text-anchor="end" font-family="Arial" font-size="8" fill="#9ab">{zero_label}</text>
    <text x="50" y="{YB+3}" text-anchor="end" font-family="Arial" font-size="8" fill="#9ab">{bot_label}</text>
    {day_svg}
    <polyline points="{pts_usd}" fill="none" stroke="#c0392b" stroke-width="2"/>
    {dots_usd}
    <polyline points="{pts_eur}" fill="none" stroke="#1a5fa8" stroke-width="2" stroke-dasharray="5,2"/>
    {dots_eur}
    <polyline points="{pts_gbp}" fill="none" stroke="#2e7d32" stroke-width="2" stroke-dasharray="2,3"/>
    {dots_gbp}
    {svg_val_label(last_usd, 510, vmin, vmax, YB, YT, "#c0392b")}
    {svg_val_label(last_eur, 510, vmin, vmax, YB, YT, "#1a5fa8", dy=-16)}
    {svg_val_label(last_gbp, 510, vmin, vmax, YB, YT, "#2e7d32", dy=6)}
    <rect x="52" y="6" width="8" height="3" fill="#c0392b"/>
    <text x="63" y="10.5" font-family="Arial" font-size="8" fill="#444">vs USD</text>
    <line x1="100" y1="8" x2="108" y2="8" stroke="#1a5fa8" stroke-width="2" stroke-dasharray="4,2"/>
    <text x="111" y="10.5" font-family="Arial" font-size="8" fill="#444">vs EUR</text>
    <line x1="149" y1="8" x2="157" y2="8" stroke="#2e7d32" stroke-width="2" stroke-dasharray="2,3"/>
    <text x="160" y="10.5" font-family="Arial" font-size="8" fill="#444">vs GBP</text>
    <rect x="340" y="4" width="218" height="14" fill="#eef2f9" rx="2"/>
    <text x="345" y="13.5" font-family="Arial" font-size="7.5" fill="#002060" font-weight="bold">↓ = INR weaker vs that currency from Mon open</text>
</svg>'''


def build_brent_inr_chart(brent_5d, usdinr_5d, day_labels):
    """Build the Brent vs USD/INR 5-day dual-axis SVG."""
    b_clean = [v for v in brent_5d if v is not None]
    u_clean = [v for v in usdinr_5d if v is not None]
    if not b_clean or not u_clean:
        return '<svg viewBox="0 0 560 88" xmlns="http://www.w3.org/2000/svg" style="width:100%;display:block;"><text x="280" y="44" text-anchor="middle" font-family="Arial" font-size="12" fill="#aaa">Chart data unavailable</text></svg>'

    # Brent scale
    bmin = min(b_clean) * 0.995
    bmax = max(b_clean) * 1.005
    # USD/INR scale
    umin = min(u_clean) * 0.999
    umax = max(u_clean) * 1.001

    YB, YT = 70, 16

    pts_b = svg_line_points(brent_5d, X5, bmin, bmax, YB, YT)
    pts_u = svg_line_points(usdinr_5d, X5, umin, umax, YB, YT)
    dots_b = svg_dots(brent_5d, X5, bmin, bmax, YB, YT, "#c0392b")
    dots_u = svg_dots(usdinr_5d, X5, umin, umax, YB, YT, "#1a5fa8")

    day_svg = ""
    for x, lbl in zip(X5, day_labels):
        day_svg += f'<text x="{x}" y="83" text-anchor="middle" font-family="Arial" font-size="8" fill="#8a9aaa">{lbl}</text>\n    '

    return f'''<svg viewBox="0 0 560 88" xmlns="http://www.w3.org/2000/svg" style="width:100%;display:block;">
    <line x1="52" y1="{YT}" x2="510" y2="{YT}" stroke="#f0e0e0" stroke-width="1"/>
    <line x1="52" y1="{(YT+YB)//2}" x2="510" y2="{(YT+YB)//2}" stroke="#eee" stroke-width="1" stroke-dasharray="3,3"/>
    <line x1="52" y1="{YB}" x2="510" y2="{YB}" stroke="#f0e0e0" stroke-width="1"/>
    <text x="50" y="{YT+3}" text-anchor="end" font-family="Arial" font-size="8" fill="#c0392b">${bmax:.0f}</text>
    <text x="50" y="{YB+3}" text-anchor="end" font-family="Arial" font-size="8" fill="#c0392b">${bmin:.0f}</text>
    <text x="512" y="{YT+3}" font-family="Arial" font-size="8" fill="#1a5fa8">{umax:.2f}</text>
    <text x="512" y="{YB+3}" font-family="Arial" font-size="8" fill="#1a5fa8">{umin:.2f}</text>
    {day_svg}
    <polyline points="{pts_b}" fill="none" stroke="#c0392b" stroke-width="2.5"/>
    {dots_b}
    <polyline points="{pts_u}" fill="none" stroke="#1a5fa8" stroke-width="2" stroke-dasharray="5,2"/>
    {dots_u}
    <rect x="52" y="5" width="8" height="3" fill="#c0392b"/>
    <text x="63" y="9.5" font-family="Arial" font-size="8" fill="#444">Brent (left $)</text>
    <line x1="128" y1="7" x2="136" y2="7" stroke="#1a5fa8" stroke-width="2" stroke-dasharray="4,2"/>
    <text x="139" y="9.5" font-family="Arial" font-size="8" fill="#444">USD/INR (right)</text>
</svg>'''

# ── Range bar helper ──────────────────────────────────────────────────────────

def range_bar(pct, color="#666"):
    return f'<div class="rbar-track"><div class="rbar-dot" style="left:{pct:.0f}%;background:{color};"></div></div>'

# ── Story card HTML ───────────────────────────────────────────────────────────

COLOR_CLASS = {
    'red':   'story red-s',
    'amber': 'story amber',
    'blue':  'story blue-s',
}

def story_card(story):
    color_cls = COLOR_CLASS.get(story.get('color', 'blue'), 'story blue-s')
    links_html = " &nbsp;·&nbsp; ".join(
        f'<a href="{lnk.get("url","#")}" target="_blank">{lnk.get("text","→ Source")}</a>'
        for lnk in story.get('links', [])
    )
    return f'''<div class="{color_cls}">
  <div class="story-tag">{story.get("tag","")}</div>
  <div class="story-head">{story.get("headline","")}</div>
  <div class="story-body">{story.get("body","")}</div>
  <div class="story-imp">{story.get("inr_relevance","")}</div>
  {'<div class="story-link">' + links_html + '</div>' if links_html else ""}
</div>'''

# ── Week ahead calendar row ───────────────────────────────────────────────────

def cal_row(event):
    impact = event.get('impact', 'MED')
    tag_cls = 'tag-hi' if impact == 'HIGH' else 'tag-med'
    row_cls = ' class="hi-row"' if impact == 'HIGH' else ''
    url = event.get('url', '#')
    evt = event.get('event', '')
    return f'''<tr{row_cls}>
      <td class="dt">{event.get("date","")}</td>
      <td><span class="{tag_cls}">{impact}</span>&nbsp; {evt} &nbsp;<a href="{url}" target="_blank" style="font-size:9px;color:#1a5fa8;">→ Source</a></td>
    </tr>'''

# ── Base CSS (shared by weekly and daily) ─────────────────────────────────────

BASE_CSS = """
*{margin:0;padding:0;box-sizing:border-box;}
body{background:#f0f2f5;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#1a1a2e;-webkit-text-size-adjust:100%;}
.wrap{max-width:620px;margin:0 auto;background:#fff;}
.hdr{background:#002060;padding:14px 16px 12px;border-bottom:3px solid #c8a84b;}
.hdr-brand{font-size:9px;letter-spacing:.16em;color:#7a9abf;text-transform:uppercase;margin-bottom:4px;}
.hdr-top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;}
.hdr-title{font-size:20px;font-weight:700;color:#fff;line-height:1.1;}
.hdr-week{font-size:10px;color:#c8a84b;font-weight:700;margin-top:3px;letter-spacing:.06em;}
.hdr-sub{font-size:9px;color:#5a7a9a;margin-top:2px;}
.hdr-date{text-align:right;font-size:9.5px;color:#8aaac8;line-height:1.7;flex-shrink:0;}
.mood{display:inline-block;background:#7d1c1c;color:#ffb3b3;font-size:9px;font-weight:700;letter-spacing:.1em;padding:2px 8px;margin-top:7px;text-transform:uppercase;}
.theme{background:#f7f4ed;border-bottom:2px solid #c8a84b;padding:7px 16px;font-size:10.5px;color:#3a2800;line-height:1.5;}
.theme strong{color:#002060;}
.sec-hdr{padding:8px 16px;font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#fff;display:flex;align-items:center;gap:8px;}
.sec-hdr.blue{background:#002060;}.sec-hdr.teal{background:#0a5a5a;}.sec-hdr.slate{background:#2a3a4a;}
.sec-num{font-size:16px;font-weight:700;opacity:.5;}
.sub-lbl{background:#f4f6f9;border-top:1px solid #dde1e8;border-bottom:1px solid #dde1e8;padding:4px 16px;font-size:9px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:#5a6a80;border-left:3px solid #c8a84b;}
.row{display:flex;gap:0;}
.card{flex:1;padding:10px 14px;border:1px solid #eef0f3;background:#fff;}
.card+.card{border-left:none;}
.lbl{font-size:9px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#6a7a8a;margin-bottom:3px;}
.val{font-size:21px;font-weight:700;color:#1a1a2e;line-height:1;}
.val-md{font-size:16px;font-weight:700;color:#1a1a2e;line-height:1;}
.chg{font-size:11px;font-weight:600;margin-top:3px;}
.red{color:#c0392b;}.green{color:#1a7a1a;}.grey{color:#7a8a9a;}
.sub{font-size:10px;color:#6a7a8a;margin-top:4px;line-height:1.4;}
.src-line{font-size:8px;color:#b0c0ce;margin-top:5px;}
.src-line a{color:#1a5fa8;text-decoration:none;}
.rbar{margin-top:7px;}
.rbar-lbl{font-size:8px;color:#9aabb8;display:flex;justify-content:space-between;}
.rbar-track{background:#e8eef3;height:4px;border-radius:2px;position:relative;margin-top:3px;}
.rbar-dot{position:absolute;top:-3px;width:10px;height:10px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 1px #888;transform:translateX(-5px);}
.insight{background:#f0f4fa;border-left:3px solid #002060;padding:8px 14px;font-size:10.5px;color:#1a1a2e;line-height:1.5;}
.insight strong{color:#002060;}
.chart-wrap{padding:10px 14px;border:1px solid #eef0f3;border-top:none;background:#fff;}
.chart-title{font-size:9px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#5a6a80;margin-bottom:6px;}
.story{padding:11px 14px;border:1px solid #eef0f3;border-left:3px solid #002060;background:#fff;}
.story+.story{border-top:none;}
.story.amber{border-left-color:#d4750a;}.story.red-s{border-left-color:#c0392b;}.story.blue-s{border-left-color:#1a5fa8;}
.story-tag{font-size:8.5px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#8a9aaa;margin-bottom:4px;}
.story-head{font-size:13px;font-weight:700;color:#1a1a2e;margin-bottom:5px;line-height:1.3;}
.story-body{font-size:11px;color:#3a4a5a;line-height:1.55;}
.story-imp{font-size:10.5px;font-weight:700;color:#002060;margin-top:6px;padding:4px 8px;background:#eef2f9;border-radius:2px;line-height:1.4;}
.story-link{font-size:9.5px;margin-top:5px;} .story-link a{color:#1a5fa8;text-decoration:none;font-weight:700;}
.cal{width:100%;border-collapse:collapse;font-size:11px;}
.cal td{padding:6px 12px;border-bottom:1px solid #eef0f3;vertical-align:top;}
.cal .dt{font-size:9px;font-weight:700;color:#8a9aaa;white-space:nowrap;width:60px;}
.cal .hi-row{background:#fdf4f4;}
.tag-hi{display:inline-block;padding:1px 5px;border-radius:2px;font-size:8px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;background:#fbe0e0;color:#c0392b;}
.tag-med{display:inline-block;padding:1px 5px;border-radius:2px;font-size:8px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;background:#fef3dc;color:#b07000;}
.ftr{background:#f4f6f9;border-top:2px solid #002060;padding:9px 16px;font-size:8.5px;color:#6a7a8a;line-height:1.7;}
.ftr a{color:#1a5fa8;text-decoration:none;font-weight:700;}
@media(max-width:460px){.row{flex-direction:column;}.card+.card{border-left:1px solid #eef0f3;border-top:none;}.hdr-date{display:none;}.val{font-size:18px;}}
"""

# ── Weekly HTML generator ─────────────────────────────────────────────────────

def generate_weekly_html(data, stories, week_ahead_events):
    """
    Generate the full weekly snapshot HTML.
    data: dict from data_fetcher.get_weekly_data()
    stories: list of dicts from macro_generator.get_weekly_stories()
    week_ahead_events: list of dicts from macro_generator.get_week_ahead()
    """
    d = data  # shorthand

    # ── Charts ──
    inr_chart = build_inr_perf_chart(
        d.get('inr_vs_usd', [0]*5),
        d.get('inr_vs_eur', [0]*5),
        d.get('inr_vs_gbp', [0]*5),
        d.get('day_labels', ['Mon','Tue','Wed','Thu','Fri'])
    )
    brent_chart = build_brent_inr_chart(
        d.get('brent_5d', [None]*5),
        d.get('usdinr_5d', [None]*5),
        d.get('day_labels', ['Mon','Tue','Wed','Thu','Fri'])
    )

    # ── Story cards ──
    stories_html = "\n".join(story_card(s) for s in stories)

    # ── Week ahead rows ──
    if week_ahead_events:
        cal_rows = "\n".join(cal_row(e) for e in week_ahead_events)
        week_ahead_section = f'''
<div class="sub-lbl">3.2 Week Ahead</div>
<div style="border:1px solid #eef0f3;">
  <table class="cal">
    {cal_rows}
  </table>
</div>'''
    else:
        week_ahead_section = ""

    # ── INR WoW colour ──
    usd_wow_val = d.get('usdinr_wow_val', 0)
    usd_wow_color = '#c0392b' if usd_wow_val > 0 else '#1a7a1a'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StanC FM · Weekly · W{d.get("week_num","")} {d.get("year","")}</title>
<style>{BASE_CSS}</style>
</head>
<body>
<div class="wrap">

<!-- HEADER -->
<div class="hdr">
  <div class="hdr-brand">Standard Chartered · Financial Markets Sales · India Desk</div>
  <div class="hdr-top">
    <div>
      <div class="hdr-title">Global FX — Weekly</div>
      <div class="hdr-week">WEEK {d.get("week_num","")} · {d.get("week_start","").upper()} – {d.get("week_end","").upper()}</div>
      <div class="hdr-sub">Internal &amp; Client Briefing · India FM Sales</div>
      <div class="mood">WEEKLY SNAPSHOT · AI-GENERATED DATA</div>
    </div>
    <div class="hdr-date">Generated {d.get("generated_at","")}</div>
  </div>
</div>

<!-- SECTION 1 — CURRENCY -->
<div class="sec-hdr blue"><span class="sec-num">01</span> CURRENCY</div>

<div class="sub-lbl">1.1 INR Spot &amp; Dollar Index</div>
<div class="row">
  <div class="card">
    <div class="lbl">USD / INR — Week Close</div>
    <div class="val">{d.get("usdinr_close","N/A")}</div>
    <div class="chg">{d.get("usdinr_wow","N/A")}</div>
    <div class="sub">
      Range: <strong>{d.get("usdinr_wk_low","N/A")}</strong> – <strong>{d.get("usdinr_wk_high","N/A")}</strong><br>
      Mon open: {d.get("usdinr_open","N/A")}
    </div>
    <div class="rbar">
      <div class="rbar-lbl"><span>52W Lo {d.get("usdinr_52w_lo","N/A")}</span><span>52W Hi {d.get("usdinr_52w_hi","N/A")}</span></div>
      {range_bar(d.get("usdinr_52w_pct",50), "#c0392b" if usd_wow_val > 0 else "#666")}
    </div>
    <div class="src-line"><a href="https://www.rbi.org.in/Scripts/ReferenceRateArchive.aspx" target="_blank">RBI Reference Rates</a> · <a href="https://finance.yahoo.com/quote/USDINR=X/" target="_blank">Yahoo Finance</a></div>
  </div>
  <div class="card">
    <div class="lbl">DXY — Dollar Index</div>
    <div class="val">{d.get("dxy_close","N/A")}</div>
    <div class="chg">{d.get("dxy_wow","N/A")}</div>
    <div class="sub">
      RBI Ref Rate: <strong>{d.get("rbi_ref","N/A")}</strong> {d.get("rbi_ref_wow","")}<br>
      52W: {d.get("dxy_52w_lo","N/A")} – {d.get("dxy_52w_hi","N/A")}
    </div>
    <div class="rbar">
      <div class="rbar-lbl"><span>52W Lo</span><span>52W Hi</span></div>
      {range_bar(d.get("dxy_52w_pct",50), "#666")}
    </div>
    <div class="src-line"><a href="https://www.investing.com/indices/usdollar" target="_blank">Investing.com DXY</a></div>
  </div>
</div>

<div class="insight">{d.get("inr_insight","")}</div>

<div class="chart-wrap" style="border-top:1px solid #eef0f3;">
  <div class="chart-title">INR weekly performance — % change from Mon open (↓ = INR weaker)</div>
  {inr_chart}
  <div class="src-line"><a href="https://wise.com/in/currency-converter/usd-to-inr-rate/history" target="_blank">Wise</a> · <a href="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html" target="_blank">ECB</a> · <a href="https://finance.yahoo.com" target="_blank">Yahoo Finance</a></div>
</div>

<div class="sub-lbl">1.2 G3 vs INR — Week Close &amp; WoW</div>
<div class="row">
  <div class="card">
    <div class="lbl">EUR / INR</div>
    <div class="val-md">{d.get("eurinr_close","N/A")}</div>
    <div class="chg">{d.get("eurinr_wow","N/A")}</div>
    <div class="rbar">
      <div class="rbar-lbl"><span>52W Lo ₹{d.get("eurinr_52w_lo","N/A")}</span><span>Hi ₹{d.get("eurinr_52w_hi","N/A")}</span></div>
      {range_bar(d.get("eurinr_52w_pct",50), "#c0392b" if d.get("eurinr_wow_val",0) > 0 else "#666")}
    </div>
    <div class="src-line"><a href="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html" target="_blank">ECB ref rates</a></div>
  </div>
  <div class="card">
    <div class="lbl">GBP / INR</div>
    <div class="val-md">{d.get("gbpinr_close","N/A")}</div>
    <div class="chg">{d.get("gbpinr_wow","N/A")}</div>
    <div class="rbar">
      <div class="rbar-lbl"><span>52W Lo ₹{d.get("gbpinr_52w_lo","N/A")}</span><span>Hi ₹{d.get("gbpinr_52w_hi","N/A")}</span></div>
      {range_bar(d.get("gbpinr_52w_pct",50), "#c0392b" if d.get("gbpinr_wow_val",0) > 0 else "#666")}
    </div>
    <div class="src-line"><a href="https://wise.com/in/currency-converter/gbp-to-inr-rate/history" target="_blank">Wise GBP/INR</a></div>
  </div>
</div>
<div class="row">
  <div class="card">
    <div class="lbl">JPY / INR (per 100 JPY)</div>
    <div class="val-md">₹{d.get("jpyinr_close","N/A")}</div>
    <div class="chg">{d.get("jpyinr_wow","N/A")}</div>
    <div class="rbar">
      <div class="rbar-lbl"><span>52W Lo ₹{d.get("jpyinr_52w_lo","N/A")}</span><span>Hi ₹{d.get("jpyinr_52w_hi","N/A")}</span></div>
      {range_bar(d.get("jpyinr_52w_pct",50), "#c0392b" if d.get("jpyinr_wow_val",0) > 0 else "#666")}
    </div>
    <div class="src-line"><a href="https://finance.yahoo.com/quote/USDJPY=X/" target="_blank">Yahoo Finance USD/JPY</a></div>
  </div>
  <div class="card">
    <div class="lbl">CNH / INR (per CNH)</div>
    <div class="val-md">₹{d.get("cnhinr_close","N/A")}</div>
    <div class="chg">{d.get("cnhinr_wow","N/A")}</div>
    <div class="rbar">
      <div class="rbar-lbl"><span>52W Lo ₹{d.get("cnhinr_52w_lo","N/A")}</span><span>Hi ₹{d.get("cnhinr_52w_hi","N/A")}</span></div>
      {range_bar(d.get("cnhinr_52w_pct",50), "#c0392b" if d.get("cnhinr_wow_val",0) > 0 else "#666")}
    </div>
    <div class="src-line"><a href="https://finance.yahoo.com/quote/USDCNH=X/" target="_blank">Yahoo Finance USD/CNH</a></div>
  </div>
</div>

<!-- SECTION 2 — RATES & COMMODITIES -->
<div class="sec-hdr teal"><span class="sec-num">02</span> RATES &amp; COMMODITIES</div>

<div class="sub-lbl">2.1 Bond Yields</div>
<div class="row">
  <div class="card">
    <div class="lbl">US 10Y Treasury</div>
    <div class="val">{d.get("us10y_close","N/A")}%</div>
    <div class="chg">{d.get("us10y_wow","N/A")}</div>
    <div class="rbar">
      <div class="rbar-lbl"><span>52W Lo {d.get("us10y_52w_lo","N/A")}%</span><span>Hi {d.get("us10y_52w_hi","N/A")}%</span></div>
      {range_bar(d.get("us10y_52w_pct",50), "#c0392b" if d.get("us10y_wow_val",0) > 0 else "#666")}
    </div>
    <div class="src-line"><a href="https://fred.stlouisfed.org/series/DGS10" target="_blank">FRED DGS10</a> · <a href="https://www.cnbc.com/quotes/US10Y" target="_blank">CNBC US10Y</a></div>
  </div>
  <div class="card">
    <div class="lbl">India 10Y G-Sec</div>
    <div class="val">{d.get("in10y_close","N/A")}%</div>
    <div class="chg">{d.get("in10y_wow","N/A")}</div>
    <div class="sub">India–US spread: <strong>{d.get("yield_spread","N/A")}</strong></div>
    <div class="rbar">
      <div class="rbar-lbl"><span>52W Lo {d.get("in10y_52w_lo","N/A")}%</span><span>Hi {d.get("in10y_52w_hi","N/A")}%</span></div>
      {range_bar(d.get("in10y_52w_pct",50), "#c0392b" if d.get("in10y_wow_val",0) > 0 else "#666")}
    </div>
    <div class="src-line"><a href="https://tradingeconomics.com/india/government-bond-yield" target="_blank">TradingEconomics India 10Y</a></div>
  </div>
</div>

<div class="sub-lbl">2.2 Policy Rates</div>
<div class="row">
  <div class="card">
    <div class="lbl">Fed Funds Rate</div>
    <div class="val" style="font-size:17px;">{d.get("fed_rate","N/A")}</div>
    <div class="chg grey">■ On hold</div>
    <div class="src-line"><a href="https://www.federalreserve.gov/monetarypolicy/openmarket.htm" target="_blank">Fed Reserve</a></div>
  </div>
  <div class="card">
    <div class="lbl">RBI Repo Rate</div>
    <div class="val" style="font-size:17px;">{d.get("rbi_rate","N/A")}</div>
    <div class="chg grey">■ On hold · Neutral stance</div>
    <div class="src-line"><a href="https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx" target="_blank">RBI MPC statement</a></div>
  </div>
</div>

<div class="sub-lbl">2.3 Commodities</div>
<div class="row">
  <div class="card">
    <div class="lbl">Brent Crude</div>
    <div class="val">${d.get("brent_close","N/A")}</div>
    <div class="chg">{d.get("brent_wow","N/A")}</div>
    <div class="sub">Week high: <strong>${d.get("brent_wk_high","N/A")}</strong></div>
    <div class="src-line"><a href="https://tradingeconomics.com/commodity/brent-crude-oil" target="_blank">TradingEconomics</a> · <a href="https://finance.yahoo.com/quote/BZ=F/" target="_blank">Yahoo Finance BZ=F</a></div>
  </div>
  <div class="card">
    <div class="lbl">MCX Gold (₹/10g proxy)</div>
    <div class="val-md">{d.get("gold_inr","N/A")}</div>
    <div class="chg">{d.get("gold_wow","N/A")}</div>
    <div class="sub">GC=F × USD/INR ÷ 3.11 · indicative</div>
    <div class="src-line"><a href="https://www.mcxindia.com/market-data/spot-market-price" target="_blank">MCX India</a> · <a href="https://finance.yahoo.com/quote/GC=F/" target="_blank">Yahoo Finance GC=F</a></div>
  </div>
</div>

<div class="chart-wrap">
  <div class="chart-title">Brent vs USD/INR — 5-day (Brent $, left · USD/INR, right)</div>
  {brent_chart}
  <div class="src-line"><a href="https://tradingeconomics.com/commodity/brent-crude-oil" target="_blank">TradingEconomics</a> · <a href="https://wise.com/in/currency-converter/usd-to-inr-rate/history" target="_blank">Wise</a></div>
</div>

<!-- SECTION 3 — MACRO -->
<div class="sec-hdr slate"><span class="sec-num">03</span> MACRO</div>
<div class="sub-lbl">3.1 Big Stories This Week</div>
{stories_html}
{week_ahead_section}

<!-- FOOTER -->
<div class="ftr">
  <strong>Standard Chartered Financial Markets — India FM Sales Desk</strong><br>
  Week {d.get("week_num","")} · {d.get("week_start","")} – {d.get("week_end","")} · Generated {d.get("generated_at","")}<br>
  Data: <a href="https://finance.yahoo.com" target="_blank">Yahoo Finance</a> · <a href="https://fred.stlouisfed.org" target="_blank">FRED</a> · <a href="https://www.rbi.org.in" target="_blank">RBI</a> · <a href="https://tradingeconomics.com" target="_blank">TradingEconomics</a> · Macro stories: Gemini AI + Google Search<br>
  <span style="color:#c0392b;">⚠ Policy rates (Fed/RBI) are static — update manually if changed. MCX Gold is indicative (GC=F proxy).</span>
</div>

</div>
</body>
</html>'''


# ── Daily HTML generator ──────────────────────────────────────────────────────

def generate_daily_html(data, stories):
    """
    Generate the full daily snapshot HTML (last 24 hours).
    """
    d = data
    stories_html = "\n".join(story_card(s) for s in stories)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StanC FM · Daily · {d.get("date","")}</title>
<style>{BASE_CSS}</style>
</head>
<body>
<div class="wrap">

<div class="hdr">
  <div class="hdr-brand">Standard Chartered · Financial Markets Sales · India Desk</div>
  <div class="hdr-top">
    <div>
      <div class="hdr-title">Global FX — Daily</div>
      <div class="hdr-week">{d.get("date","").upper()}</div>
      <div class="hdr-sub">Internal &amp; Client Briefing · India FM Sales</div>
      <div class="mood">DAILY SNAPSHOT · 24H CHANGE</div>
    </div>
    <div class="hdr-date">Generated {d.get("generated_at","")}</div>
  </div>
</div>

<div class="sec-hdr blue"><span class="sec-num">01</span> CURRENCY</div>
<div class="sub-lbl">INR Spot &amp; Dollar Index</div>
<div class="row">
  <div class="card">
    <div class="lbl">USD / INR</div>
    <div class="val">{d.get("usdinr_close","N/A")}</div>
    <div class="chg">{d.get("usdinr_chg","N/A")}</div>
    <div class="sub">RBI Ref Rate: <strong>{d.get("rbi_ref","N/A")}</strong></div>
    <div class="rbar">
      <div class="rbar-lbl"><span>52W Lo {d.get("usdinr_52w_lo","N/A")}</span><span>Hi {d.get("usdinr_52w_hi","N/A")}</span></div>
      {range_bar(d.get("usdinr_52w_pct",50))}
    </div>
    <div class="src-line"><a href="https://finance.yahoo.com/quote/USDINR=X/" target="_blank">Yahoo Finance</a> · <a href="https://www.rbi.org.in" target="_blank">RBI</a></div>
  </div>
  <div class="card">
    <div class="lbl">DXY — Dollar Index</div>
    <div class="val">{d.get("dxy_close","N/A")}</div>
    <div class="chg">{d.get("dxy_chg","N/A")}</div>
    <div class="src-line"><a href="https://www.investing.com/indices/usdollar" target="_blank">Investing.com</a></div>
  </div>
</div>

<div class="sub-lbl">G3 vs INR — 24H Change</div>
<div class="row">
  <div class="card">
    <div class="lbl">EUR / INR</div>
    <div class="val-md">{d.get("eurinr_close","N/A")}</div>
    <div class="chg">{d.get("eurinr_chg","N/A")}</div>
    <div class="src-line"><a href="https://www.ecb.europa.eu" target="_blank">ECB</a></div>
  </div>
  <div class="card">
    <div class="lbl">GBP / INR</div>
    <div class="val-md">{d.get("gbpinr_close","N/A")}</div>
    <div class="chg">{d.get("gbpinr_chg","N/A")}</div>
    <div class="src-line"><a href="https://finance.yahoo.com" target="_blank">Yahoo Finance</a></div>
  </div>
</div>
<div class="row">
  <div class="card">
    <div class="lbl">JPY / INR (per 100 JPY)</div>
    <div class="val-md">₹{d.get("jpyinr_close","N/A")}</div>
    <div class="chg">{d.get("jpyinr_chg","N/A")}</div>
    <div class="src-line"><a href="https://finance.yahoo.com/quote/USDJPY=X/" target="_blank">Yahoo Finance</a></div>
  </div>
  <div class="card">
    <div class="lbl">CNH / INR (per CNH)</div>
    <div class="val-md">₹{d.get("cnhinr_close","N/A")}</div>
    <div class="chg">{d.get("cnhinr_chg","N/A")}</div>
    <div class="src-line"><a href="https://finance.yahoo.com/quote/USDCNH=X/" target="_blank">Yahoo Finance</a></div>
  </div>
</div>

<div class="sec-hdr teal"><span class="sec-num">02</span> RATES &amp; COMMODITIES</div>
<div class="row">
  <div class="card">
    <div class="lbl">US 10Y Treasury</div>
    <div class="val">{d.get("us10y_close","N/A")}%</div>
    <div class="chg">{d.get("us10y_chg","N/A")}</div>
    <div class="src-line"><a href="https://fred.stlouisfed.org/series/DGS10" target="_blank">FRED</a></div>
  </div>
  <div class="card">
    <div class="lbl">India 10Y G-Sec</div>
    <div class="val">{d.get("in10y_close","N/A")}%</div>
    <div class="chg">{d.get("in10y_chg","N/A")}</div>
    <div class="sub">Spread vs US: <strong>{d.get("yield_spread","N/A")}</strong></div>
    <div class="src-line"><a href="https://tradingeconomics.com/india/government-bond-yield" target="_blank">TradingEconomics</a></div>
  </div>
</div>
<div class="row">
  <div class="card">
    <div class="lbl">Fed Funds</div>
    <div class="val" style="font-size:17px;">{d.get("fed_rate","N/A")}</div>
    <div class="src-line"><a href="https://www.federalreserve.gov" target="_blank">Fed Reserve</a></div>
  </div>
  <div class="card">
    <div class="lbl">RBI Repo</div>
    <div class="val" style="font-size:17px;">{d.get("rbi_rate","N/A")}</div>
    <div class="src-line"><a href="https://www.rbi.org.in" target="_blank">RBI</a></div>
  </div>
</div>
<div class="row">
  <div class="card">
    <div class="lbl">Brent Crude</div>
    <div class="val">${d.get("brent_close","N/A")}</div>
    <div class="chg">{d.get("brent_chg","N/A")}</div>
    <div class="src-line"><a href="https://tradingeconomics.com/commodity/brent-crude-oil" target="_blank">TradingEconomics</a></div>
  </div>
  <div class="card">
    <div class="lbl">MCX Gold (proxy)</div>
    <div class="val-md">{d.get("gold_inr","N/A")}</div>
    <div class="chg">{d.get("gold_chg","N/A")}</div>
    <div class="src-line"><a href="https://www.mcxindia.com" target="_blank">MCX India</a></div>
  </div>
</div>

<div class="sec-hdr slate"><span class="sec-num">03</span> MACRO</div>
<div class="sub-lbl">Key Developments — Last 24 Hours</div>
{stories_html}

<div class="ftr">
  <strong>Standard Chartered Financial Markets — India FM Sales Desk</strong><br>
  Daily Snapshot · {d.get("date","")} · Generated {d.get("generated_at","")}<br>
  Data: <a href="https://finance.yahoo.com" target="_blank">Yahoo Finance</a> · <a href="https://fred.stlouisfed.org" target="_blank">FRED</a> · <a href="https://www.rbi.org.in" target="_blank">RBI</a> · Macro stories: Gemini AI + Google Search<br>
  <span style="color:#c0392b;">⚠ Policy rates are static — update if changed. MCX Gold is indicative.</span>
</div>

</div>
</body>
</html>'''
