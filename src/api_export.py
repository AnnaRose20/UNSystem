from datetime import datetime
import json

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import pandas as pd
import io

# for the database operations
from sqlalchemy import create_engine, text

# relative import – src is a package
from . import generators_api
from .pdf_downloader import PDFDownloader

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

    The requested_links table enforces a UNIQUE constraint on
    (OrgID, Link, Year).  This function removes the previous entries
    for the same org before inserting fresh data, preventing constraint
    violations.  Duplicates within the frame are also dropped based on
    the constraint columns.
    """
    # normalise column name used by generators
    if "URL" in df.columns and "Link" not in df.columns:
        df = df.rename(columns={"URL": "Link"})

    # inject OrgID and time‑stamp
    df["OrgID"] = orgid
    df["RequestedAt"] = datetime.now()
    # get ParentId from org_node table
    query = text("SELECT parent_id FROM org_node WHERE id = :org")
    engine = create_engine("sqlite:///uno.db")
    with engine.connect() as conn:
        result = conn.execute(query, {"org": orgid})
        parent_id = result.scalar()
    df["parent_id"] = parent_id
    

    # keep only the columns we care about
    cols = [c for c in ["Year", "Type", "Symbol", "Link", "OrgID", "RequestedAt", "parent_id"]
            if c in df.columns]
    df = df[cols]

    # drop duplicates based on the UNIQUE constraint columns: (OrgID, Link, Year)
    # this preserves the most recent RequestedAt for each unique combination
    df = df.drop_duplicates(subset=["OrgID", "Link", "Year"], keep="last")

    engine = create_engine("sqlite:///uno.db")
    with engine.begin() as conn:
        # Only delete rows that would conflict (same OrgID, Link, Year)
        # This preserves data for other years of the same organization
        for _, row in df[["Link", "Year"]].drop_duplicates().iterrows():
            conn.execute(
                text("DELETE FROM requested_links WHERE OrgID = :org AND Link = :link AND Year = :year"),
                {"org": orgid, "link": row["Link"], "year": row["Year"]},
            )
        df.to_sql("requested_links", conn, if_exists="append", index=False)


@app.get("/export/urls")
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


@app.get("/download/pdfs")
def download_pdfs(
    org: str = Query(..., description="Organisation name"),
    year: int = Query(None, description="Filter by year"),
    type: str = Query(None, description="Filter by document type Resolution, Meeting Record, Bulletin,  Document, Report of the UNU Council (GAOR Supp 31), Audited Financial Statement (GAOR Supp 5/Add.5), Institutional Framework/Report")
):
    """
    Download PDFs from URLs for a specific organization, year, and type.
    
    Query parameters:
    - org: Organization ID (e.g., 'UNGA', 'UNSC')
    - year: Optional year to filter by
    - type: Optional document type to filter by (e.g., 'Resolution', 'Report')
    
    Returns JSON with download status, file paths, and statistics.
    """
    org = org.upper().replace("-", "").replace(" ", "")
    
    # Initialize the PDF downloader
    downloader = PDFDownloader(db_path="uno.db", download_dir="data/downloads")
    
    # Start the download batch
    result = downloader.download_batch(orgid=org, year=year, doc_type=type)
    
    # Return the summary as JSON
    return JSONResponse(content=result)


@app.get("/download/status")
def get_download_status(
    org: str = Query(..., description="Organisation name"),
    year: int = Query(None, description="Filter by year"),
    type: str = Query(None, description="Filter by document type Resolution, Meeting Record, Bulletin,  Document, Report of the UNU Council (GAOR Supp 31), Audited Financial Statement (GAOR Supp 5/Add.5), Institutional Framework/Report")
):
    """
    Check available URLs for download without actually downloading them.
    
    Returns a count and sample of URLs that would be downloaded.
    """
    org = org.upper().replace("-", "").replace(" ", "")
    
    downloader = PDFDownloader(db_path="uno.db", download_dir="data/downloads")
    df = downloader.query_urls(orgid=org, year=year, doc_type=type)
    
    if df.empty:
        return JSONResponse({
            "status": "no_data",
            "message": f"No URLs found for OrgID={org}, Year={year}, Type={type}",
            "count": 0
        })
    
    return JSONResponse({
        "status": "ok",
        "orgid": org,
        "year": year,
        "doc_type": type,
        "total_urls": len(df),
        "sample_urls": df.head(5)[["Symbol", "Link", "Type", "Year"]].to_dict(orient="records")
    })


@app.get("/retrieve/docs")
def retrieve_docs(
    org: str = Query(..., description="Organization ID (e.g., 'UNGA', 'UNSC')")
):
    """
    Retrieve documents based on OrgID and download corresponding PDFs.

    Query parameters:
    - org: Organization ID (e.g., 'UNGA', 'UNSC')

    Returns a JSON response with the retrieved documents and downloads PDFs.
    """
    org = org.upper().replace("-", "").replace(" ", "")

    # Connect to the database
    engine = create_engine("sqlite:///uno.db")
    with engine.connect() as conn:
        # Query to fetch documents for the given OrgID
        query = "SELECT * FROM requested_links WHERE OrgID = :org"
        params = {"org": org}

        # Execute the query
        result = conn.execute(text(query), params)
        rows = [dict(row) for row in result.mappings()]  # Use .mappings() to convert rows to dictionaries
        print(rows)
    if not rows:
        return JSONResponse({
            "status": "no_data",
            "message": f"No documents found for OrgID={org}",
            "count": 0
        })

    # Initialize the PDF downloader
    downloader = PDFDownloader(db_path="uno.db", download_dir="data/downloads")

    # Download PDFs for the retrieved links
    download_results = []
    for row in rows:
        link = row.get("Link")
        if link:
            download_result = downloader.download_pdf(link)
            download_results.append({"link": link, "status": download_result})

    return JSONResponse({
        "status": "ok",
        "orgid": org,
        "total_docs": len(rows),
        "documents": rows,
        "download_results": download_results
    })


@app.get("/getalldocuments")
def get_documents(
    org: str = Query(..., description="Organization ID (e.g., 'UNGA', 'UNSC')"),
    include_children: bool = Query(False, description="Include documents from child organizations")
):
    """
    Retrieve documents for a given OrgID, optionally including child organizations.

    Query parameters:
    - org: Organization ID (e.g., 'UNGA', 'UNSC')
    - include_children: Whether to include documents from child organizations

    Returns a JSON response with the retrieved documents.
    """
    org = org.upper().replace("-", "").replace(" ", "")

    # Connect to the database
    engine = create_engine("sqlite:///uno.db")
    with engine.connect() as conn:
        # Fetch child organizations if include_children is True
        org_ids = [org]
        if include_children:
            child_query = """
                WITH RECURSIVE OrgTree AS (
                    SELECT id FROM org_node WHERE id = :org
                    UNION ALL
                    SELECT o.id FROM org_node o
                    INNER JOIN OrgTree ot ON o.parent_id = ot.id
                )
                SELECT id FROM OrgTree
            """
            result = conn.execute(text(child_query), {"org": org})
            org_ids = [row["id"] for row in result.mappings()]

        # Query to fetch documents for the given OrgID(s)
        query = f"SELECT * FROM requested_links WHERE OrgID IN ({','.join([':id' + str(i) for i in range(len(org_ids))])})"
        params = {f"id{i}": org_id for i, org_id in enumerate(org_ids)}

        # Execute the query
        result = conn.execute(text(query), params)
        rows = [dict(row) for row in result.mappings()]  # Use .mappings() to convert rows to dictionaries

    if not rows:
        return JSONResponse({
            "status": "no_data",
            "message": f"No documents found for OrgID={org}",
            "count": 0
        })

    # Initialize the PDFDownloader
    downloader = PDFDownloader(db_path="uno.db", download_dir="data/downloads")
    download_summary = downloader.download_all_documents(rows)

    return JSONResponse({
        "status": "ok",
        "orgid": org,
        "include_children": include_children,
        "total_docs": len(rows),
        "download_summary": download_summary
    })