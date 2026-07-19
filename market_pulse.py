#!/usr/bin/env python3
"""
market_pulse.py: the Market Pulse data desk. Free, keyless market context, explained honestly.

Fetches five independent, keyless sources at build time and writes site/data/pulse.json,
which site_build.py renders as the "Market Pulse" page:

  1. Fear & Greed Index        alternative.me          crowd sentiment gauge + 90d history
  2. Price history             CoinGecko (keyless)     365d daily closes for the majors ->
                               RSI-14, MACD(12,26,9), 50/200-day SMAs, 12-month-high
                               distance, 30d realized volatility. All stdlib arithmetic.
  3. Stablecoin supply         DefiLlama (keyless)     total USD-pegged float: crypto's
                               dry powder, current + 30d change + 1y trend
  4. Perp leverage             OKX (Deribit fallback)  funding (current + history), open
                               interest (current + 30d trend), long/short ratio, and
                               recent liquidations: how crowded the bets are
  5. Whole market              CoinGecko /global       total cap + Bitcoin dominance
  6. ETF flows                 Farside Investors       daily US spot BTC/ETH ETF net flows
  7. Bitcoin network           mempool.space           recommended fees + difficulty change

FAIL-OPEN, PER SECTION: each source is fetched independently; a failed source is warned and
omitted while the others still publish. If every source fails, nothing is written and the
previously committed snapshot stands (the site renders whatever sections exist). This is
market DATA, not news: it never touches the editorial pipeline or the human gate, and the
page says so. Like the Whale Watch board, it refreshes at every Netlify build (see
netlify.toml and DEVIATIONS D8).

USAGE
  python3 market_pulse.py            # live fetch -> site/data/pulse.json (+ out/ copy)
"""

import json
import math
import os
import urllib.request
from datetime import datetime, timezone

import common

HERE = os.path.dirname(os.path.abspath(__file__))
SITE_DATA = os.path.join(HERE, "site", "data", "pulse.json")
UA = "CryptoCronkite-MarketPulse/1.0 (+https://gocheckmycrypto.com)"

ASSETS = [("bitcoin", "BTC"), ("ethereum", "ETH"), ("solana", "SOL"), ("ripple", "XRP"),
          ("binancecoin", "BNB"), ("dogecoin", "DOGE"), ("cardano", "ADA")]

# Perp contracts for the leverage desk. OKX's public endpoints are keyless and reachable
# from US build infrastructure (Binance/Bybit geo-block theirs, see DEVIATIONS D9); Deribit
# is the fallback for BTC/ETH. No BNB here: OKX does not list a BNB perp.
LEVERAGE_INSTRUMENTS = [("BTC", "BTC-USDT-SWAP"), ("ETH", "ETH-USDT-SWAP"),
                        ("SOL", "SOL-USDT-SWAP"), ("XRP", "XRP-USDT-SWAP"),
                        ("DOGE", "DOGE-USDT-SWAP")]


def get_json(url, timeout=30, attempts=3):
    """Fetch JSON with polite backoff: keyless CoinGecko rate-limits bursts, so a 429 (or a
    transient 5xx) waits and retries instead of dropping the section."""
    import time
    import urllib.error
    delay = 20
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503):
                raise
            last = e
        except Exception as e:
            last = e
        if i < attempts - 1:
            time.sleep(delay)
            delay *= 2
    raise last


# ---- indicator math (standard definitions, stdlib only) -----------------------

def sma(values, n):
    return sum(values[-n:]) / n if len(values) >= n else None


def ema_series(values, n):
    if len(values) < n:
        return []
    k = 2 / (n + 1)
    out = [sum(values[:n]) / n]  # seed with SMA
    for v in values[n:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rolling_sma(values, n):
    """Full rolling SMA series; result[k] corresponds to values[k + n - 1]."""
    if len(values) < n:
        return []
    out = []
    s = sum(values[:n])
    out.append(s / n)
    for i in range(n, len(values)):
        s += values[i] - values[i - n]
        out.append(s / n)
    return out


def _date_label(ts_seconds):
    return datetime.fromtimestamp(int(ts_seconds), timezone.utc).strftime("%b %d")


def rsi14(closes, n=14):
    if len(closes) < n + 1:
        return None
    gains, losses = [], []
    for a, b in zip(closes[:-1], closes[1:]):
        d = b - a
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:n]) / n
    avg_l = sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):  # Wilder smoothing
        avg_g = (avg_g * (n - 1) + g) / n
        avg_l = (avg_l * (n - 1) + l) / n
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100 - 100 / (1 + rs)


