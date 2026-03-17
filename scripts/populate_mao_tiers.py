"""
populate_mao_tiers.py
---------------------
One-time script: creates and populates the `mao_tiers` table in Supabase.

Steps:
  1. Run scripts/setup_mao_tiers.sql in the Supabase SQL Editor first.
  2. Then run: python scripts/populate_mao_tiers.py

Reads Supabase credentials from .streamlit/secrets.toml automatically.
Uses upsert (on county conflict) so it's safe to re-run.
"""

import pathlib
import re
import sys

# ---------------------------------------------------------------------------
# MAO tier data (sourced from MAO Tiers sheet)
# ---------------------------------------------------------------------------

MAO_TIERS = [
    # Tier A — 73%–77%
    ("Davidson County",    "A", 0.73, 0.77),
    ("Dickson County",     "A", 0.73, 0.77),
    ("Montgomery County",  "A", 0.73, 0.77),
    ("Putnam County",      "A", 0.73, 0.77),
    ("Robertson County",   "A", 0.73, 0.77),
    ("Rutherford County",  "A", 0.73, 0.77),
    ("Sumner County",      "A", 0.73, 0.77),
    ("Williamson County",  "A", 0.73, 0.77),
    ("Wilson County",      "A", 0.73, 0.77),

    # Tier B — 68%–72%
    ("Anderson County",    "B", 0.68, 0.72),
    ("Bedford County",     "B", 0.68, 0.72),
    ("Blount County",      "B", 0.68, 0.72),
    ("Bradley County",     "B", 0.68, 0.72),
    ("Campbell County",    "B", 0.68, 0.72),
    ("Carroll County",     "B", 0.68, 0.72),
    ("Cheatham County",    "B", 0.68, 0.72),
    ("Coffee County",      "B", 0.68, 0.72),
    ("Cumberland County",  "B", 0.68, 0.72),
    ("Franklin County",    "B", 0.68, 0.72),
    ("Gibson County",      "B", 0.68, 0.72),
    ("Giles County",       "B", 0.68, 0.72),
    ("Hamblen County",     "B", 0.68, 0.72),
    ("Hardeman County",    "B", 0.68, 0.72),
    ("Hardin County",      "B", 0.68, 0.72),
    ("Hawkins County",     "B", 0.68, 0.72),
    ("Henry County",       "B", 0.68, 0.72),
    ("Knox County",        "B", 0.68, 0.72),
    ("Lawrence County",    "B", 0.68, 0.72),
    ("Lincoln County",     "B", 0.68, 0.72),
    ("Loudon County",      "B", 0.68, 0.72),
    ("Madison County",     "B", 0.68, 0.72),
    ("Marion County",      "B", 0.68, 0.72),
    ("Maury County",       "B", 0.68, 0.72),
    ("McMinn County",      "B", 0.68, 0.72),
    ("Obion County",       "B", 0.68, 0.72),
    ("Polk County",        "B", 0.68, 0.72),
    ("Rhea County",        "B", 0.68, 0.72),
    ("Roane County",       "B", 0.68, 0.72),
    ("Sequatchie County",  "B", 0.68, 0.72),
    ("Sevier County",      "B", 0.68, 0.72),
    ("Stewart County",     "B", 0.68, 0.72),
    ("Sullivan County",    "B", 0.68, 0.72),
    ("Washington County",  "B", 0.68, 0.72),
    ("Wayne County",       "B", 0.68, 0.72),
    ("Weakley County",     "B", 0.68, 0.72),
    ("White County",       "B", 0.68, 0.72),

    # Tier C — 61%–66%
    ("Benton County",      "C", 0.61, 0.66),
    ("Cannon County",      "C", 0.61, 0.66),
    ("Chester County",     "C", 0.61, 0.66),
    ("Claiborne County",   "C", 0.61, 0.66),
    ("Cocke County",       "C", 0.61, 0.66),
    ("Crockett County",    "C", 0.61, 0.66),
    ("Decatur County",     "C", 0.61, 0.66),
    ("DeKalb County",      "C", 0.61, 0.66),
    ("Dyer County",        "C", 0.61, 0.66),
    ("Fayette County",     "C", 0.61, 0.66),
    ("Fentress County",    "C", 0.61, 0.66),
    ("Grundy County",      "C", 0.61, 0.66),
    ("Haywood County",     "C", 0.61, 0.66),
    ("Henderson County",   "C", 0.61, 0.66),
    ("Hickman County",     "C", 0.61, 0.66),
    ("Houston County",     "C", 0.61, 0.66),
    ("Humphreys County",   "C", 0.61, 0.66),
    ("Jackson County",     "C", 0.61, 0.66),
    ("Lake County",        "C", 0.61, 0.66),
    ("Lauderdale County",  "C", 0.61, 0.66),
    ("Lewis County",       "C", 0.61, 0.66),
    ("Macon County",       "C", 0.61, 0.66),
    ("Marshall County",    "C", 0.61, 0.66),
    ("McNairy County",     "C", 0.61, 0.66),
    ("Moore County",       "C", 0.61, 0.66),
    ("Morgan County",      "C", 0.61, 0.66),
    ("Overton County",     "C", 0.61, 0.66),
    ("Perry County",       "C", 0.61, 0.66),
    ("Scott County",       "C", 0.61, 0.66),
    ("Smith County",       "C", 0.61, 0.66),
    ("Tipton County",      "C", 0.61, 0.66),
    ("Trousdale County",   "C", 0.61, 0.66),
    ("Union County",       "C", 0.61, 0.66),
    ("Van Buren County",   "C", 0.61, 0.66),
    ("Warren County",      "C", 0.61, 0.66),

    # Tier D — 53%–58%
    ("Bledsoe County",     "D", 0.53, 0.58),
    ("Carter County",      "D", 0.53, 0.58),
    ("Clay County",        "D", 0.53, 0.58),
    ("Grainger County",    "D", 0.53, 0.58),
    ("Greene County",      "D", 0.53, 0.58),
    ("Hamilton County",    "D", 0.53, 0.58),
    ("Hancock County",     "D", 0.53, 0.58),
    ("Jefferson County",   "D", 0.53, 0.58),
    ("Johnson County",     "D", 0.53, 0.58),
    ("Meigs County",       "D", 0.53, 0.58),
    ("Monroe County",      "D", 0.53, 0.58),
    ("Pickett County",     "D", 0.53, 0.58),
    ("Shelby County",      "D", 0.53, 0.58),
    ("Unicoi County",      "D", 0.53, 0.58),
]


# ---------------------------------------------------------------------------
# Credential loader
# ---------------------------------------------------------------------------

def _load_supabase_creds() -> tuple[str, str]:
    secrets_path = pathlib.Path(__file__).parent.parent / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        raise FileNotFoundError(f"Could not find {secrets_path}")
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
    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: supabase package not installed. Run: pip install supabase")
        sys.exit(1)

    url, key = _load_supabase_creds()
    print(f"Connecting to Supabase: {url}")
    client = create_client(url, key)

    rows = [
        {"county": county, "tier": tier, "mao_min": mao_min, "mao_max": mao_max}
        for county, tier, mao_min, mao_max in MAO_TIERS
    ]

    print(f"Upserting {len(rows)} MAO tier rows...")
    resp = client.table("mao_tiers").upsert(rows, on_conflict="county").execute()
    print(f"Done. Rows affected: {len(resp.data)}")


if __name__ == "__main__":
    main()
