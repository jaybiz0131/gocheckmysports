#!/usr/bin/env python3
"""
whale_flows.py: follow the money, not the feed.

A scrolling list of individual whale transfers is noise. The signal is the AGGREGATE: are
whales, on net, moving coins ONTO exchanges (which historically precedes selling) or OFF
exchanges into self-custody (accumulation)? This script classifies each large transfer by the
owner_type of its endpoints and rolls them up into a higher-perspective view per asset, plus
the biggest single moves onto exchanges.

DATA comes from Whale Alert's FREE public alert archive (keyless; their old keyed REST API
was retired behind paid plans -- see DEVIATIONS D7). The archive names owners ("binance",
"unknown wallet"), so exchanges are identified by a curated name list in common.py, and only
the very large transfers Whale Alert posts publicly (roughly $50M+) appear.

CLASSIFICATION (owner names matched against common.KNOWN_EXCHANGES):
  wallet/unknown -> exchange   = INFLOW  (money onto an exchange; potential sell pressure)
  exchange -> wallet/unknown   = OUTFLOW (money off an exchange; accumulation / self-custody)
  exchange -> exchange         = INTERNAL (ignored; not directional signal)
  wallet -> wallet             = WALLET  (ignored; no exchange involved)
  net_usd per asset = outflow - inflow   (positive = net leaving exchanges = accumulation)

This is a HEURISTIC and market data, not news and not advice. Exchange labels come from Whale
Alert; unlabeled wallets are treated as non-exchange. The site frames it as such.

OUTPUT
  out/whale_flows.json          full analysis (runtime)
  site/data/flows.json          the snapshot the site renders (a board, refreshed each run)

USAGE
  python3 whale_flows.py                      # live: Whale Alert public archive (no key)
  python3 whale_flows.py --fixture F          # analyze a saved transactions file (tests)
  python3 whale_flows.py --window 24          # lookback hours (default from config)
  python3 whale_flows.py --example            # write the snapshot flagged example (illustrative)
"""

import json
import os
import sys
from datetime import datetime, timezone

import common

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out", "whale_flows.json")
SITE_DATA = os.path.join(HERE, "site", "data", "flows.json")
UA = "CryptoCronkite-WhaleFlows/1.0"


def classify(txn):
    ft = (txn.get("from", {}) or {}).get("owner_type", "")
    tt = (txn.get("to", {}) or {}).get("owner_type", "")
    f_ex, t_ex = ft == "exchange", tt == "exchange"
    if t_ex and not f_ex:
        return "inflow"
    if f_ex and not t_ex:
        return "outflow"
    if f_ex and t_ex:
        return "internal"
    return "wallet"


# Stablecoins invert the signal: a stablecoin moving ONTO an exchange is buying power arriving
# (dry powder), not sell pressure. So we score the sell-pressure/accumulation signal on volatile
# assets only, and report stablecoin exchange inflow separately as incoming buying power.
STABLES = {"USDT", "USDC", "DAI", "BUSD", "TUSD", "FDUSD", "USDE", "PYUSD", "USDD", "GUSD"}