def macd(closes, fast=12, slow=26, signal_n=9):
    if len(closes) < slow + signal_n:
        return None
    ema_f = ema_series(closes, fast)
    ema_s = ema_series(closes, slow)
    line = [f - s for f, s in zip(ema_f[len(ema_f) - len(ema_s):], ema_s)]
    sig = ema_series(line, signal_n)
    if not sig:
        return None
    return {"macd": line[-1], "signal": sig[-1], "hist": line[-1] - sig[-1]}


def realized_vol_30d(closes):
    if len(closes) < 31:
        return None
    rets = [math.log(b / a) for a, b in zip(closes[-31:-1], closes[-30:]) if a > 0]
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(365) * 100


def downsample(values, n=48):
    if len(values) <= n:
        return [round(v, 6) for v in values]
    step = (len(values) - 1) / (n - 1)
    return [round(values[int(i * step)], 6) for i in range(n)]


# ---- sections (each independently fail-open) ----------------------------------

def section_fng():
    d = get_json("https://api.alternative.me/fng/?limit=90")["data"]
    newest = d[0]
    hist = [int(x["value"]) for x in reversed(d)]  # oldest -> newest
    return {"value": int(newest["value"]), "label": newest["value_classification"],
            "history": hist,
            "window": {"start": _date_label(d[-1]["timestamp"]),
                       "end": _date_label(newest["timestamp"])}}


def section_assets():
    import time
    out = []
    for i, (cid, sym) in enumerate(ASSETS):
        if i:
            time.sleep(7)  # keyless CoinGecko dislikes bursts; a build can afford politeness
        d = get_json(f"https://api.coingecko.com/api/v3/coins/{cid}/market_chart"
                     f"?vs_currency=usd&days=365&interval=daily")
        rows = [p for p in d.get("prices", []) if p and p[1]]
        closes = [p[1] for p in rows]
        if len(closes) < 210:
            raise ValueError(f"{sym}: only {len(closes)} daily closes from CoinGecko")
        last = closes[-1]
        hi = max(closes)
        m = macd(closes)
        s50, s200 = sma(closes, 50), sma(closes, 200)
        win = closes[-90:]
        # rolling SMA series sliced to the same 90-day window and downsampled in step with
        # the price spark, so the dashboard can overlay them on one chart
        sma50_win = rolling_sma(closes, 50)[-90:]
        sma200_win = rolling_sma(closes, 200)[-90:]
        out.append({
            # keep cents on cheap coins: $1.10 must not flatten to $1 (4 decimals below $100)
            "symbol": sym, "name": cid, "price": round(last, 2 if last >= 100 else 4),
            "chg_24h_pct": round((last / closes[-2] - 1) * 100, 2),
            "rsi14": round(rsi14(closes), 1),
            "macd_above_signal": bool(m and m["hist"] >= 0),
            "sma50": round(s50, 2), "sma200": round(s200, 2),
            "above_sma200": last >= s200,
            "golden_cross": s50 >= s200,
            "pct_from_high_12m": round((last / hi - 1) * 100, 1),
            "vol30_pct": round(realized_vol_30d(closes), 1),
            "spark": downsample(win, 64),
            "spark_sma50": downsample(sma50_win, 64),
            "spark_sma200": downsample(sma200_win, 64),
            "spark_high": round(max(win), 2), "spark_low": round(min(win), 2),
            "window": {"start": _date_label(rows[-90][0] / 1000),
                       "end": _date_label(rows[-1][0] / 1000)},
        })
    return out


