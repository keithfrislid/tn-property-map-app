# RHD Deal Intelligence — Claude Context

## Project Overview

**App Name:** RHD Deal Intelligence
**Type:** Streamlit analytics web application
**Purpose:** Interactive Tennessee county property map and deal intelligence platform for a real estate operations team.
**Entry Point:** `app.py` → `app_controller.py` → view files

---

## Architecture at a Glance

```
app.py                        # Thin entrypoint (init_state + run_app)
app_controller.py             # Main orchestration & wiring
app_sections.py               # Sidebar & map interaction handlers
core/
  config.py                   # Column definitions, map/page defaults
  state.py                    # Session state initialization
  colors.py                   # Color schemes & coloring logic
data/
  data.py                     # Supabase data loading & normalization (5 min cache)
  filters.py                  # Data filtering & selection logic
  enrich.py                   # GeoJSON enrichment for map rendering
  geo.py                      # County adjacency via Shapely
  map_build.py                # Folium map construction
  momentum.py                 # Buyer momentum calculations (▲▼→)
  scoring.py                  # Health score: close_rate * log(1 + deals), 0–100
calculators/
  calculator_logic.py         # Acquisitions feasibility calculator logic
  calculator_support.py       # Calculator helpers
views/
  map_view.py                 # Map + below-map panel
  acquisitions_view.py        # Acquisitions tabs wrapper
  acquisitions_calculator.py  # Acquisitions calculator UI
  admin.py                    # Admin auth & financial dashboard
  admin_view.py               # Admin tabs wrapper
services/
  controller_services.py      # Pure service helpers (no Streamlit UI)
ui/
  controls.py                 # Top filter controls
  ui_sidebar.py               # Sidebar rendering
debug/
  debug_tools.py              # Debug panel (enable via ?debug=1 in URL)
tests/
  test_smoke.py               # Smoke tests (pytest)
scripts/
  migrate_dispo_rep.py        # Data migration utility
  populate_mao_tiers.py       # MAO tier batch loader
  setup_mao_tiers.sql         # Supabase SQL schema for mao_tiers
.streamlit/
  secrets.toml                # Supabase credentials + optional admin password
.github/workflows/
  tests.yml                   # CI: pytest on push to main + PRs (Python 3.11)
tn_counties.geojson           # Local backup GeoJSON (remote Plotly dataset preferred)
```

---

## Data Source

**Backend:** Supabase (PostgreSQL)
**Recently migrated from:** Google Sheets (commit `6515b15`)

### Tables

| Table | Purpose |
|-------|---------|
| `closed_deals` | All property transactions (sold + cut loose) |
| `mao_tiers` | Maximum Allowable Offer tier bands per county (A–D) |

### Supabase → App Column Mapping

| Supabase Column | App Column |
|----------------|-----------|
| `property_address` | `Address` |
| `county` | `County` |
| `transaction_link` | `Salesforce_URL` |
| `assigned_buyer` | `Buyer` |
| `dispositions_rep` | `Dispo Rep` |
| `contract_purchase_price` | `Contract Price` |
| `amended_purchase_price` | `Amended Price` |
| `wholesale_sales_price` | `Wholesale Price` |
| `market` | `Market` |
| `acquisition_rep` | `Acquisition Rep` |
| `city` | `City` |
| `rhd_buyer_agent_commission` | `RHD Buyer Agent Commission` |
| `path` | → `Status` ("Closed/Won" = sold, "Contract Cancelled/Lost" = cut loose) |

### Derived/Normalized Columns (from `data.normalize_inputs()`)

- `County_clean_up` — uppercase, no "COUNTY" suffix
- `County_key` — alphanumeric only, for GeoJSON joining
- `Status_norm` — "sold" | "cut loose" | ""
- `Date_dt`, `Year`
- `Buyer_clean`, `Dispo_Rep_clean`, `Market_clean`, `Acquisition_Rep_clean`
- `Contract_Price_num`, `Amended_Price_num`, `Wholesale_Price_num`
- `Effective_Contract_Price` — Amended if present, else Contract
- `RHD_Buyer_Agent_Commission_num` — Commission as float (NULL → 0)
- `Gross_Profit` — Wholesale minus Effective Contract minus RHD Buyer Agent Commission
- `MAO_Tier`, `MAO_Range_Str` — joined from mao_tiers table

---

## Three Team Views

### 1. Dispo View (Operations/Outcomes)
- Tracks Sold vs Cut Loose outcomes by county
- Filters: Year, Status Mode, Buyer (with momentum ▲▼→), Dispo Rep, Acquisition Rep
- Map colors: Green (Sold), Red (Cut Loose), Blue (Both)
- Below-map panel: county details, property list, top buyers