def analyze(txns, window_hours, top_assets=6, top_moves=6, example=False, date=None):
    assets = {}
    vol_in = vol_out = 0.0
    stable_in = stable_out = 0.0
    counted = 0
    inflow_moves = []
    outflow_moves = []
    exchanges = {}
    for t in txns:
        kind = classify(t)
        sym = (t.get("symbol") or "?").upper()
        usd = float(t.get("amount_usd") or 0)
        if kind in ("internal", "wallet"):
            continue
        counted += 1
        is_stable = sym in STABLES
        if kind in ("inflow", "outflow"):
            move = {"symbol": sym, "amount": float(t.get("amount") or 0), "usd": usd,
                    "to": (t.get("to", {}) or {}).get("owner") or (
                        "unknown exchange" if kind == "inflow" else "unknown wallet"),
                    "from": (t.get("from", {}) or {}).get("owner") or (
                        "unknown wallet" if kind == "inflow" else "unknown exchange"),
                    "blockchain": t.get("blockchain", ""), "hash": t.get("hash", ""),
                    "ts": float(t.get("timestamp") or 0), "stable": is_stable}
            (inflow_moves if kind == "inflow" else outflow_moves).append(move)
            # exchange concentration: who is receiving (inflow) or dispensing (outflow)
            ex_name = move["to"] if kind == "inflow" else move["from"]
            e = exchanges.setdefault(ex_name, {"exchange": ex_name,
                                               "inflow_usd": 0.0, "outflow_usd": 0.0})
            e["inflow_usd" if kind == "inflow" else "outflow_usd"] += usd
        if is_stable:
            if kind == "inflow":
                stable_in += usd
            else:
                stable_out += usd
            continue
        # volatile asset: this is the directional sell-pressure / accumulation signal
        a = assets.setdefault(sym, {"symbol": sym, "inflow_usd": 0.0, "outflow_usd": 0.0})
        if kind == "inflow":
            a["inflow_usd"] += usd
            vol_in += usd
        else:
            a["outflow_usd"] += usd
            vol_out += usd

    by_asset = []
    for a in assets.values():
        a["net_usd"] = round(a["outflow_usd"] - a["inflow_usd"])  # + = net off exchanges
        a["inflow_usd"] = round(a["inflow_usd"])
        a["outflow_usd"] = round(a["outflow_usd"])
        by_asset.append(a)
    by_asset.sort(key=lambda x: abs(x["net_usd"]), reverse=True)
    by_asset = by_asset[:top_assets]

    inflow_moves.sort(key=lambda m: m["usd"], reverse=True)
    outflow_moves.sort(key=lambda m: m["usd"], reverse=True)
    by_exchange = []
    for e in exchanges.values():
        e["net_usd"] = round(e["outflow_usd"] - e["inflow_usd"])  # + = net dispensing
        e["inflow_usd"] = round(e["inflow_usd"])
        e["outflow_usd"] = round(e["outflow_usd"])
        by_exchange.append(e)
    by_exchange.sort(key=lambda e: e["inflow_usd"] + e["outflow_usd"], reverse=True)
    net = vol_out - vol_in  # positive = net off exchanges (accumulation)
    direction = "off exchanges" if net >= 0 else "onto exchanges"

    return {
        "example": example,
        "generated": date or "undated",
        "window_hours": window_hours,
        "txn_count": counted,
        "volatile": {
            "inflow_usd": round(vol_in), "outflow_usd": round(vol_out),
            "net_usd": round(net), "direction": direction,
        },
        "stablecoins": {
            "inflow_usd": round(stable_in), "outflow_usd": round(stable_out),
            "net_buying_power_usd": round(stable_in - stable_out),
        },
        "by_asset": by_asset,
        "by_exchange": by_exchange[:5],
        "top_inflows": inflow_moves[:top_moves],
        "top_outflows": outflow_moves[:top_moves],
        "note": ("Data: Whale Alert public alert archive; exchanges identified by name, and only "
                 "the very large transfers Whale Alert posts (roughly $50M+) appear. For volatile "
                 "assets, coins moving onto exchanges can precede selling and coins moving off "
                 "suggests accumulation or self-custody. Stablecoins are the opposite: onto an "
                 "exchange is buying power arriving, so they are scored separately. Market data, "
                 "not news, not advice."),
    }


HISTORY_WEEKS = 13

# The public archive only carries the very largest transfers (~$50M+), so a quiet day can
# leave the configured window with zero exchange-relevant moves. Rather than publish a blank
# board, widen the lookback step by step until something appears, and label the board with
# the window it actually shows (render_flows explains the widening to the reader).
WIDEN_HOURS = (48, 72, 168)


def load_from_archive(cfg, window_hours, max_decompressed_bytes=8_000_000):
    """Pull the window's transfers from Whale Alert's FREE public alert archive (keyless;
    see common.whale_archive_transactions and DEVIATIONS D7). Only transfers count as flow
    signal; mints/burns/freezes are not exchange flows."""
    wa = cfg["sources"].get("whale_alert", {})
    url = wa.get("archive_url", common.WHALE_ARCHIVE_URL)
    txns = common.whale_archive_transactions(window_hours, archive_url=url,
                                             max_decompressed_bytes=max_decompressed_bytes)
    return [t for t in txns if t.get("transaction_type") == "transfer"]


