import re
import pandas as pd
import streamlit as st

from core.config import REQUIRED_COLS, C


# -------------------------
# Supabase client
# -------------------------

def _get_supabase_client():
    from supabase import create_client
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)


# -------------------------
# Low-level helpers
# -------------------------

def _normalize_county_key(x: str) -> str:
    """
    Forgiving county join key:
    - uppercase
    - remove the word 'COUNTY'
    - remove anything that's not A-Z
    """
    s = "" if x is None else str(x)
    s = s.upper().strip()
    s = re.sub(r"\bCOUNTY\b", "", s)
    s = re.sub(r"[^A-Z]", "", s)
    return s


def _normalize_status(series: pd.Series) -> pd.Series:
    """
    Canonicalize to exactly:
      - 'sold'
      - 'cut loose'
    Everything else becomes ''.
    Handles both Google Sheets values and Supabase `path` values.
    """
    s = series.fillna("").astype(str).str.strip().str.lower()
    compact = (
        s.str.replace(r"[\s\-_/]+", "", regex=True)
         .str.replace(r"[^a-z]", "", regex=True)
    )

    out = pd.Series([""] * len(s), index=s.index, dtype="object")
    # Sold — covers "sold", "closed", "closedwon" (Supabase "Closed/Won")
    out.loc[compact.isin(["sold", "closed", "close", "closing", "settled", "closedwon"])] = "sold"
    # Cut Loose — covers "cutloose", "contractcancelledlost" (Supabase path)
    out.loc[compact.isin(["cutloose", "cutlose", "cut", "contractcancelledlost"])] = "cut loose"
    return out


def _to_number(series: pd.Series) -> pd.Series:
    """Convert money-like strings to floats. "$74,000" -> 74000.0 ; "" -> NaN"""
    if series is None:
        return pd.Series(dtype="float64")
    s = series.astype(str).str.replace(r"[\$,]", "", regex=True).str.strip()
    s = s.replace({"": None, "nan": None, "None": None})
    return pd.to_numeric(s, errors="coerce")


# -------------------------
# Phase A2: Single source of truth normalization
# -------------------------

def normalize_inputs(df: pd.DataFrame) -> pd.DataFrame:
    """
    One place to harden and normalize the raw deals data.

    Guarantees these columns exist and are correct:
      - County_clean_up, County_key
      - Buyer_clean
      - Status_norm
      - Date_dt, Year
    Also ensures optional columns exist (no KeyErrors).
    """
    df = df.copy()

    # Ensure expected columns exist (even if source changes)
    optional_cols = [
        "Salesforce_URL", "Buyer", "Date", "Status", "County", "Address", "City",
        "Dispo Rep", "Contract Price", "Amended Price", "Wholesale Price",
        "Market", "Acquisition Rep",
    ]
    for col in optional_cols:
        if col not in df.columns:
            df[col] = ""

    # --- County normalization ---
    county_raw = df[C.county].astype(str).fillna("").str.strip().str.upper()
    county_clean = county_raw.str.replace(r"\s+COUNTY\b", "", regex=True).str.strip()
    county_clean = county_clean.replace({"STEWART COUTY": "STEWART"})
    df["County_clean_up"] = county_clean
    df["County_key"] = df["County_clean_up"].apply(_normalize_county_key)

    # --- Buyer normalization ---
    df["Buyer_clean"] = df[C.buyer].astype(str).fillna("").str.strip()

    # --- Status normalization ---
    df["Status_norm"] = _normalize_status(df[C.status])

    # --- Date parsing ---
    df["Date_dt"] = pd.to_datetime(df.get(C.date), errors="coerce")
    df["Year"] = df["Date_dt"].dt.year

    # --- Dispo Rep ---
    dispo_col = None
    for cand in ["Dispo Rep", "Dispo_Rep", "DispoRep", "DISPO REP"]:
        if cand in df.columns:
            dispo_col = cand
            break
    df["Dispo_Rep"] = df[dispo_col] if dispo_col else ""
    df["Dispo_Rep_clean"] = df["Dispo_Rep"].astype(str).fillna("").str.strip()

    # --- Market + Acquisition Rep ---
    if "Market" not in df.columns:
        df["Market"] = ""
    df["Market_clean"] = df["Market"].astype(str).fillna("").str.strip()

    if "Acquisition Rep" not in df.columns:
        df["Acquisition Rep"] = ""
    df["Acquisition_Rep_clean"] = df["Acquisition Rep"].astype(str).fillna("").str.strip()

    # --- Financials (numeric) ---
    df["Contract_Price_num"] = _to_number(df.get("Contract Price"))
    df["Amended_Price_num"] = _to_number(df.get("Amended Price"))
    df["Wholesale_Price_num"] = _to_number(df.get("Wholesale Price"))

    # Effective contract price = amended if present, else contract
    df["Effective_Contract_Price"] = df["Contract_Price_num"]
    has_amended = df["Amended_Price_num"].notna()
    df.loc[has_amended, "Effective_Contract_Price"] = df.loc[has_amended, "Amended_Price_num"]

    # Gross Profit = Wholesale - Effective Contract
    df["Gross_Profit"] = df["Wholesale_Price_num"] - df["Effective_Contract_Price"]

    return df