### 2. Acquisitions View (Buyers & Feasibility)
- Assesses county-level buyer depth and acquisition feasibility
- Map colors: MAO tier-based (Green A → Red D)
- Includes **RHD Feasibility Calculator** tab:
  - Input: proposed contract price + county
  - Uses historical pricing data and pricing "cliffs"
  - Falls back to neighboring counties (BFS, max 2 hops) if < 15 deals
  - Confidence: High (30+ deals), Medium (15+), Low (<15)
  - Output: "Accept" / "Caution" / "Decline" recommendation

### 3. Admin View (Financial Dashboard)
- Password-gated (Streamlit secrets or `SALES_MANAGER_PASSWORD` env var)
- 2-hour session timeout
- Metrics: Total GP, Wholesale Volume, Sold Deal Count, Avg GP/Deal
- Charts: GP by Month/Quarter, GP by Dispo Rep (pie), GP by Market (pie)
- Table: County GP rankings + CSV export

---

## Key Algorithms

### Health Score (`data/scoring.py`)
```
score = close_rate * log(1 + total_deals), normalized to 0–100
```

### Buyer Momentum (`data/momentum.py`)
- Compares last 12 months vs previous 12 months
- Visual indicators: ▲ (growing), ▼ (declining), → (flat)

### County Adjacency (`data/geo.py`)
- Uses Shapely geometry to find neighboring counties
- Cached (O(n²) over 95 TN counties, acceptable)
- Used by feasibility calculator for fallback data

### Acquisitions Feasibility Calculator (`calculators/calculator_logic.py`)
- Bins deals by price (adaptive bin size)
- Computes cut rate per bin
- Finds "tail cut rate" for prices ≥ proposed price
- `MIN_SUPPORT_N=15`, `MAX_HOPS=2`

---

## Caching Strategy

All expensive operations cached with 5-minute TTL (`@st.cache_data(ttl=300)`):
- `load_data()` — Supabase closed_deals
- `load_mao_tiers()` — Supabase mao_tiers
- `load_tn_geojson()` — Remote Plotly TN counties GeoJSON
- `build_county_adjacency()` — Shapely geometry computation

---

## Session State Keys

| Key | Purpose |
|-----|---------|
| `team_view` | Current view (Dispo/Acquisitions/Admin) |
| `selected_county` | Map-clicked county (Dispo) |
| `acq_selected_county` | Selected county (Acquisitions) |
| `county_source` | Origin of selection (map/dropdown) |
| `last_map_clicked_county` | Most recent map click |
| `last_map_synced_county` | Last county synced to dropdown |
| `county_quick_search` | Shared dropdown placeholder |
| `dispo_rep_choice` | Selected Dispo Rep filter |
| `dispo_acq_rep_choice` | Selected Acquisition Rep (Dispo view) |
| `sales_manager_authed` | Admin auth flag |
| `sales_manager_authed_at` | Auth timestamp (2-hour timeout) |
| `county_adjacency` | Precomputed neighbor map |
| `debug_log` | Debug event log |

---

## Map Rendering

- **Library:** Folium + streamlit-folium
- **GeoJSON:** Remote Plotly TN counties dataset (local `tn_counties.geojson` as backup)
- **Center:** lat 35.8, lon -86.4, zoom 7
- **Tile:** cartodbpositron
- Map controls disabled (no keyboard/zoom shortcuts)
- County coloring: intensity bands (1, 2–5, 6–10, >10 deals) + view-specific color palette

---

## Naming Conventions

- **Raw/computed columns:** `Snake_Case_With_Caps` (e.g., `County_clean_up`, `Status_norm`)
- **Display columns:** Title Case (e.g., `County`, `Buyer`)
- **Functions — render/UI:** `render_*`
- **Functions — compute:** `compute_*`, `build_*`
- **Functions — filter/apply:** `apply_*`, `split_*`
- **Functions — transform:** `enrich_*`, `normalize_*`

---

## Testing & CI/CD

- **Tests:** `tests/test_smoke.py` (2 smoke tests via pytest)
- **CI:** GitHub Actions — runs on push to `main` and all PRs
- **Python:** 3.11

---

## Secrets & Environment Variables

| Variable | Source | Purpose |
|----------|--------|---------|
| `supabase.url` | `.streamlit/secrets.toml` | Supabase project URL |
| `supabase.key` | `.streamlit/secrets.toml` | Supabase service role key |
| `SALES_MANAGER_PASSWORD` | env var or secrets | Admin dashboard password |
| `debug` | secrets or `?debug=1` URL param | Enable debug panel |

---

## Recent History

- **Latest:** Migrated data source from Google Sheets to Supabase (`6515b15`)
- Prior work: Debugging branch merged (PR #29), CI/CD test fixes
