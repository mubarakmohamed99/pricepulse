"""
Generate simulated historical snapshots for demo purposes.

Why: the sandbox site (books.toscrape.com) has STATIC prices, so a real price
history can't form. This script clones the latest real snapshot backwards in
time with small random price walks so the dashboard's trend/price-change
features can be demonstrated. Snapshots are clearly labeled
"simulated demo history" in the database and in the UI.

On a real client project this file would not exist -- history accumulates
naturally from scheduled scraper runs (cron / GitHub Actions / n8n).
"""

import random
import sqlite3
from datetime import datetime, timedelta, timezone

from scraper.config import BASE_URL, DB_PATH

WEEKS = 6
random.seed(42)


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    snap = conn.execute(
        "SELECT id, scraped_at FROM snapshots WHERE note NOT LIKE '%simulated%' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not snap:
        raise SystemExit("Run the scraper first: python -m scraper.scrape")
    latest_id, latest_at = snap
    rows = conn.execute(
        "SELECT title, category, price, rating, in_stock, url FROM products WHERE snapshot_id = ?",
        (latest_id,),
    ).fetchall()
    base_time = datetime.fromisoformat(latest_at)
    if base_time.tzinfo is None:
        base_time = base_time.replace(tzinfo=timezone.utc)

    # walk prices backwards week by week
    prices = {r[5]: r[2] for r in rows}
    for week in range(1, WEEKS + 1):
        ts = (base_time - timedelta(weeks=week)).isoformat(timespec="seconds")
        cur = conn.execute(
            "INSERT INTO snapshots (scraped_at, source, note) VALUES (?, ?, ?)",
            (ts, BASE_URL, "simulated demo history"),
        )
        snap_id = cur.lastrowid
        out = []
        for title, category, _price, rating, in_stock, url in rows:
            drift = random.uniform(-0.06, 0.06)  # +/- 6% per week
            prices[url] = round(max(2.0, prices[url] * (1 + drift)), 2)
            out.append((snap_id, title, category, prices[url], rating, in_stock, url))
        conn.executemany(
            "INSERT OR REPLACE INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", out
        )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    print(f"Done. Database now has {n} snapshots.")


if __name__ == "__main__":
    main()