def section_stables():
    d = get_json("https://stablecoins.llama.fi/stablecoincharts/all")
    pts = [(int(p["date"]), (p.get("totalCirculatingUSD") or {}).get("peggedUSD"))
           for p in d if (p.get("totalCirculatingUSD") or {}).get("peggedUSD")]
    pts.sort()
    year_pts = pts[-365:]
    year = [v for _, v in year_pts]
    cur = year[-1]
    prev30 = year[-31] if len(year) > 31 else year[0]
    return {"total_usd": round(cur), "change_30d_pct": round((cur / prev30 - 1) * 100, 2),
            "spark": downsample(year, 64),
            "spark_high": round(max(year)), "spark_low": round(min(year)),
            "window": {"start": _date_label(year_pts[0][0]),
                       "end": _date_label(year_pts[-1][0])}}


def section_movers(top_n=5, universe=100):
    """One call, two boards: the full top-100 price table (with 7-day sparklines) and the
    top gainers/losers derived from it, so micro-cap pump coins never make either board."""
    d = get_json("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd"
                 f"&order=market_cap_desc&per_page={universe}&page=1"
                 "&price_change_percentage=24h&sparkline=true")

    def pack(c, spark=False):
        chg = c.get("price_change_percentage_24h")
        out = {"symbol": (c.get("symbol") or "").upper(), "name": c.get("name") or "",
               "price": c.get("current_price"),
               "chg_24h_pct": round(chg, 2) if chg is not None else None,
               "mcap_usd": c.get("market_cap"), "rank": c.get("market_cap_rank"),
               "gecko_id": c.get("id") or ""}
        if spark:
            pts = ((c.get("sparkline_in_7d") or {}).get("price")) or []
            out["spark7d"] = downsample(pts, 28) if len(pts) >= 2 else []
        return out

    movers = [c for c in d if c.get("price_change_percentage_24h") is not None]
    movers.sort(key=lambda c: c["price_change_percentage_24h"])
    top100 = sorted(d, key=lambda c: (c.get("market_cap_rank") or 999))
    return {"universe": universe,
            "gainers": [pack(c) for c in reversed(movers[-top_n:])],
            "losers": [pack(c) for c in movers[:top_n]],
            "top100": [pack(c, spark=True) for c in top100]}


