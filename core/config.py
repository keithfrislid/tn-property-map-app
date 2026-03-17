# config.py
from dataclasses import dataclass
from pathlib import Path

# Base directory of the repo
BASE_DIR = Path(__file__).resolve().parent

# -----------------------------
# Data / files
# -----------------------------

# Columns that must be present after loading + renaming from Supabase
# (City is not in Supabase; it is added as an empty column in data.py)
REQUIRED_COLS = {"Address", "County", "Salesforce_URL"}

# GeoJSON file (local, in repo root)
GEOJSON_LOCAL_PATH = BASE_DIR / "tn_counties.geojson"

# -----------------------------
# Streamlit page config
# -----------------------------
DEFAULT_PAGE = dict(
    page_title="TN Property Map",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -----------------------------
# Map defaults
# -----------------------------
MAP_DEFAULTS = dict(
    center_lat=35.8,
    center_lon=-86.4,
    zoom_start=7,
    tiles="cartodbpositron",
)

# -----------------------------
# Column names (single source of truth)
# These are the names used throughout the app AFTER Supabase columns
# have been renamed in data.py.
# -----------------------------
@dataclass(frozen=True)
class Cols:
    address: str = "Address"
    city: str = "City"
    county: str = "County"
    sf_url: str = "Salesforce_URL"
    status: str = "Status"
    buyer: str = "Buyer"
    date: str = "Date"

C = Cols()
