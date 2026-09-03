# Serene Paper Book

A public, single-file paper-trading ledger: open positions ranked best to worst,
a watchlist, closed trades, and a page per ticker with the owner-earnings intrinsic
value and a written thesis. Anyone with the link can view and refresh prices;
editing needs the PIN.

## How it fits together

| Piece | Role |
|---|---|
| `index.html` | The whole interface. No build step, no framework. |
| `data/portfolio.json` | **The database of record.** Trades, watchlist, theses, valuations. Every edit is a git commit, so history is the audit trail. |
| `data/prices.json` | Price snapshot written by the scheduled workflow (Massive, key kept as a repo secret). The page falls back to it when a live quote is unavailable. |
| `data/vault.json` | The editing token, encrypted with the PIN (PBKDF2 + AES-GCM in the browser). Created once from the `#/setup` page. |
| `refresh_prices.py` | Writes `data/prices.json`. Massive first, Yahoo as fallback. |
| `.github/workflows/prices.yml` | Runs `refresh_prices.py` every 20 minutes in US hours, and on demand. |
| `tools/sync_oe.py` | Copies the bear/base/bull values per share from `../oe-db/oe.db` into the book. `--push` commits and pushes. |
| `serve_local.py` / `open_book.bat` | Local preview with editing on and no PIN; edits write to `data/portfolio.json`. |

## Prices

Clicking **Refresh prices** in the page asks CNBC's public quote service for every
ticker on the book (regular-session last; keyless and cross-origin friendly). If the
viewer has unlocked editing, the same click also dispatches the snapshot workflow,
which prices the book through Massive and commits `data/prices.json`. A ticker CNBC
cannot price shows the workflow snapshot instead, marked with a small `s`.

Non-US listings: give the row a `quote_symbol` in CNBC form (`NESN-CH`) and, if
Massive cannot price it, a `yahoo_symbol` (`NESN.SW`).

## Metrics

* **Return to date** = price ÷ entry − 1 (sign flipped for shorts). Closed trades use the exit price.
* **IRR p.a.** = (1 + return)^(365 ÷ days held) − 1. A dagger marks holding periods under 30 days, where annualising is not meaningful.
* **Book IRR** is the money-weighted return over every trade's cash flows, with open positions marked at the latest price today.
* **Intrinsic** is the base-case owner-earnings value per share; **upside** = intrinsic ÷ price − 1. The ticker page shows the bear / base / bull range only; the pipeline's workings stay private.

## Editing

Unlock with the PIN. Enter a trade, exit it, delete it, add or promote a watchlist
name, write a thesis, or type an intrinsic value by hand for a name the pipeline has
not covered. Each action commits to `data/portfolio.json`; the page re-reads the
latest version before writing so two editors do not clobber each other.

The PIN is a convenience lock, not a secret: the encrypted token sits in a public
repository, so keep the token fine-grained and scoped to this repository alone.

## Local run

```
python -m http.server 8765      # then open http://localhost:8765
python refresh_prices.py        # snapshot, using MASSIVE_API_KEY if set
python tools/sync_oe.py --push  # pull valuations from oe.db and publish
```
