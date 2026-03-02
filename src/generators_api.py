# src/generators.py
from __future__ import annotations
import datetime
import pandas as pd
import requests
from bs4 import BeautifulSoup

# ==========================================================
# Helper: standardize DataFrame output
# ==========================================================
def standardize(df: pd.DataFrame, org: str) -> pd.DataFrame:
    df = df.copy()

    if "Link" in df.columns and "URL" not in df.columns:
        df = df.rename(columns={"Link": "URL"})

    if "Org" not in df.columns:
        df.insert(0, "Org", org)

    if "Year" not in df.columns:
        df["Year"] = pd.NA

    keep_cols = [c for c in ["Org", "Year", "Type", "Symbol", "URL"] if c in df.columns]
    return df[keep_cols].dropna(subset=["URL"])


# ==========================================================
# UNGA
# ==========================================================
session_data = {
    80: {"res": 246, "pv": 69},
    79: {"res": 334, "pv": 95},
    78: {"res": 331, "pv": 110},
    77: {"res": 335, "pv": 100},
    76: {"res": 307, "pv": 100},
    75: {"res": 325, "pv": 105},
    74: {"res": 297, "pv": 90},
    73: {"res": 344, "pv": 105},
    72: {"res": 313, "pv": 115},
    71: {"res": 329, "pv": 100},
}

def generate_unga_df() -> pd.DataFrame:
    base_url = "https://docs.un.org/en"
    rows = []

    for session, counts in session_data.items():
        year = 1945 + session

        for i in range(1, counts["res"] + 1):
            sym = f"A/RES/{session}/{i}"
            rows.append({"Year": year, "Type": "Resolution", "Symbol": sym, "URL": f"{base_url}/{sym}"})

        for j in range(1, counts["pv"] + 1):
            sym = f"A/{session}/PV.{j}"
            rows.append({"Year": year, "Type": "Meeting Record", "Symbol": sym, "URL": f"{base_url}/{sym}"})

    return standardize(pd.DataFrame(rows), "UNGA")


# ==========================================================
# UNSC
# ==========================================================
def generate_unsc_df() -> pd.DataFrame:
    base_url = "https://undocs.org/en"
    rows = []

    current_year = datetime.datetime.now().year
    for y in range(current_year - 10, current_year + 1):
        for i in range(1, 101):
            sym = f"S/{y}/{i}"
            rows.append({"Year": y, "Type": "Document", "Symbol": sym, "URL": f"{base_url}/{sym}"})

        for i in range(1, 26):
            sym = f"S/PRST/{y}/{i}"
            rows.append({"Year": y, "Type": "Presidential Statement", "Symbol": sym, "URL": f"{base_url}/{sym}"})

    return standardize(pd.DataFrame(rows), "UNSC")


# ==========================================================
# ECOSOC
# ==========================================================
def generate_ecosoc_df(years_back: int = 10) -> pd.DataFrame:
    current_year = datetime.datetime.now().year
    rows = []

    for year in range(current_year - years_back, current_year + 1):
        for i in range(1, 41):
            sym = f"E/RES/{year}/{i}"
            rows.append({"Year": year, "Type": "Resolution", "Symbol": sym, "URL": f"https://undocs.org/en/{sym}"})

    return standardize(pd.DataFrame(rows), "ECOSOC")


# ==========================================================
# Secretariat
# ==========================================================
def generate_secretariat_df(years_back: int = 10) -> pd.DataFrame:
    current_year = datetime.datetime.now().year
    rows = []

    for year in range(current_year - years_back, current_year + 1):
        for i in range(1, 11):
            sym = f"ST/SGB/{year}/{i}"
            rows.append({"Year": year, "Type": "Bulletin", "Symbol": sym, "URL": f"https://undocs.org/en/{sym}"})

    return standardize(pd.DataFrame(rows), "SECRETARIAT")


