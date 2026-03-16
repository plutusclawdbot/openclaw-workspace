#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

WORKSPACE = Path(__file__).resolve().parents[1]
TMP_ROOT = WORKSPACE / "tmp" / "market-brief"
RUN_DIR: Path | None = None
OUT_DIR = WORKSPACE
CT_LIST_ID = "1933193197817135501"


def london_now() -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("Europe/London"))
    except Exception:
        return dt.datetime.utcnow()


def ensure_dirs() -> None:
    global RUN_DIR
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    if RUN_DIR is None:
        timestamp = london_now().strftime("%Y%m%d-%H%M%S")
        RUN_DIR = Path(tempfile.mkdtemp(prefix=f"run-{timestamp}-", dir=str(TMP_ROOT)))


def run(cmd: list[str], timeout: int = 25) -> str:
    return subprocess.check_output(cmd, text=True, cwd=str(WORKSPACE), timeout=timeout)


def fetch_json(url: str, timeout: int = 8) -> Any:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_text(url: str, timeout: int = 8) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def safe_fetch_text(url: str, default: str = "") -> str:
    try:
        return fetch_text(url)
    except Exception:
        return default


def safe_fetch_json(url: str, default: Any = None) -> Any:
    try:
        return fetch_json(url)
    except Exception:
        return default


def pct(curr: float | None, prev: float | None) -> float | None:
    if curr is None or prev in (None, 0):
        return None
    return ((curr / prev) - 1.0) * 100.0


def fmt_num(x: float | None, digits: int = 2) -> str:
    if x is None:
        return "n/a"
    return f"{x:.{digits}f}"


