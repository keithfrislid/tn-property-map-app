"""
migrate_dispo_rep.py
--------------------
One-time script: backfills the `dispositions_rep` column in the Supabase
`closed_deals` table using exported CSV data (e.g. from your Google Sheet).

Match key: transaction_link (Supabase) == Salesforce_URL (CSV column)

Usage:
    python scripts/migrate_dispo_rep.py path/to/your_export.csv

The script reads Supabase credentials from .streamlit/secrets.toml automatically.
"""

import sys
import pathlib
import re
import csv

# ---------------------------------------------------------------------------
# Credential loader — reads from .streamlit/secrets.toml
# ---------------------------------------------------------------------------

def _load_supabase_creds() -> tuple[str, str]:
    secrets_path = pathlib.Path(__file__).parent.parent / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        raise FileNotFoundError(
            f"Could not find {secrets_path}. "
            "Make sure .streamlit/secrets.toml exists with [supabase] url and key."
        )
    text = secrets_path.read_text(encoding="utf-8")
    url_match = re.search(r'url\s*=\s*"([^"]+)"', text)
    key_match = re.search(r'key\s*=\s*"([^"]+)"', text)
    if not url_match or not key_match:
        raise ValueError("Could not parse url/key from .streamlit/secrets.toml")
    return url_match.group(1), key_match.group(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/migrate_dispo_rep.py <path_to_csv>")
        sys.exit(1)

    csv_path = pathlib.Path(sys.argv[1])
    if not csv_path.exists():
        print(f"ERROR: File not found: {csv_path}")
        sys.exit(1)

    # --- Load CSV ---
    print(f"Reading CSV: {csv_path}")
    mapping: dict[str, str] = {}   # transaction_link -> dispo_rep value

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        # Flexible column detection
        url_col = next(
            (h for h in headers if h.strip().lower() in ("salesforce_url", "salesforce url", "sf_url")),
            None,
        )
        dispo_col = next(
            (h for h in headers if h.strip().lower() in ("dispo rep", "dispo_rep", "dispositions_rep", "dispositions rep")),
            None,
        )

        if not url_col:
            print(f"ERROR: Could not find Salesforce_URL column. Headers found: {headers}")
            sys.exit(1)
        if not dispo_col:
            print(f"ERROR: Could not find 'Dispo Rep' column. Headers found: {headers}")
            sys.exit(1)

        print(f"  URL column   : '{url_col}'")
        print(f"  Dispo column : '{dispo_col}'")

        skipped_no_url = 0
        skipped_no_dispo = 0

        for row in reader:
            url = (row.get(url_col) or "").strip()
            dispo = (row.get(dispo_col) or "").strip()
            if not url:
                skipped_no_url += 1
                continue
            if not dispo:
                skipped_no_dispo += 1
                continue
            mapping[url] = dispo

    print(f"  Rows with valid URL + Dispo Rep : {len(mapping)}")
    print(f"  Rows skipped (no URL)           : {skipped_no_url}")
    print(f"  Rows skipped (no Dispo Rep)     : {skipped_no_dispo}")

    if not mapping:
        print("Nothing to update. Exiting.")
        return

    # --- Connect to Supabase ---
    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: supabase package not installed. Run: pip install supabase")
        sys.exit(1)

    url, key = _load_supabase_creds()
    print(f"\nConnecting to Supabase: {url}")
    client = create_client(url, key)

    # --- Fetch all closed_deals transaction_links (in one query) ---
    print("Fetching existing records from closed_deals...")
    resp = client.table("closed_deals").select("id, transaction_link, dispositions_rep").execute()
    existing = resp.data or []
    print(f"  Found {len(existing)} total records in closed_deals")

    # Build lookup: transaction_link -> row id
    link_to_id: dict[str, str] = {}
    for row in existing:
        link = (row.get("transaction_link") or "").strip()
        if link:
            link_to_id[link] = row["id"]

    # --- Update records ---
    updated = 0
    not_found = 0
    already_set = 0
    errors = 0

    # Build a quick lookup of existing dispo values
    link_to_current_dispo: dict[str, str] = {
        (r.get("transaction_link") or "").strip(): (r.get("dispositions_rep") or "").strip()
        for r in existing
    }

    print(f"\nUpdating dispositions_rep for {len(mapping)} records...")

    for sf_url, dispo_rep in mapping.items():
        row_id = link_to_id.get(sf_url)
        if not row_id:
            not_found += 1
            continue

        current = link_to_current_dispo.get(sf_url, "")
        if current == dispo_rep:
            already_set += 1
            continue

        try:
            client.table("closed_deals").update(
                {"dispositions_rep": dispo_rep}
            ).eq("id", row_id).execute()
            updated += 1
        except Exception as e:
            print(f"  ERROR updating {sf_url}: {e}")
            errors += 1

    print("\n--- Results ---")
    print(f"  Updated       : {updated}")
    print(f"  Already set   : {already_set}")
    print(f"  Not found     : {not_found}")
    print(f"  Errors        : {errors}")
    print("Done.")


if __name__ == "__main__":
    main()