# ==========================================================
# Pattern-based agencies (UNICEF, UNWOMEN, UNFPA, etc.)
# ==========================================================
def simple_pattern(org: str, prefix: str, years_back: int = 10, count: int = 20):
    current_year = datetime.datetime.now().year
    rows = []

    for year in range(current_year - years_back, current_year + 1):
        for i in range(1, count + 1):
            sym = f"{prefix}/{year}/{i}"
            rows.append({"Year": year, "Type": "Document", "Symbol": sym, "URL": f"https://undocs.org/en/{sym}"})

    return standardize(pd.DataFrame(rows), org)


def generate_unicef_df(years_back=10): return simple_pattern("UNICEF", "E/ICEF", years_back)
def generate_unwomen_df(years_back=10): return simple_pattern("UNWOMEN", "UNW", years_back)
def generate_unctad_df(years_back=10): return simple_pattern("UNCTAD", "TD", years_back)
def generate_unfpa_df(years_back=10): return simple_pattern("UNFPA", "DP/FPA", years_back)
def generate_unhcr_df(years_back=10): return simple_pattern("UNHCR", "A/AC.96", years_back)
def generate_ocha_df(years_back=10): return simple_pattern("OCHA", "A", years_back)
def generate_unrwa_df(years_back=10): return simple_pattern("UNRWA", "A/AC.183", years_back)
def generate_unhabitat_df(years_back=10): return simple_pattern("UNHABITAT", "HS", years_back)
def generate_unodc_df(years_back=10): return simple_pattern("UNODC", "E/CN.7", years_back)
def generate_unitar_df(years_back=10): return simple_pattern("UNITAR", "UNITAR", years_back)
def generate_unu_df(years_back: int = 10) -> pd.DataFrame:
    """Return UNU documents for the past `years_back` years.

    The notebook helper built an Excel file; here we simply construct the
    same rows and hand back a DataFrame to be consumed by the API layer.
    """
    current_year = datetime.datetime.now().year
    start_year = current_year - years_back
    rows: list[dict] = []

    for year in range(start_year, current_year + 1):
        session = year - 1945

        # report of the UNU Council (GAOR supplement 31)
        sym = f"A/{session}/31"
        rows.append({
            "Year": year,
            "Type": "Report of the UNU Council (GAOR Supp 31)",
            "Symbol": sym,
            "URL": f"https://undocs.org/en/{sym}",
        })

        # audited financial statement (GAOR supplement 5/add.5)
        sym = f"A/{session}/5/Add.5"
        rows.append({
            "Year": year,
            "Type": "Audited Financial Statement (GAOR Supp 5/Add.5)",
            "Symbol": sym,
            "URL": f"https://undocs.org/en/{sym}",
        })

        # institutional framework/flagship report (external site)
        rows.append({
            "Year": year,
            "Type": "Institutional Framework/Report",
            "Symbol": f"UNU-Pub-{year}",
            "URL": "https://unu.edu",
        })

    return standardize(pd.DataFrame(rows), "UNU")
def generate_wfp_df(years_back=10): return simple_pattern("WFP", "WFP", years_back)


# ==========================================================
# Web-scrape orgs (ICJ, FAO, ICAO, HRC, IMO, ILO)
# ==========================================================
def scrape_links(org: str, base_url: str):
    r = requests.get(base_url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    rows = []
    for a in soup.select("a[href]"):
        href = a["href"]
        if href.startswith("/"):
            href = base_url.rstrip("/") + href
        rows.append({"Type": "Web Link", "Symbol": pd.NA, "URL": href})

    return standardize(pd.DataFrame(rows), org)


def generate_icj_df(): return scrape_links("ICJ", "https://www.icj-cij.org/")
def generate_fao_df(): return scrape_links("FAO", "https://www.fao.org/publications/en/")
def generate_icao_df(): return scrape_links("ICAO", "https://www.icao.int/publications/Pages/default.aspx")
def generate_hrc_df(): return scrape_links("HRC", "https://www.ohchr.org/en/hr-bodies/hrc")
def generate_imo_df(): return scrape_links("IMO", "https://www.imo.org")
def generate_ilo_df(): return scrape_links("ILO", "https://www.ilo.org/global/publications/lang--en/index.htm")