def save_json(name: str, payload: Any) -> None:
    if RUN_DIR is None:
        ensure_dirs()
    assert RUN_DIR is not None
    (RUN_DIR / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def save_text(name: str, payload: str) -> None:
    if RUN_DIR is None:
        ensure_dirs()
    assert RUN_DIR is not None
    (RUN_DIR / name).write_text(payload, encoding="utf-8")


@dataclass
class Quote:
    symbol: str
    price: float | None
    prev: float | None

    @property
    def move_pct(self) -> float | None:
        return pct(self.price, self.prev)


def yahoo_quote(symbol: str) -> Quote:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
    data = safe_fetch_json(url, default=None)
    if not data:
        return Quote(symbol=symbol, price=None, prev=None)
    try:
        meta = data["chart"]["result"][0]["meta"]
        return Quote(symbol=symbol, price=meta.get("regularMarketPrice"), prev=meta.get("chartPreviousClose"))
    except Exception:
        return Quote(symbol=symbol, price=None, prev=None)


def treasury_quote(symbol: str) -> float | None:
    q = yahoo_quote(symbol)
    if q.price is None:
        return None
    try:
        return float(q.price)
    except Exception:
        return None


def fred_last(series: str, start: str) -> list[dict[str, str]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={start}"
    text = safe_fetch_text(url, default="")
    if not text.strip():
        return []
    rows = list(csv.DictReader(text.splitlines()))
    rows = [r for r in rows if r.get(series) not in (None, "", ".")]
    return rows[-5:]


def get_market_snapshot() -> dict[str, Any]:
    symbols = [
        "CL=F", "BZ=F", "DX-Y.NYB", "EURUSD=X", "GBPUSD=X", "USDJPY=X",
        "HG=F", "GC=F", "BTC-USD", "ETH-USD", "^VIX", "^GSPC", "^NDX", "^RUT",
        "HYG", "LQD", "TLT", "IEF", "XLF", "XLE", "SMH", "^IRX", "^FVX", "^TNX"
    ]
    quotes = {s: yahoo_quote(s).__dict__ for s in symbols}
    fred = {
        "DGS2": fred_last("DGS2", "2026-02-20"),
        "DGS10": fred_last("DGS10", "2026-02-20"),
        "T10YIE": fred_last("T10YIE", "2026-02-20"),
        "BAMLH0A0HYM2": fred_last("BAMLH0A0HYM2", "2026-02-20"),
        "BAMLC0A0CM": fred_last("BAMLC0A0CM", "2026-02-20"),
        "DTWEXBGS": fred_last("DTWEXBGS", "2026-02-20"),
    }
    treasury_fallback = {
        "DGS2": treasury_quote("^FVX"),
        "DGS10": treasury_quote("^TNX"),
        "DGS3MO": treasury_quote("^IRX"),
    }
    payload = {"quotes": quotes, "fred": fred, "treasury_fallback": treasury_fallback}
    save_json("market_snapshot.json", payload)
    return payload


def get_polymarket() -> dict[str, Any]:
    all_events = []
    for offset in range(0, 5000, 500):
        out = run(["polymarket", "-o", "json", "events", "list", "--active", "true", "--closed", "false", "--limit", "500", "--offset", str(offset)])
        all_events.extend(json.loads(out))
    seen = {}
    for ev in all_events:
        seen[ev["id"]] = ev
    events = []
    for ev in seen.values():
        liq = float(ev.get("liquidity") or 0)
        v24 = float(ev.get("volume24hr") or 0)
        vtot = float(ev.get("volume") or 0)
        if liq >= 500000:
            events.append({**ev, "liq": liq, "v24": v24, "vtot": vtot})
    events.sort(key=lambda x: x["v24"], reverse=True)
    top = events[:10]
    enriched = []
    for ev in top:
        detail = json.loads(run(["polymarket", "-o", "json", "events", "get", str(ev["id"])]))
        options = []
        for m in detail.get("markets") or []:
            op = m.get("outcomePrices")
            if isinstance(op, str):
                try:
                    op = json.loads(op)
                except Exception:
                    op = []
            yes = float((op or [0])[0]) * 100.0 if op else 0.0
            options.append({"question": m.get("question"), "yes": yes})
        options.sort(key=lambda x: x["yes"], reverse=True)
        enriched.append({
            "title": detail.get("title"),
            "id": detail.get("id"),
            "slug": detail.get("slug"),
            "volume": float(detail.get("volume") or 0),
            "top_options": options[:3],
        })
    payload = {"top_events": enriched}
    save_json("polymarket_top_events.json", payload)
    return payload


def get_ct() -> dict[str, Any]:
    raw = run(["twitter", "list", CT_LIST_ID, "--max", "100", "--yaml"])
    save_text("ct_100.yaml", raw)
    try:
        import yaml  # type: ignore
    except Exception:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "pyyaml"], check=False, cwd=str(WORKSPACE))
        import yaml  # type: ignore
    obj = yaml.safe_load(raw)
    posts = obj.get("data", [])
    bull_terms = [r"\blong\b", r"\bbull", r"risk-on", r"breakout", r"rally", r"higher", r"strong accumulation", r"bounce"]
    bear_terms = [r"\bshort\b", r"\bbear", r"risk-off", r"sell", r"downside", r"war", r"underpricing", r"liquidation", r"dump"]
    theme_patterns = {
        "oil": [r"\boil\b", r"\bcrude\b", r"\bbrent\b", r"\bwti\b", r"hormuz", r"energy"],
        "fed": [r"\bfed\b", r"powell", r"cuts?", r"rates?", r"sep", r"fomc"],
        "ai_semis": [r"\bai\b", r"semis?", r"nvda", r"nvidia", r"smh"],
        "crypto": [r"\bbtc\b", r"\beth\b", r"crypto", r"hyperliquid", r"\$hype\b", r"sol\b"],
        "geopolitics": [r"iran", r"israel", r"war", r"missile", r"strike", r"middle east"],
    }
    counts = {"bullish": 0, "bearish": 0, "neutral": 0}
    bulls: list[dict[str, str]] = []
    bears: list[dict[str, str]] = []
    hype_posts: list[dict[str, str]] = []
    theme_counts = {k: 0 for k in theme_patterns}
    theme_examples = {k: [] for k in theme_patterns}
    for p in posts:
        text = (p.get("text") or "")
        lower = text.lower()
        author = ((p.get("author") or {}).get("screenName") or "")
        bull = sum(1 for t in bull_terms if re.search(t, lower))
        bear = sum(1 for t in bear_terms if re.search(t, lower))
        if re.search(r"\b(hype|hyperliquid|\$hype)\b", lower):
            hype_posts.append({"author": author, "text": text})
        for theme, patterns in theme_patterns.items():
            if any(re.search(pattern, lower) for pattern in patterns):
                theme_counts[theme] += 1
                if len(theme_examples[theme]) < 3:
                    theme_examples[theme].append({"author": author, "text": text[:280]})
        row = {"author": author, "text": text}
        if bull > bear and bull > 0:
            counts["bullish"] += 1
            bulls.append(row)
        elif bear > bull and bear > 0:
            counts["bearish"] += 1
            bears.append(row)
        else:
            counts["neutral"] += 1
    ranked_themes = sorted(theme_counts.items(), key=lambda kv: kv[1], reverse=True)
    payload = {
        "counts": counts,
        "bulls": bulls[:12],
        "bears": bears[:12],
        "hype_posts": hype_posts[:12],
        "theme_counts": theme_counts,
        "top_themes": [{"theme": theme, "count": count, "examples": theme_examples[theme]} for theme, count in ranked_themes[:4] if count > 0],
    }
    save_json("ct_analysis.json", payload)
    return payload


