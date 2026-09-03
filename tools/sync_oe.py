"""Copy owner-earnings valuations from oe-db/oe.db into data/portfolio.json.

Run from anywhere:  python tools/sync_oe.py [--push] [TICKER ...]

For every ticker on the paper book (trades + watchlist), or the tickers given,
pull the bear/base/bull value per share, margin of safety, anchor owner earnings,
growth rates, gate status and quality profile from the local oe.db and write them
under portfolio.json -> valuations[TICKER] with source "oe.db".  Manual entries
(source "manual") are left alone unless --force is given.

With --push the script does: git pull --rebase, commit, git push, so the public
page picks the values up.  Nothing else in portfolio.json is touched, so browser
edits and this script can coexist.
"""
import json, os, sqlite3, subprocess, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BOOK = os.path.join(ROOT, "data", "portfolio.json")
OE_DB = os.path.abspath(os.path.join(ROOT, "..", "oe-db", "oe.db"))


def fnum(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def load_valuation(con, tk):
    row = con.execute("SELECT name, asof FROM company WHERE ticker=?", (tk,)).fetchone()
    if not row:
        return None
    vals = {s: fnum(v) for s, v in con.execute("SELECT scenario, value_ps FROM valuation WHERE ticker=?", (tk,))}
    if vals.get("BASE") is None:
        return None
    a = {k: v for k, v in con.execute("SELECT key, value FROM assumption WHERE ticker=?", (tk,))}
    g = con.execute("SELECT status, reason, latest_fy, anchor_oe, g_bear, g_base, g_bull, dated FROM gate WHERE ticker=?", (tk,)).fetchone()
    q = con.execute("SELECT profile FROM quality WHERE ticker=?", (tk,)).fetchone()
    return {
        "source": "oe.db",
        "name": row[0],
        "asof": (g[7] if g and g[7] else row[1]) or datetime.date.today().isoformat(),
        "bear": vals.get("BEAR"), "base": vals.get("BASE"), "bull": vals.get("BULL"),
        "mos": fnum(a.get("mos")) if fnum(a.get("mos")) is not None else 0.30,
        "shares": fnum(a.get("shares")), "net_debt": fnum(a.get("net_debt")),
        "anchor_oe": fnum(g[3]) if g else None, "latest_fy": g[2] if g else None,
        "g_bear": fnum(g[4]) if g else fnum(a.get("g_bear")),
        "g_base": fnum(g[5]) if g else fnum(a.get("g_base")),
        "g_bull": fnum(g[6]) if g else fnum(a.get("g_bull")),
        "gate": g[0] if g else None, "gate_reason": g[1] if g else None,
        "profile": q[0] if q else None,
        "synced": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }


def main(argv):
    push = "--push" in argv
    force = "--force" in argv
    want = [a.upper() for a in argv if not a.startswith("--")]
    if not os.path.exists(OE_DB):
        sys.exit("oe.db not found at %s" % OE_DB)
    if push:
        subprocess.run(["git", "pull", "--rebase", "--autostash"], cwd=ROOT, check=True)
    book = json.load(open(BOOK, encoding="utf-8"))
    book.setdefault("valuations", {})
    if not want:
        want = sorted({t["ticker"] for t in book.get("trades", [])} | {w["ticker"] for w in book.get("watchlist", [])})
    con = sqlite3.connect(OE_DB)
    changed, missing = [], []
    for tk in want:
        cur = book["valuations"].get(tk)
        if cur and cur.get("source") == "manual" and not force:
            print("%-6s manual entry kept (use --force to overwrite)" % tk)
            continue
        v = load_valuation(con, tk)
        if v is None:
            missing.append(tk)
            continue
        book["valuations"][tk] = v
        changed.append(tk)
        print("%-6s base %.2f  buy-below %.2f  gate %s" % (tk, v["base"], v["base"] * (1 - v["mos"]), v["gate"]))
    if missing:
        print("not on the owner-earnings board:", ", ".join(missing))
    if not changed:
        print("nothing to write")
        return
    book["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with open(BOOK, "w", encoding="utf-8") as f:
        json.dump(book, f, indent=2)
        f.write("\n")
    print("wrote", BOOK)
    if push:
        subprocess.run(["git", "add", "data/portfolio.json"], cwd=ROOT, check=True)
        subprocess.run(["git", "commit", "-m", "valuations: sync %s from oe.db" % ", ".join(changed)], cwd=ROOT, check=True)
        subprocess.run(["git", "push"], cwd=ROOT, check=True)


if __name__ == "__main__":
    main(sys.argv[1:])
