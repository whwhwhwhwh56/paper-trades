"""Write data/prices.json: one quote per ticker on the paper book.

Primary source: Massive (api.massive.com) v3 universal snapshot, using the key in
MASSIVE_API_KEY (a GitHub Actions secret in CI; locally the environment or the
MCP config in ~/.claude.json, same lookup as the universe screen).  Fallback per
ticker: Yahoo's keyless v8 chart endpoint, which also covers non-US listings via
the optional "yahoo_symbol" field on a trade or watchlist row.

The key never reaches the page: the browser reads only this file.
"""
import json, os, sys, time, urllib.request, urllib.parse, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BOOK = os.path.join(HERE, "data", "portfolio.json")
OUT = os.path.join(HERE, "data", "prices.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) serene-paper-book/1.0"}


def massive_key():
    k = os.environ.get("MASSIVE_API_KEY")
    if k:
        return k
    path = os.path.join(os.path.expanduser("~"), ".claude.json")
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    found = []

    def walk(node):
        if isinstance(node, dict):
            for key, val in node.items():
                if key == "mcpServers" and isinstance(val, dict):
                    for cfg in val.values():
                        env = (cfg or {}).get("env") or {}
                        if env.get("MASSIVE_API_KEY"):
                            found.append(env["MASSIVE_API_KEY"])
                else:
                    walk(val)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return found[0] if found else None


def get_json(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.load(r)


def iso_from_ns(ns):
    try:
        return datetime.datetime.fromtimestamp(int(ns) / 1e9, datetime.timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return None


def massive_quotes(tickers, key):
    out = {}
    for i in range(0, len(tickers), 100):
        chunk = tickers[i:i + 100]
        url = "https://api.massive.com/v3/snapshot?" + urllib.parse.urlencode({"ticker.any_of": ",".join(chunk), "limit": 250, "apiKey": key})
        for attempt in range(3):
            try:
                d = get_json(url)
                break
            except Exception as exc:
                if attempt == 2:
                    print("massive failed:", exc, file=sys.stderr)
                    d = {}
                time.sleep(2 ** attempt)
        for r in d.get("results", []):
            s = r.get("session") or {}
            reg = s.get("close")
            latest = s.get("price") or reg
            if reg is None and latest is None:
                continue
            open_now = r.get("market_status") == "open"
            out[r["ticker"]] = {
                "price": latest if open_now else (reg if reg is not None else latest),
                "ext": None if open_now else latest,
                "prev": s.get("previous_close"),
                "name": r.get("name"),
                "ccy": "USD",
                "mkt": r.get("market_status"),
                "asof": iso_from_ns(s.get("last_updated")) or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "provider": "massive",
            }
    return out


def yahoo_quote(sym):
    try:
        d = get_json("https://query1.finance.yahoo.com/v8/finance/chart/%s?range=1d&interval=1d" % urllib.parse.quote(sym))
        m = d["chart"]["result"][0]["meta"]
        p = m.get("regularMarketPrice")
        if p is None:
            return None
        ts = m.get("regularMarketTime")
        return {"price": p, "ext": None, "prev": m.get("chartPreviousClose") or m.get("previousClose"), "name": m.get("longName") or m.get("shortName"),
                "ccy": m.get("currency"), "mkt": None,
                "asof": datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat(timespec="seconds") if ts else None,
                "provider": "yahoo"}
    except Exception as exc:
        print("yahoo %s failed: %s" % (sym, exc), file=sys.stderr)
        return None


def main():
    book = json.load(open(BOOK, encoding="utf-8")) if os.path.exists(BOOK) else {}
    rows = list(book.get("trades", [])) + list(book.get("watchlist", []))
    extra = [t.upper() for t in sys.argv[1:]]
    tickers, ysym = [], {}
    for r in rows:
        tk = r["ticker"].upper()
        if tk not in tickers:
            tickers.append(tk)
        if r.get("yahoo_symbol"):
            ysym[tk] = r["yahoo_symbol"]
    for tk in extra:
        if tk not in tickers:
            tickers.append(tk)
    prices = {}
    key = massive_key()
    if key and tickers:
        prices = massive_quotes([t for t in tickers if t not in ysym], key)
    elif tickers:
        print("no MASSIVE_API_KEY; using Yahoo for everything", file=sys.stderr)
    for tk in tickers:
        if tk in prices:
            continue
        q = yahoo_quote(ysym.get(tk, tk.replace(".", "-")))
        if q:
            prices[tk] = q
    old = {}
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT, encoding="utf-8")).get("prices", {})
        except Exception:
            pass
    for tk in tickers:  # keep the last good quote rather than dropping a ticker
        if tk not in prices and tk in old:
            prices[tk] = dict(old[tk], stale=True)
    snap = {"asof": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "source": "massive" if key else "yahoo", "count": len(prices), "prices": prices}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=1, sort_keys=True)
        f.write("\n")
    print("%d of %d tickers priced via %s -> %s" % (len(prices), len(tickers), snap["source"], OUT))


if __name__ == "__main__":
    main()