def get_podcast() -> dict[str, Any]:
    payload = {"title_hint": None, "raw_found": False, "summary": None}
    try:
        proc = subprocess.run(
            [
                "ai-summary",
                "https://podcasts.apple.com/gb/podcast/all-in-with-chamath-jason-sacks-friedberg/id1502871393",
                "--length", "short",
                "--timeout", "25s",
                "--plain",
            ],
            text=True,
            cwd=str(WORKSPACE),
            capture_output=True,
            timeout=30,
            check=False,
        )
        if proc.returncode == 0:
            text = (proc.stdout or "").strip()
            payload["summary"] = text[:3000] if text else None
            m = re.search(r"Rewriting the Rules:[^\n]{0,240}", text)
            if m:
                payload["title_hint"] = m.group(0).strip()
                payload["raw_found"] = True
            elif text:
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                candidates = []
                for line in lines[:8]:
                    lower = line.lower()
                    if "apple podcasts" in lower or "presents \"all-in\"" in lower or "weekly talk show" in lower:
                        continue
                    if line.startswith("http://") or line.startswith("https://"):
                        continue
                    candidates.append(line)
                if candidates:
                    payload["title_hint"] = candidates[0][:240]
                    payload["raw_found"] = True
    except Exception:
        pass
    save_json("podcast_signal.json", payload)
    return payload


