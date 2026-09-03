"""Copy owner-earnings valuations from oe-db/oe.db into data/portfolio.json.

Run from anywhere:  python tools/sync_oe.py [--push] [TICKER ...]

For every ticker on the paper book (trades + watchlist), or the tickers given,
pull the bear/base/bull value per share from the local oe.db and write them under
portfolio.json -> valuations[TICKER] with source "oe.db".  Nothing else from the
pipeline (anchor, growth, gate, reasoning) is published.  Manual entries
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
    g = con.execute("SELECT dated FROM gate WHERE ticker=?", (tk,)).fetchone()
    # Only the values themselves go to the public book. The workings (anchor OE,
    # growth, gate rulings, judge reasoning, shares, net debt) stay in oe.db.
    return {
        "source": "oe.db",
        "name": row[0],
        "asof": (g[0] if g and g[0] else row[1]) or datetime.date.today().isoformat(),
        "bear": vals.get("BEAR"), "base": vals.get("BASE"), "bull": vals.get("BULL"),
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
        print("%-6s bear %.2f  base %.2f  bull %.2f" % (tk, v["bear"] or 0, v["base"], v["bull"] or 0))
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
