#!/usr/bin/env python3
"""
CAIO — Outdoor Companies Explorer (Streamlit UI)

A local web app to browse, search, sort, and filter the enriched company dataset.

Run it on your local network so other devices (phone, laptop) can view it too:

    pip install -r requirements.txt
    streamlit run app.py --server.address=0.0.0.0

Streamlit prints a "Network URL" (e.g. http://192.168.1.23:8501). Any device on
the same Wi-Fi/LAN can open that URL. (The plain `streamlit run app.py` default
only serves localhost; `--server.address=0.0.0.0` exposes it to the LAN.)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

DATA = Path(__file__).parent / "enriched_companies.csv"

st.set_page_config(page_title="CAIO — Outdoor Companies", page_icon="🏔️", layout="wide")


@st.cache_data
def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA)
    # Numeric founded year for range filtering ("N/A" -> NaN).
    df["founded_year_num"] = pd.to_numeric(df["founded_year"], errors="coerce")
    return df


df = load_data()

st.title("🏔️ Outdoor Companies Explorer")
st.caption(f"{len(df)} companies · source: enriched_companies.csv")

# --------------------------------------------------------------------------- #
# Sidebar filters
# --------------------------------------------------------------------------- #
st.sidebar.header("Filters")

countries = sorted(df["headquarters_country"].dropna().unique())
sel_countries = st.sidebar.multiselect("Country", countries)

states = sorted(df["headquarters_state"].dropna().unique())
sel_states = st.sidebar.multiselect("State / region", states)

yr_min, yr_max = int(df["founded_year_num"].min()), int(df["founded_year_num"].max())
sel_years = st.sidebar.slider("Founded year", yr_min, yr_max, (yr_min, yr_max))
include_unknown_year = st.sidebar.checkbox("Include unknown founding year", value=True)

only_revenue = st.sidebar.checkbox("Only companies with known revenue", value=False)

# --------------------------------------------------------------------------- #
# Search + sort controls
# --------------------------------------------------------------------------- #
c1, c2, c3 = st.columns([3, 2, 1])
query = c1.text_input("🔎 Search", placeholder="Search company, city, CEO, description…")
sort_cols = [
    "company_name", "headquarters_country", "headquarters_state",
    "headquarters_city", "founded_year_num", "ceo_or_founder", "annual_revenue",
]
sort_by = c2.selectbox(
    "Sort by", sort_cols, index=0,
    format_func=lambda c: c.replace("_num", "").replace("_", " ").title(),
)
ascending = c3.radio("Order", ["Asc", "Desc"], horizontal=True) == "Asc"

# --------------------------------------------------------------------------- #
# Apply filters + search + sort
# --------------------------------------------------------------------------- #
view = df.copy()

if sel_countries:
    view = view[view["headquarters_country"].isin(sel_countries)]
if sel_states:
    view = view[view["headquarters_state"].isin(sel_states)]
if only_revenue:
    view = view[view["annual_revenue"].str.upper() != "N/A"]

year_mask = view["founded_year_num"].between(sel_years[0], sel_years[1])
if include_unknown_year:
    year_mask = year_mask | view["founded_year_num"].isna()
view = view[year_mask]

if query:
    q = query.strip().lower()
    searchable = [
        "company_name", "website", "headquarters_city", "headquarters_state",
        "headquarters_country", "phone_number", "founded_year",
        "ceo_or_founder", "annual_revenue", "industry_segment",
    ]
    mask = view[searchable].apply(
        lambda col: col.astype(str).str.lower().str.contains(q, na=False)
    ).any(axis=1)
    view = view[mask]

view = view.sort_values(sort_by, ascending=ascending, na_position="last")

st.write(f"**{len(view)}** of {len(df)} companies match")

# --------------------------------------------------------------------------- #
# Results table (columns are also click-sortable in the UI)
# --------------------------------------------------------------------------- #
display_cols = [
    "company_name", "website", "headquarters_city", "headquarters_state",
    "headquarters_country", "phone_number", "founded_year",
    "ceo_or_founder", "annual_revenue", "industry_segment",
]

st.dataframe(
    view[display_cols],
    use_container_width=True,
    hide_index=True,
    column_config={
        "company_name": st.column_config.TextColumn("Company", width="medium"),
        "website": st.column_config.LinkColumn("Website", display_text="site"),
        "headquarters_city": "City",
        "headquarters_state": "State/Region",
        "headquarters_country": "Country",
        "phone_number": "Phone",
        "founded_year": "Founded",
        "ceo_or_founder": "CEO / Founder",
        "annual_revenue": "Revenue",
        "industry_segment": st.column_config.TextColumn("What they do", width="large"),
    },
)

st.download_button(
    "⬇️ Download filtered CSV",
    view[display_cols].to_csv(index=False).encode("utf-8"),
    "companies_filtered.csv",
    "text/csv",
)
