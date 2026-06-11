"""Site + runtime configuration. Swap these values to point at another site."""
import os
from pathlib import Path

# Target site (legal scraping sandbox: "We love being scraped!")
BASE_URL = "https://books.toscrape.com/"

# Be a good citizen
CRAWL_DELAY_SECONDS = 0.05
USER_AGENT = "PricePulseBot/1.0 (+portfolio demo; respectful crawler)"

# Storage
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("PRICEPULSE_DB", PROJECT_ROOT / "data" / "prices.db"))
