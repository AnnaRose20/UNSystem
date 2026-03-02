from datetime import datetime

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
import pandas as pd
import io

# for the database operations
from sqlalchemy import create_engine, text

# relative import – src is a package
from . import generators_api

app = FastAPI(title="UNO URL Export API")


# ==========================================================
# Organization registry
# ==========================================================
ORG_GENERATORS = {
    "UNGA": generators_api.generate_unga_df,
    "UNSC": generators_api.generate_unsc_df,
    "ECOSOC": lambda: generators_api.generate_ecosoc_df(10),
    "SECRETARIAT": lambda: generators_api.generate_secretariat_df(10),

    "UNICEF": lambda: generators_api.generate_unicef_df(10),
    "UNWOMEN": lambda: generators_api.generate_unwomen_df(10),
    "UNCTAD": lambda: generators_api.generate_unctad_df(10),
    "UNFPA": lambda: generators_api.generate_unfpa_df(10),
    "UNHCR": lambda: generators_api.generate_unhcr_df(10),
    "OCHA": lambda: generators_api.generate_ocha_df(10),
    "UNRWA": lambda: generators_api.generate_unrwa_df(10),
    "UNHABITAT": lambda: generators_api.generate_unhabitat_df(10),
    "UNODC": lambda: generators_api.generate_unodc_df(10),
    "UNITAR": lambda: generators_api.generate_unitar_df(10),
    "UNU": lambda: generators_api.generate_unu_df(10),
    "WFP": lambda: generators_api.generate_wfp_df(10),

    "ICJ": generators_api.generate_icj_df,
    "FAO": generators_api.generate_fao_df,
    "ICAO": generators_api.generate_icao_df,
    "HRC": generators_api.generate_hrc_df,
    "IMO": generators_api.generate_imo_df,
}


def df_to_excel_bytes(df: pd.DataFrame):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return output


def _save_to_database(df: pd.DataFrame, orgid: str):
    """Add OrgID and timestamp, dedupe and write rows to sqlite table.

    Previous entries for the same organisation are removed first so that
    calling the same org twice overwrites rather than appends.
    """
    # normalise column name used by generators
    if "URL" in df.columns and "Link" not in df.columns:
        df = df.rename(columns={"URL": "Link"})

    # inject OrgID and time‑stamp
    df["OrgID"] = orgid
    df["RequestedAt"] = datetime.now()

    # keep only the columns we care about and drop any duplicates
    cols = [c for c in ["Year", "Type", "Symbol", "Link", "OrgID", "RequestedAt"]
            if c in df.columns]
    df = df[cols].drop_duplicates()

    engine = create_engine("sqlite:///uno.db")
    with engine.begin() as conn:
        # remove whatever we inserted previously for this org
        conn.execute(
            text("DELETE FROM requested_links WHERE OrgID = :org"),
            {"org": orgid},
        )
        df.to_sql("requested_links", conn, if_exists="append", index=False)


@app.get("/export/urls.xlsx")
def export_urls(
    org: str = Query(..., description="Organisation name"),
    year: int = Query(None, description="Filter by year")
):
    org = org.upper().replace("-", "").replace(" ", "")

    if org not in ORG_GENERATORS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown org. Available: {list(ORG_GENERATORS.keys())}"
        )

    df = ORG_GENERATORS[org]()

    if year and "Year" in df.columns:
        df = df[df["Year"] == year]

    if df.empty:
        raise HTTPException(status_code=404, detail="No data found.")

    # persist request to database (adds OrgID + RequestedAt,
    # overwrites previous rows for the same org)
    _save_to_database(df, org)

    excel_file = df_to_excel_bytes(df)

    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="{org}_urls.xlsx"'}
    )