def normalize_tiers(tiers: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize the MAO tiers data into the format expected by the app.
    Returns: County_clean_up, County_key, MAO_Tier, MAO_Range_Str
    """
    out_cols = ["County_clean_up", "County_key", "MAO_Tier", "MAO_Range_Str"]
    if tiers is None or tiers.empty:
        return pd.DataFrame(columns=out_cols)

    tiers = tiers.copy()
    tiers.columns = [str(c).strip() for c in tiers.columns]

    # County column (case-insensitive search)
    county_col = next(
        (c for c in tiers.columns if str(c).strip().lower() in ("county", "county_name", "countyname")),
        tiers.columns[0],
    )

    # Tier column
    tier_col = next(
        (c for c in tiers.columns if str(c).strip().lower() in ("tier", "mao tier", "mao_tier")),
        None,
    )

    # Min/Max columns
    min_col = next(
        (c for c in tiers.columns if str(c).strip().lower() in ("mao min", "mao_min", "min")),
        None,
    )
    max_col = next(
        (c for c in tiers.columns if str(c).strip().lower() in ("mao max", "mao_max", "max")),
        None,
    )

    df = pd.DataFrame()

    county_raw = tiers[county_col].astype(str).fillna("").str.strip().str.upper()
    county_clean = county_raw.str.replace(r"\s+COUNTY\b", "", regex=True).str.strip()
    county_clean = county_clean.replace({"STEWART COUTY": "STEWART"})
    df["County_clean_up"] = county_clean
    df["County_key"] = df["County_clean_up"].apply(_normalize_county_key)

    df["MAO_Tier"] = tiers[tier_col].astype(str).str.strip() if tier_col else ""

    if min_col and max_col:
        def to_pct(x):
            try:
                v = float(x)
                return v * 100.0 if v <= 1.0 else v
            except Exception:
                return None

        mins = tiers[min_col].apply(to_pct)
        maxs = tiers[max_col].apply(to_pct)

        def fmt_range(lo, hi):
            if lo is None and hi is None:
                return ""
            if lo is None:
                return f"≤{hi:.0f}%"
            if hi is None:
                return f"≥{lo:.0f}%"
            return f"{lo:.0f}%–{hi:.0f}%"

        df["MAO_Range_Str"] = [fmt_range(lo, hi) for lo, hi in zip(mins, maxs)]
    else:
        df["MAO_Range_Str"] = ""

    return df[out_cols]


# -------------------------
# Cached loaders
# -------------------------

@st.cache_data(ttl=300, show_spinner=False)
def load_mao_tiers() -> pd.DataFrame:
    client = _get_supabase_client()
    resp = client.table("mao_tiers").select("county, tier, mao_min, mao_max").execute()
    raw = pd.DataFrame(resp.data or [])
    return normalize_tiers(raw)


@st.cache_data(ttl=300, show_spinner=False)
def load_data() -> pd.DataFrame:
    client = _get_supabase_client()

    cols = (
        "property_address, county, transaction_link, path, assigned_buyer, "
        "desired_closing_date, contract_release_date, dispositions_rep, "
        "contract_purchase_price, amended_purchase_price, wholesale_sales_price, "
        "market, acquisition_rep"
    )
    all_rows = []
    page_size = 1000
    offset = 0
    while True:
        resp = (
            client.table("closed_deals")
            .select(cols)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = resp.data or []
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    raw = pd.DataFrame(all_rows)

    # --- Rename Supabase columns → app column names ---
    raw = raw.rename(columns={
        "property_address":        "Address",
        "county":                  "County",
        "transaction_link":        "Salesforce_URL",
        "assigned_buyer":          "Buyer",
        "dispositions_rep":        "Dispo Rep",
        "contract_purchase_price": "Contract Price",
        "amended_purchase_price":  "Amended Price",
        "wholesale_sales_price":   "Wholesale Price",
        "market":                  "Market",
        "acquisition_rep":         "Acquisition Rep",
    })

    # --- Map path → Status ---
    # Supabase: "Closed/Won" | "Contract Cancelled/Lost"
    path_map = {
        "Closed/Won":                "Sold",
        "Contract Cancelled/Lost":   "Cut Loose",
    }
    raw["Status"] = raw["path"].map(path_map).fillna(raw.get("path", ""))

    # --- Derive Date: closing date for sold deals, release date for cut loose ---
    # Coalesce: prefer desired_closing_date, fall back to contract_release_date
    closing = pd.to_datetime(raw.get("desired_closing_date"), errors="coerce")
    release = pd.to_datetime(raw.get("contract_release_date"), errors="coerce")
    raw["Date"] = closing.combine_first(release)

    # --- City: not stored in Supabase; add empty column so app doesn't break ---
    raw["City"] = ""

    # --- Validate required columns ---
    missing = [c for c in REQUIRED_COLS if c not in raw.columns]
    if missing:
        raise ValueError(f"Missing required columns after Supabase load: {missing}")

    df = normalize_inputs(raw)

    # --- Merge MAO tiers ---
    try:
        tiers = load_mao_tiers()
        if not tiers.empty:
            df = df.merge(
                tiers[["County_key", "MAO_Tier", "MAO_Range_Str"]],
                on="County_key",
                how="left",
            )
    except Exception as e:
        st.warning(f"Could not load/merge MAO tiers (showing blank tiers). Details: {type(e).__name__}")
        df["MAO_Tier"] = ""
        df["MAO_Range_Str"] = ""

    return df