def section_leverage():
    """The derivatives tape for the majors: funding (current + history), open interest
    (current + 30d trend), the long/short account ratio, and recent liquidations. All from
    OKX's keyless public API (Binance/Bybit geo-block US build infra, DEVIATIONS D9);
    Deribit's public ticker is the BTC/ETH snapshot fallback. Per-asset fail-open inside
    the section; the section publishes if at least one asset resolved."""
    import time
    OKX = "https://www.okx.com/api/v5"
    # contract sizes for liquidation notionals (sz is in contracts, not coins)
    ct_val = {}
    try:
        for inst in get_json(f"{OKX}/public/instruments?instType=SWAP")["data"]:
            ct_val[inst["instId"]] = float(inst.get("ctVal") or 0)
    except Exception as e:
        common.gh("warning", f"market_pulse: leverage instruments lookup failed ({e})")
    out = []
    for i, (sym, inst) in enumerate(LEVERAGE_INSTRUMENTS):
        if i:
            time.sleep(1)  # OKX allows bursts, but a build can afford politeness
        try:
            f = get_json(f"{OKX}/public/funding-rate?instId={inst}")["data"][0]
            o = get_json(f"{OKX}/public/open-interest?instId={inst}")["data"][0]
            rate = float(f["fundingRate"])  # fraction per 8h funding interval
            a = {
                "symbol": sym, "venue": "OKX",
                "funding_8h_pct": round(rate * 100, 4),
                "funding_annual_pct": round(rate * 3 * 365 * 100, 1),
                "next_funding_utc": datetime.fromtimestamp(
                    int(f["fundingTime"]) / 1000, timezone.utc).strftime("%H:%M UTC"),
                "open_interest_usd": round(float(o["oiUsd"])),
            }
            ccy = sym  # rubik stats key by base currency
            try:  # funding history: is the cost of the bet rising or fading?
                hist = get_json(f"{OKX}/public/funding-rate-history?instId={inst}&limit=21")["data"]
                a["funding_history_pct"] = [round(float(h["realizedRate"]) * 100, 4)
                                            for h in reversed(hist)]
            except Exception:
                pass
            try:  # 30d open-interest trend (daily, USD)
                oi = get_json(f"{OKX}/rubik/stat/contracts/open-interest-volume"
                              f"?ccy={ccy}&period=1D")["data"]
                a["oi_history_usd"] = [round(float(x[1])) for x in reversed(oi[:30])]
            except Exception:
                pass
            try:  # long/short account ratio: which way the crowd leans
                ls = get_json(f"{OKX}/rubik/stat/contracts/long-short-account-ratio"
                              f"?ccy={ccy}&period=1D")["data"]
                a["long_short_ratio"] = round(float(ls[0][1]), 2)
                a["long_short_history"] = [round(float(x[1]), 2) for x in reversed(ls[:30])]
            except Exception:
                pass
            try:  # recent liquidations: forced closes, split by side
                liq = get_json(f"{OKX}/public/liquidation-orders?instType=SWAP"
                               f"&state=filled&uly={inst.rsplit('-', 1)[0]}")["data"]
                details = [d for row in liq for d in (row.get("details") or [])]
                cv = ct_val.get(inst, 0)
                if details and cv:
                    longs = [d for d in details if d.get("posSide") == "long"]
                    shorts = [d for d in details if d.get("posSide") == "short"]
                    usd = lambda ds: round(sum(
                        float(d.get("sz") or 0) * cv * float(d.get("bkPx") or 0) for d in ds))
                    oldest = min(int(d.get("ts") or 0) for d in details)
                    hours = max(1, round((time.time() * 1000 - oldest) / 3_600_000))
                    a["liquidations"] = {
                        "window_hours": hours, "count": len(details),
                        "longs_usd": usd(longs), "shorts_usd": usd(shorts),
                    }
            except Exception:
                pass
            out.append(a)
        except Exception as e:
            common.gh("warning", f"market_pulse: leverage {sym} via OKX failed ({e})")
    if not any(a["symbol"] in ("BTC", "ETH") for a in out):
        for sym in ("BTC", "ETH"):
            try:
                d = get_json("https://www.deribit.com/api/v2/public/ticker"
                             f"?instrument_name={sym}-PERPETUAL")["result"]
                out.append({
                    "symbol": sym, "venue": "Deribit",
                    "funding_8h_pct": round(float(d.get("funding_8h", 0)) * 100, 4),
                    "funding_annual_pct": round(float(d.get("funding_8h", 0)) * 3 * 365 * 100, 1),
                    "next_funding_utc": "",
                    "open_interest_usd": round(float(d.get("open_interest", 0))),
                })
            except Exception as e:
                common.gh("warning", f"market_pulse: leverage {sym} via Deribit failed ({e})")
    if not out:
        raise ValueError("no leverage venue reachable")
    return {"assets": out,
            "note": ("Perpetual-swap funding and open interest from public exchange data "
                     "(single-venue snapshots, not market-wide totals).")}


def section_market():
    """The whole-market frame: total cap and Bitcoin dominance, from CoinGecko's keyless
    global endpoint (the same one the browser ticker already calls)."""
    g = get_json("https://api.coingecko.com/api/v3/global")["data"]
    return {
        "total_mcap_usd": round((g.get("total_market_cap") or {}).get("usd", 0)),
        "mcap_change_24h_pct": round(g.get("market_cap_change_percentage_24h_usd") or 0, 2),
        "btc_dominance_pct": round((g.get("market_cap_percentage") or {}).get("btc", 0), 1),
    }


