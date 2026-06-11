# 📈 PricePulse — E-commerce Price Monitoring Dashboard

**Live demo:** https://pricepulse-monitor.streamlit.app · **Author:** [Mubarak Ahmed](https://www.upwork.com/freelancers/mubarakahmedmohamud)

PricePulse scrapes an e-commerce catalogue (1,000 products, 50 categories, full
pagination), stores timestamped snapshots in SQLite, and serves an interactive
dashboard with price-drop alerts, category analytics, full-text product search,
and one-click CSV/Excel export. It also includes a **live-scrape button** that
runs the real scraper on demand — proof the pipeline works end-to-end.

> Target site is [books.toscrape.com](https://books.toscrape.com), a public
> sandbox built for scraping practice ("We love being scraped!"), so the demo
> is 100% legal and stable. The scraper is config-driven (`scraper/config.py`)
> and adapts to real client sites in minutes.

## Features

| Capability | How |
|---|---|
| Resilient scraping | `requests.Session` + retries with exponential backoff, polite crawl delay, identifiable User-Agent |
| Full-site coverage | Category discovery + pagination handling (50 categories, 1,000 products) |
| Price history | Every run = a new timestamped snapshot in SQLite → trends & change detection |
| Price-drop alerts | Configurable %-change threshold between snapshots |
| Clean delivery | Filterable table, CSV & Excel export (the formats clients actually use) |
| Live proof | "Run live scrape" tab fires real HTTP requests from the server, on demand |

*Note: because the sandbox site has static prices, historical snapshots are
simulated (clearly labeled) so trend features can be demonstrated. On a real
project, history accumulates from scheduled runs — cron, GitHub Actions, or n8n.*

## Architecture

```
books.toscrape.com ──> scraper/scrape.py ──> data/prices.db (SQLite, snapshots)
        (requests + BeautifulSoup,                  │
         retries, pagination)                       ▼
                                            app.py (Streamlit + Plotly)
                                            charts · alerts · search · CSV/Excel
```

## Run it yourself

```bash
pip install -r requirements.txt
python -m scraper.scrape          # full scrape -> new snapshot (the app also self-seeds on first run)
python seed_history.py            # demo-only: simulated history
streamlit run app.py
```

## Stack

Python · Requests · BeautifulSoup · SQLite · pandas · Streamlit · Plotly · openpyxl

---

### Need something like this for your business?

I build scrapers for real sites — JavaScript-heavy pages (Playwright), login
flows, anti-bot handling, scheduled runs that keep a Google Sheet or database
fresh. **[Hire me on Upwork](https://www.upwork.com/freelancers/mubarakahmedmohamud).**