def build_brief(snapshot: dict[str, Any], poly: dict[str, Any], ct: dict[str, Any], podcast: dict[str, Any]) -> str:
    now = london_now().strftime("%Y-%m-%d %H:%M")
    q = snapshot["quotes"]
    fred = snapshot["fred"]
    treasury_fallback = snapshot.get("treasury_fallback") or {}

    def qv(sym: str) -> tuple[float | None, float | None]:
        item = q[sym]
        return item.get("price"), item.get("prev")

    def mv(sym: str) -> float | None:
        p, prev = qv(sym)
        return pct(p, prev)

    def fred_value(series: str) -> float | None:
        rows = fred.get(series) or []
        if not rows:
            return None
        value = rows[-1].get(series)
        if value in (None, "", "."):
            return None
        try:
            return float(value)
        except Exception:
            return None

    def fmt_pct_or_na(x: float | None, digits: int = 2) -> str:
        if x is None:
            return "n/a"
        return f"{x:.{digits}f}%"

    def move_text(sym: str, digits: int = 2) -> str:
        move = mv(sym)
        if move is None:
            return "n/a"
        sign = "+" if move >= 0 else ""
        return f"{sign}{move:.{digits}f}%"

    dgs2 = fred_value("DGS2")
    dgs10 = fred_value("DGS10")
    t10 = fred_value("T10YIE")
    hy = fred_value("BAMLH0A0HYM2")
    ig = fred_value("BAMLC0A0CM")
    if dgs2 is None:
        fallback_2y = treasury_fallback.get("DGS2")
        if fallback_2y is not None:
            dgs2 = fallback_2y
    if dgs10 is None:
        fallback_10y = treasury_fallback.get("DGS10")
        if fallback_10y is not None:
            dgs10 = fallback_10y

    bullish = ct["counts"]["bullish"]
    bearish = ct["counts"]["bearish"]
    neutral = ct["counts"]["neutral"]
    total = bullish + bearish + neutral

    oil_up = (mv("CL=F") or 0) > 3 or (mv("BZ=F") or 0) > 3
    usd_firm = (mv("DX-Y.NYB") or 0) > 0
    vix_level = q["^VIX"].get("price")
    vix_hot = (vix_level or 0) >= 22
    semis_rel = (mv("SMH") or 0) >= (mv("^GSPC") or -999)

    confidence_reasons: list[str] = []
    if oil_up:
        confidence_reasons.append("oil is confirming the geopolitical inflation impulse")
    if usd_firm:
        confidence_reasons.append("USD strength is reinforcing tighter financial conditions")
    if vix_hot:
        confidence_reasons.append("volatility is elevated, so path-dependency is high")
    if dgs2 is None or dgs10 is None:
        confidence_reasons.append("rates data is partially degraded, lowering precision")
    confidence_line = "; ".join(confidence_reasons[:3]) if confidence_reasons else "signal is mixed across assets"

    what_changed = []
    if oil_up:
        what_changed.append(f"Oil repriced sharply higher (WTI {fmt_num(q['CL=F']['price'])}, {move_text('CL=F')}; Brent {fmt_num(q['BZ=F']['price'])}, {move_text('BZ=F')}).")
    if usd_firm:
        what_changed.append(f"The dollar firmed (DXY proxy {fmt_num(q['DX-Y.NYB']['price'])}, {move_text('DX-Y.NYB')}).")
    if vix_hot:
        what_changed.append(f"Volatility stayed elevated (VIX {fmt_num(vix_level)}), which argues against complacent beta." )
    if semis_rel:
        what_changed.append("Leadership is still concentrated in semis/AI rather than broad index breadth.")
    if not what_changed:
        what_changed.append("Cross-asset moves were mixed, with no clean regime break outside headline-sensitive assets.")

    expression_lines = [
        "- **Own:** energy, defense, selective AI/semis leadership.",
        "- **Hedge with:** gold / commodity exposure rather than relying only on long duration.",
        "- **Avoid / fade:** long duration, small caps, low-quality cyclicals unless oil reverses lower.",
    ]
    if dgs2 is not None and dgs10 is not None:
        expression_lines.append(f"- **Rates context:** UST 2Y {fmt_pct_or_na(dgs2)} / 10Y {fmt_pct_or_na(dgs10)} keeps the burden on duration.")

    change_view_lines = [
        "- **Bullish risk reset:** genuine Middle East de-escalation and oil cooling back below current breakout levels.",
        "- **Policy relief:** Powell leans balanced/dovish instead of validating the inflation shock.",
        "- **Tape confirmation:** breadth improves beyond semis/AI and credit stops leaking.",
        "- **Bearish confirmation:** oil extends higher and credit spreads start confirming equity weakness.",
    ]

    catalyst_lines = [
        "- **Wednesday:** FOMC decision, SEP, Powell.",
        "- **Thursday:** ECB communication.",
        "- **Ongoing:** Middle East / Hormuz headlines, Treasury auctions, Nvidia GTC / AI complex.",
    ]

    supporting_data = []
    supporting_data.append(f"- **Equities:** S&P {fmt_num(q['^GSPC']['price'])} ({move_text('^GSPC')}), NDX {fmt_num(q['^NDX']['price'])} ({move_text('^NDX')}), Russell {fmt_num(q['^RUT']['price'])} ({move_text('^RUT')}).")
    supporting_data.append(f"- **FX:** EURUSD {fmt_num(q['EURUSD=X']['price'], 4)}, GBPUSD {fmt_num(q['GBPUSD=X']['price'], 4)}, USDJPY {fmt_num(q['USDJPY=X']['price'], 3)}.")
    supporting_data.append(f"- **Commodities:** Gold {fmt_num(q['GC=F']['price'])} ({move_text('GC=F')}), Copper {fmt_num(q['HG=F']['price'])} ({move_text('HG=F')}).")
    supporting_data.append(f"- **Credit proxies:** HYG {fmt_num(q['HYG']['price'])} ({move_text('HYG')}), LQD {fmt_num(q['LQD']['price'])} ({move_text('LQD')}), TLT {fmt_num(q['TLT']['price'])} ({move_text('TLT')}).")
    supporting_data.append(f"- **Crypto:** BTC {fmt_num(q['BTC-USD']['price'])} ({move_text('BTC-USD')}), ETH {fmt_num(q['ETH-USD']['price'])} ({move_text('ETH-USD')}).")
    if dgs2 is not None or dgs10 is not None or t10 is not None or hy is not None or ig is not None:
        rates_bits = []
        if dgs2 is not None:
            rates_bits.append(f"2Y {fmt_pct_or_na(dgs2)}")
        if dgs10 is not None:
            rates_bits.append(f"10Y {fmt_pct_or_na(dgs10)}")
        if t10 is not None:
            rates_bits.append(f"10Y breakeven {fmt_pct_or_na(t10)}")
        if hy is not None:
            rates_bits.append(f"HY OAS {fmt_pct_or_na(hy)}")
        if ig is not None:
            rates_bits.append(f"IG OAS {fmt_pct_or_na(ig)}")
        supporting_data.append(f"- **Rates / spreads:** {', '.join(rates_bits)}.")

    ct_lines = []
    if total:
        ct_lines.append(
            f"- **Sentiment split:** {round(bullish/total*100)}% bullish / {round(bearish/total*100)}% bearish / {round(neutral/total*100)}% neutral."
        )
    top_themes = ct.get("top_themes") or []
    if top_themes:
        theme_summary = ", ".join(f"{item['theme']} ({item['count']})" for item in top_themes[:3])
        ct_lines.append(f"- **Dominant CT themes:** {theme_summary}.")
        lead_theme = top_themes[0]["theme"]
        if lead_theme in ("oil", "geopolitics"):
            ct_lines.append("- **Read-through:** CT is focused on geopolitics / energy, which aligns with the macro tape rather than fighting it.")
        elif lead_theme == "ai_semis":
            ct_lines.append("- **Read-through:** CT is still clustered around AI/semis leadership, reinforcing the narrow-breadth regime.")
        elif lead_theme == "crypto":
            ct_lines.append("- **Read-through:** CT attention is skewing toward crypto, so watch for divergence versus macro risk assets.")
        else:
            ct_lines.append("- **Read-through:** CT is cautious/neutral overall, which supports a fragile market rather than a washed-out capitulation low.")
    else:
        ct_lines.append("- **Read-through:** CT is cautious/neutral overall, which supports a fragile market rather than a washed-out capitulation low.")
    if len(ct.get("hype_posts") or []) > 0:
        ct_lines.append(f"- **Crypto chatter:** Hyperliquid / HYPE mentions were limited ({len(ct['hype_posts'])}), so this isn’t a broad speculative blow-off signal.")

    poly_lines = []
    macro_events = []
    for ev in poly.get("top_events", []):
        title = (ev.get("title") or "").lower()
        if any(term in title for term in ["fed", "rate", "inflation", "recession", "oil", "war", "israel", "iran", "gdp", "cpi", "jobs"]):
            event_options = [str(opt.get("question") or "").lower() for opt in ev.get("top_options", [])]
            stale_markers = ["march 1", "march 4", "yesterday", "already happened", "resolved"]
            if any(marker in opt for marker in stale_markers for opt in event_options):
                continue
            if any(re.search(r"on march \d{1,2}", opt) for opt in event_options):
                continue
            macro_events.append(ev)
    for ev in macro_events[:3]:
        poly_lines.append(f"- **{ev['title']}** (${int(ev['volume']):,})")
        for opt in ev["top_options"][:2]:
            poly_lines.append(f"  - {opt['question']} | {opt['yes']:.2f}%")

    podcast_line = "- No material market-relevant podcast signal today."
    if podcast.get("raw_found"):
        podcast_line = f"- Latest All-In signal worth a glance: **{podcast.get('title_hint')}**"

    bottom_line = "Stay pro-energy / defense / AI leaders and underweight duration until oil cools or Powell meaningfully offsets the inflation shock."

    pm_lines = [
        "## PM Memo",
        f"- **Regime:** late-cycle slowdown with a fresh geopolitical / inflation impulse.",
        f"- **What changed:** {' '.join(what_changed)}",
        "- **Best expression:** own energy / defense / selective AI-semis leadership; hedge with gold / commodities; avoid over-owning duration and low-quality beta.",
        "- **What changes the view:** de-escalation + cooler oil + better breadth flips this more constructive; higher oil + weaker credit keeps it defensive.",
        "- **Catalysts:** Wednesday FOMC / SEP / Powell, Thursday ECB, plus Middle East headlines, Treasury auctions, and Nvidia GTC.",
    ]

    expanded_lines = [
        "## Expanded View",
        "### Regime",
        "- **Base case:** late-cycle slowdown with a fresh geopolitical / inflation impulse.",
        "- **Core read:** oil is tightening financial conditions faster than growth is breaking.",
        f"- **Confidence:** **Medium** — {confidence_line}.",
        "",
        "### Why This Isn’t A Full Risk-Off Accident Yet",
        "- Credit looks weak, but not disorderly enough to call this a systemic break.",
        "- Leadership is narrow, but semis/AI are still holding up better than broad beta.",
        "- The reset is being driven by oil and policy sensitivity, not a full collapse in growth expectations.",
        "",
        "### Best Expression",
        *expression_lines,
        "",
        "### What Changes The View",
        *change_view_lines,
        "",
        "### Supporting Data",
        *supporting_data,
        "",
        "### Positioning / Flow",
        "- Consensus came in leaning softer inflation / easier Fed; higher oil is forcing a reset.",
        "- This still looks like a correction regime, not a systemic credit accident.",
        *ct_lines,
    ]

    trade_lines = [
        "## Trade",
        "### Setup",
        "- **Primary view:** stay pro-energy / defense / selective AI leaders, underweight duration and low-quality beta.",
        f"- **Macro driver:** oil shock remains live (WTI {fmt_num(q['CL=F']['price'])}, Brent {fmt_num(q['BZ=F']['price'])}) into Powell.",
        f"- **Rates backdrop:** 2Y {fmt_pct_or_na(dgs2)}, 10Y {fmt_pct_or_na(dgs10)}." if (dgs2 is not None or dgs10 is not None) else "- **Rates backdrop:** partially degraded; use price action in TLT/LQD/HYG as confirmation.",
        "",
        "### Expression",
        "- **Longs:** energy, defense, AI/semis leaders on relative strength.",
        "- **Hedges:** gold / commodity exposure; keep duration hedges smaller than usual.",
        "- **Avoid / short bias:** small caps, low-quality cyclicals, passive index beta if oil keeps climbing.",
        "",
        "### Triggers",
        "- **Add risk:** de-escalation headlines + breadth repair beyond semis.",
        "- **Cut risk:** oil extends higher and credit starts confirming stress.",
        "- **Don’t fight Powell:** if Fed hold comes with hawkish spillover language, stay defensive.",
        "",
        "### Levels / Tape",
        f"- **Oil:** WTI {fmt_num(q['CL=F']['price'])} ({move_text('CL=F')}), Brent {fmt_num(q['BZ=F']['price'])} ({move_text('BZ=F')}).",
        f"- **Equities:** S&P {fmt_num(q['^GSPC']['price'])} ({move_text('^GSPC')}), NDX {fmt_num(q['^NDX']['price'])} ({move_text('^NDX')}), SMH {fmt_num(q['SMH']['price'])} ({move_text('SMH')}).",
        f"- **Credit:** HYG {fmt_num(q['HYG']['price'])} ({move_text('HYG')}), LQD {fmt_num(q['LQD']['price'])} ({move_text('LQD')}), TLT {fmt_num(q['TLT']['price'])} ({move_text('TLT')}).",
    ]

    lines = [
        f"Generated: {now} (Europe/London)",
        "",
        "# Daily Market Brief",
        f"**Bottom line:** {bottom_line}",
        "",
        *pm_lines,
        "",
        *expanded_lines,
        "",
        *trade_lines,
    ]

    if poly_lines:
        lines.extend([
            "",
            "## Prediction Market Check",
            *poly_lines,
            "- Takeaway: Fed/no-change is consensus; the surprise variable is tone, spillover, and oil persistence — not the hold itself.",
        ])

    lines.extend([
        "",
        "## Podcast Signal Check",
        podcast_line,
        "",
        "## Data Notes",
        "- Weak or unavailable series are suppressed where possible instead of being forced into the note.",
        "- Source set: Yahoo Finance chart API, FRED, CT list pull, Polymarket, podcast summarization.",
    ])

    return "\n".join(lines) + "\n"


def main() -> None:
    ensure_dirs()
    try:
        print('[1/5] market snapshot...', file=sys.stderr, flush=True)
        snapshot = get_market_snapshot()
        print('[2/5] polymarket...', file=sys.stderr, flush=True)
        poly = get_polymarket()
        print('[3/5] ct...', file=sys.stderr, flush=True)
        ct = get_ct()
        print('[4/5] podcast...', file=sys.stderr, flush=True)
        podcast = get_podcast()
        print('[5/5] render...', file=sys.stderr, flush=True)
        brief = build_brief(snapshot, poly, ct, podcast)
        date_str = london_now().strftime("%Y-%m-%d")
        out = OUT_DIR / f"market-overview-{date_str}.md"
        out.write_text(brief, encoding="utf-8")
        if RUN_DIR is not None and RUN_DIR.exists():
            shutil.rmtree(RUN_DIR, ignore_errors=True)
        print(str(out))
        print()
        print(brief)
    except Exception as e:
        debug_dir = RUN_DIR if RUN_DIR is not None else TMP_ROOT
        print(f"Run failed; temporary debug artifacts kept at: {debug_dir}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
