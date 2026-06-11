"""
PricePulse -- E-commerce Price Monitoring Dashboard
Live demo of a Python scraping + data pipeline + Streamlit stack.
"""

import io
import sqlite3
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from scraper.config import BASE_URL, DB_PATH
from scraper.scrape import get_categories, make_session, scrape_category

st.set_page_config(page_title="PricePulse | Price Monitor", page_icon="📈", layout="wide")



# ---------- bootstrap: self-seed on first run ----------
def ensure_data() -> None:
    """If the DB is missing/empty (fresh deploy), scrape live + seed demo history."""
    import sqlite3 as _sq
    if DB_PATH.exists():
        try:
            n = _sq.connect(DB_PATH).execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
            if n:
                return
        except _sq.Error:
            pass
    with st.spinner("First launch: scraping the full catalogue live (~1 minute)…"):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "scraper.scrape", "--note", "initial live scrape"], check=True)
        subprocess.run([sys.executable, "seed_history.py"], check=True)


ensure_data()

# ---------- data access ----------
@st.cache_data(ttl=600)
def load_data():
    conn = sqlite3.connect(DB_PATH)
    snaps = pd.read_sql("SELECT * FROM snapshots ORDER BY scraped_at", conn)
    prods = pd.read_sql(
        """SELECT p.*, s.scraped_at FROM products p
           JOIN snapshots s ON s.id = p.snapshot_id""",
        conn,
    )
    conn.close()
    prods["scraped_at"] = pd.to_datetime(prods["scraped_at"], format="ISO8601", utc=True)
    snaps["scraped_at"] = pd.to_datetime(snaps["scraped_at"], format="ISO8601", utc=True)
    return snaps, prods


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="products")
    return buf.getvalue()


snaps, prods = load_data()
latest_id = snaps["id"].iloc[-1]
latest = prods[prods["snapshot_id"] == latest_id]
prev_id = snaps["id"].iloc[-2] if len(snaps) > 1 else None

# ---------- header ----------
st.title("📈 PricePulse — Price Monitoring Dashboard")
st.caption(
    f"Source: [{BASE_URL}]({BASE_URL}) (a public scraping sandbox — *\"We love being scraped!\"*) · "
    f"{len(latest):,} products · {len(snaps)} snapshots · "
    f"latest scrape {snaps['scraped_at'].iloc[-1]:%d %b %Y %H:%M} UTC. "
    "Historical snapshots are simulated for demo visualization (the sandbox site has static prices); "
    "on a real project, history accumulates from scheduled scraper runs."
)

# ---------- KPIs ----------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Products tracked", f"{len(latest):,}")
c2.metric("Categories", latest["category"].nunique())
c3.metric("Average price", f"£{latest['price'].mean():.2f}")
if prev_id is not None:
    prev = prods[prods["snapshot_id"] == prev_id][["url", "price"]].rename(columns={"price": "prev_price"})
    merged = latest.merge(prev, on="url")
    drops = (merged["price"] < merged["prev_price"]).sum()
    c4.metric("Price drops since last snapshot", int(drops))

tab_overview, tab_changes, tab_explorer, tab_live = st.tabs(
    ["📊 Overview", "🔻 Price changes", "🔎 Data explorer", "⚡ Live scrape"]
)

# ---------- overview ----------
with tab_overview:
    left, right = st.columns(2)
    with left:
        fig = px.histogram(latest, x="price", nbins=40, title="Price distribution (latest snapshot)")
        fig.update_layout(yaxis_title="Products", xaxis_title="Price (£)")
        st.plotly_chart(fig, width='stretch')
    with right:
        by_cat = (
            latest.groupby("category")["price"]
            .agg(["mean", "count"])
            .sort_values("count", ascending=False)
            .head(15)
            .reset_index()
        )
        fig = px.bar(by_cat, x="category", y="mean", hover_data=["count"],
                     title="Average price by category (top 15 by size)")
        fig.update_layout(yaxis_title="Avg price (£)", xaxis_title="")
        st.plotly_chart(fig, width='stretch')

    trend = prods.groupby("scraped_at")["price"].mean().reset_index()
    fig = px.line(trend, x="scraped_at", y="price", markers=True,
                  title="Average catalogue price over time")
    fig.update_layout(yaxis_title="Avg price (£)", xaxis_title="Snapshot date")
    st.plotly_chart(fig, width='stretch')