def weekly_history(txns, weeks=HISTORY_WEEKS, now=None):
    """Roll exchange-relevant transfers into 7-day buckets (oldest -> newest): net volatile
    flow (the accumulation/sell-pressure signal, same scoring as the board) plus the count
    of exchange-relevant moves. The trend view for 'have whales been accumulating lately'."""
    import time as _time
    now = now or _time.time()
    buckets = [{"net_usd": 0.0, "moves": 0} for _ in range(weeks)]
    for t in txns:
        age = max(0.0, now - float(t.get("timestamp") or 0))
        idx = int(age // (7 * 24 * 3600))
        if idx >= weeks:
            continue
        kind = classify(t)
        if kind in ("internal", "wallet"):
            continue
        b = buckets[idx]
        b["moves"] += 1
        if (t.get("symbol") or "").upper() in STABLES:
            continue  # stables are scored separately on the board; the trend is volatile-only
        usd = float(t.get("amount_usd") or 0)
        b["net_usd"] += usd if kind == "outflow" else -usd
    out = []
    for i in range(weeks - 1, -1, -1):
        end = datetime.fromtimestamp(now - i * 7 * 24 * 3600, timezone.utc).strftime("%b %d")
        out.append({"week_ending": end, "net_usd": round(buckets[i]["net_usd"]),
                    "moves": buckets[i]["moves"]})
    return out


def run(fixture=None, window=None, example=False):
    cfg = common.load_config()
    window_hours = window or cfg.get("whale_flows", {}).get("window_hours", 24)
    top_assets = cfg.get("whale_flows", {}).get("top_assets", 6)
    top_moves = cfg.get("whale_flows", {}).get("top_moves", 6)

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history = None
    if fixture:
        txns = json.load(open(fixture, encoding="utf-8")).get("transactions", [])
        example = True  # a fixture-derived board is always illustrative
    else:
        try:
            # One archive read covers both views: the last HISTORY_WEEKS of transfers feed
            # the weekly trend, and the freshest window_hours slice feeds the board.
            import time as _time
            txns_hist = load_from_archive(cfg, HISTORY_WEEKS * 7 * 24,
                                          max_decompressed_bytes=32_000_000)
            cutoff = _time.time() - window_hours * 3600
            txns = [t for t in txns_hist if float(t.get("timestamp") or 0) >= cutoff]
            history = weekly_history(txns_hist)
        except Exception as e:
            # Fail-open for the BOARD only: keep the committed snapshot rather than fail a
            # deploy over a market-data hiccup. The news pipeline's gates are unaffected.
            common.gh("warning", f"whale_flows: archive fetch failed ({e}) -> skipping "
                                 f"(no board written; the previous snapshot stands).")
            return 0

    result = analyze(txns, window_hours, top_assets, top_moves, example=example, date=date)
    if not fixture and not result["txn_count"]:
        import time as _time
        for wider in WIDEN_HOURS:
            if wider <= window_hours:
                continue
            cutoff = _time.time() - wider * 3600
            txns = [t for t in txns_hist if float(t.get("timestamp") or 0) >= cutoff]
            result = analyze(txns, wider, top_assets, top_moves, example=example, date=date)
            if result["txn_count"]:
                result["window_widened_from"] = window_hours
                break
        else:
            # Even a week of lookback is empty: keep the committed snapshot rather than
            # overwrite it with a blank board (same fail-open as an archive fetch error).
            common.gh("warning", f"whale_flows: no exchange-relevant transfers in the last "
                                 f"{WIDEN_HOURS[-1]}h -> keeping the previous snapshot.")
            return 0
    if history:
        result["history"] = history
        # baseline: the median week's |net| lets the page say whether the current window
        # is running hot or quiet relative to the last quarter
        import statistics
        abs_nets = sorted(abs(w["net_usd"]) for w in history)
        result["weekly_median_abs_usd"] = round(statistics.median(abs_nets)) if abs_nets else 0
    common.write_out(os.path.basename(OUT), result)
    os.makedirs(os.path.dirname(SITE_DATA), exist_ok=True)
    json.dump(result, open(SITE_DATA, "w", encoding="utf-8"), indent=2)
    tag = " [EXAMPLE]" if result["example"] else ""
    v = result["volatile"]
    print(f"whale_flows{tag}: {result['txn_count']} exchange-relevant transfers, volatile net "
          f"${v['net_usd']:,} {v['direction']}, stablecoin buying power "
          f"${result['stablecoins']['net_buying_power_usd']:,} -> {os.path.relpath(SITE_DATA)}")
    return 0


def main():
    argv = sys.argv[1:]
    fixture = argv[argv.index("--fixture") + 1] if "--fixture" in argv else None
    window = int(argv[argv.index("--window") + 1]) if "--window" in argv else None
    example = "--example" in argv
    sys.exit(run(fixture=fixture, window=window, example=example))


if __name__ == "__main__":
    main()
