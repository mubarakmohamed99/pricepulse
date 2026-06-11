"""
PricePulse scraper
------------------
Scrapes product data (title, price, rating, stock, category) from the target
e-commerce site and stores a timestamped snapshot in SQLite.

Design notes:
- requests.Session with retry + exponential backoff (handles flaky networks)
- Polite crawl delay + identifiable User-Agent
- Category-aware crawling with full pagination
- Idempotent snapshots: every run is a new snapshot, enabling price history
- Config-driven selectors (see config.py) so it adapts to other sites

Usage:
    python -m scraper.scrape            # full scrape, save snapshot
    python -m scraper.scrape --pages 2  # quick scrape (first N pages per category)
"""

import argparse
import logging
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from scraper.config import BASE_URL, CRAWL_DELAY_SECONDS, DB_PATH, USER_AGENT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pricepulse")

RATING_MAP = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def make_session() -> requests.Session:
    """Session with retries and backoff -- survives transient errors."""
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    time.sleep(CRAWL_DELAY_SECONDS)  # be polite
    return BeautifulSoup(resp.text, "html.parser")


def get_categories(session: requests.Session) -> list[tuple[str, str]]:
    """Return [(category_name, category_url), ...] from the sidebar."""
    soup = get_soup(session, BASE_URL)
    links = soup.select("div.side_categories ul ul a")
    cats = []
    for a in links:
        name = a.get_text(strip=True)
        url = urljoin(BASE_URL, a["href"])
        cats.append((name, url))
    log.info("Found %d categories", len(cats))
    return cats


def parse_listing_page(soup: BeautifulSoup, category: str, page_url: str) -> list[dict]:
    """Extract all products from one listing page."""
    products = []
    for card in soup.select("article.product_pod"):
        title = card.h3.a["title"].strip()
        price_text = card.select_one("p.price_color").get_text(strip=True)
        price = float(re.sub(r"[^0-9.]", "", price_text))
        rating_cls = card.select_one("p.star-rating")["class"]
        rating = next((RATING_MAP[c] for c in rating_cls if c in RATING_MAP), None)
        in_stock = 1 if "In stock" in card.select_one("p.instock").get_text() else 0
        url = urljoin(page_url, card.h3.a["href"])
        products.append(
            dict(title=title, category=category, price=price,
                 rating=rating, in_stock=in_stock, url=url)
        )
    return products


def scrape_category(session: requests.Session, name: str, url: str,
                    max_pages: int | None = None) -> list[dict]:
    """Scrape one category, following pagination."""
    products, page, page_url = [], 1, url
    while True:
        soup = get_soup(session, page_url)
        products.extend(parse_listing_page(soup, name, page_url))
        next_link = soup.select_one("li.next a")
        if not next_link or (max_pages and page >= max_pages):
            break
        page_url = urljoin(page_url, next_link["href"])
        page += 1
    log.info("Category %-22s -> %d products", name, len(products))
    return products


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scraped_at TEXT NOT NULL,
            source TEXT NOT NULL,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS products (
            snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
            title TEXT NOT NULL,
            category TEXT,
            price REAL,
            rating INTEGER,
            in_stock INTEGER,
            url TEXT,
            PRIMARY KEY (snapshot_id, url)
        );
        """
    )
    return conn


def save_snapshot(conn: sqlite3.Connection, products: list[dict], note: str = "") -> int:
    scraped_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO snapshots (scraped_at, source, note) VALUES (?, ?, ?)",
        (scraped_at, BASE_URL, note),
    )
    snap_id = cur.lastrowid
    conn.executemany(
        """INSERT OR REPLACE INTO products
           (snapshot_id, title, category, price, rating, in_stock, url)
           VALUES (:snapshot_id, :title, :category, :price, :rating, :in_stock, :url)""",
        [dict(p, snapshot_id=snap_id) for p in products],
    )
    conn.commit()
    return snap_id


def main() -> int:
    parser = argparse.ArgumentParser(description="PricePulse scraper")
    parser.add_argument("--pages", type=int, default=None,
                        help="Max pages per category (default: all)")
    parser.add_argument("--note", default="scheduled scrape", help="Snapshot note")
    args = parser.parse_args()

    session = make_session()
    all_products: list[dict] = []
    for name, url in get_categories(session):
        try:
            all_products.extend(scrape_category(session, name, url, args.pages))
        except requests.RequestException as exc:
            log.error("Category %s failed after retries: %s", name, exc)

    if not all_products:
        log.error("No products scraped -- selectors may need updating.")
        return 1

    conn = init_db(DB_PATH)
    snap_id = save_snapshot(conn, all_products, note=args.note)
    log.info("Saved snapshot #%d with %d products -> %s", snap_id, len(all_products), DB_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