# ---------- price changes ----------
with tab_changes:
    if prev_id is None:
        st.info("Need at least two snapshots to compare. Run the scraper again later.")
    else:
        merged = latest.merge(prev, on="url", suffixes=("", "_prev"))
        merged["change"] = merged["price"] - merged["prev_price"]
        merged["change_pct"] = 100 * merged["change"] / merged["prev_price"]
        changed = merged[merged["change"] != 0].copy()

        threshold = st.slider("Alert threshold — minimum % change", 1, 25, 5)
        alerts = changed[changed["change_pct"].abs() >= threshold]
        st.write(f"**{len(alerts)} products** moved ≥ {threshold}% between the last two snapshots.")

        show = alerts[["title", "category", "prev_price", "price", "change", "change_pct"]] \
            .sort_values("change_pct")
        show.columns = ["Product", "Category", "Old £", "New £", "Δ £", "Δ %"]
        st.dataframe(
            show.style.format({"Old £": "{:.2f}", "New £": "{:.2f}", "Δ £": "{:+.2f}", "Δ %": "{:+.1f}"})
                .map(lambda v: "color:#16a34a" if isinstance(v, (int, float)) and v < 0 else
                               ("color:#dc2626" if isinstance(v, (int, float)) and v > 0 else ""),
                     subset=["Δ £", "Δ %"]),
            width='stretch', height=420,
        )
        st.caption("Green = price drop (buy signal) · Red = increase. "
                   "On client projects these alerts go to email/Slack/Google Sheets automatically.")

# ---------- data explorer ----------
with tab_explorer:
    f1, f2, f3 = st.columns([2, 2, 3])
    cats = sorted(latest["category"].unique())
    sel_cats = f1.multiselect("Category", cats)
    pmin, pmax = float(latest["price"].min()), float(latest["price"].max())
    price_range = f2.slider("Price range (£)", pmin, pmax, (pmin, pmax))
    query = f3.text_input("Search product name")

    view = latest.copy()
    if sel_cats:
        view = view[view["category"].isin(sel_cats)]
    view = view[(view["price"] >= price_range[0]) & (view["price"] <= price_range[1])]
    if query:
        view = view[view["title"].str.contains(query, case=False, na=False)]

    st.write(f"**{len(view):,} products**")
    cols = ["title", "category", "price", "rating", "in_stock", "url"]
    st.dataframe(view[cols], width='stretch', height=420,
                 column_config={"url": st.column_config.LinkColumn("Product page")})

    d1, d2 = st.columns(2)
    d1.download_button("⬇️ Download CSV", view[cols].to_csv(index=False).encode(),
                       "pricepulse_products.csv", "text/csv", width='stretch')
    d2.download_button("⬇️ Download Excel", to_excel_bytes(view[cols]),
                       "pricepulse_products.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width='stretch')

# ---------- live scrape ----------
with tab_live:
    st.write(
        "Prove it works **right now**: this button runs the actual scraper against "
        f"{BASE_URL} live from this server — real HTTP requests, real parsing, no cached data."
    )
    n_cats = st.slider("Categories to scrape live", 1, 5, 2)
    if st.button("🚀 Run live scrape", type="primary"):
        with st.spinner("Scraping live…"):
            t0 = datetime.now()
            session = make_session()
            cats = get_categories(session)[:n_cats]
            rows = []
            for name, url in cats:
                rows.extend(scrape_category(session, name, url, max_pages=1))
            secs = (datetime.now() - t0).total_seconds()
        df = pd.DataFrame(rows)
        st.success(f"Scraped {len(df)} products from {n_cats} categories in {secs:.1f}s")
        st.dataframe(df, width='stretch')

st.divider()
st.caption("Built by Mubarak Ahmed · Python · Requests/BeautifulSoup · SQLite · Streamlit · "
           "[Source on GitHub](https://github.com/)")