def get_text(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _parse_farside(html):
    """Rows of Farside's flow table: [(date, total_usd_m), ...] oldest->newest, plus the
    cumulative total. HTML scrape, so parse defensively and return nothing on any doubt.
    Farside PRE-PUBLISHES the next trading day as a row of zeros before flows settle, so
    trailing rows where every fund cell is zero/blank are dropped (an all-zero placeholder
    is not a $0 flow day); interior zero days, if any, are kept."""
    import re as _re
    days, cumulative = [], None
    for tr in _re.findall(r"<tr[^>]*>(.*?)</tr>", html, _re.S):
        cells = [_re.sub(r"<[^>]+>", "", c).replace("&nbsp;", " ").strip()
                 for c in _re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, _re.S)]
        if len(cells) < 3:
            continue

        def num(s):
            s = s.replace(",", "").strip()
            neg = s.startswith("(") and s.endswith(")")
            s = s.strip("()")
            try:
                v = float(s)
            except ValueError:
                return None
            return -v if neg else v

        if _re.match(r"^\d{1,2} \w{3} \d{4}$", cells[0]):
            v = num(cells[-1])
            if v is not None:
                fund_vals = [num(c) for c in cells[1:-1]]
                settled = any(fv for fv in fund_vals if fv)
                days.append((cells[0], v, settled))
        elif cells[0] == "Total":
            cumulative = num(cells[-1])
    while days and not days[-1][2]:
        days.pop()
    return [(d, v) for d, v, _ in days], cumulative


def section_etf_flows():
    """Daily US spot-ETF net flows for BTC and ETH from Farside Investors' public tables
    (the flows themselves are the funds' published data). An HTML scrape is brittle by
    nature (DEVIATIONS D12), so any parse doubt drops the board rather than shipping a
    wrong number."""
    import time
    out = {}
    for key, url in (("btc", "https://farside.co.uk/btc/"), ("eth", "https://farside.co.uk/eth/")):
        try:
            days, cumulative = _parse_farside(get_text(url))
            if not days:
                raise ValueError("no parseable flow rows")
            latest_date, latest = days[-1]
            out[key] = {
                "latest_date": latest_date,
                "latest_net_usd_m": round(latest, 1),
                "recent": [{"date": d, "net_usd_m": round(v, 1)} for d, v in days[-10:]],
                "cumulative_usd_m": round(cumulative, 1) if cumulative is not None else None,
            }
        except Exception as e:
            common.gh("warning", f"market_pulse: etf flows ({key}) failed ({e})")
        time.sleep(1)
    if not out:
        raise ValueError("no ETF flow board parsed")
    out["note"] = ("US spot ETF net creations/redemptions in USD millions, as published by "
                   "the funds and tabulated by Farside Investors. Flow data lags a trading "
                   "day and pauses on market holidays.")
    return out


def section_network():
    fees = get_json("https://mempool.space/api/v1/fees/recommended")
    diff = get_json("https://mempool.space/api/v1/difficulty-adjustment")
    return {"fastest_fee": fees.get("fastestFee"), "hour_fee": fees.get("hourFee"),
            "difficulty_change_pct": round(diff.get("difficultyChange", 0), 1),
            "retarget_blocks": diff.get("remainingBlocks")}


def main():
    pulse = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "note": ("Free public market data, computed with standard formulas at build time: "
                 "sentiment from alternative.me, prices from CoinGecko, stablecoin float from "
                 "DefiLlama, Bitcoin network data from mempool.space. Market data, not news, "
                 "not advice."),
    }
    sections = [("fng", section_fng), ("assets", section_assets),
                ("movers", section_movers), ("stables", section_stables),
                ("leverage", section_leverage), ("market", section_market),
                ("etf_flows", section_etf_flows), ("network", section_network)]
    got = 0
    for name, fn in sections:
        try:
            pulse[name] = fn()
            got += 1
        except Exception as e:
            common.gh("warning", f"market_pulse: section '{name}' failed ({e}) -> omitted")
    if got == 0:
        common.gh("warning", "market_pulse: every source failed -> nothing written "
                             "(the previous snapshot stands).")
        return 0
    os.makedirs(os.path.dirname(SITE_DATA), exist_ok=True)
    json.dump(pulse, open(SITE_DATA, "w", encoding="utf-8"), indent=2)
    common.write_out("market_pulse.json", pulse)
    parts = [n for n, _ in sections if n in pulse]
    print(f"market_pulse: {got}/{len(sections)} sections -> {os.path.relpath(SITE_DATA)} "
          f"({', '.join(parts)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
