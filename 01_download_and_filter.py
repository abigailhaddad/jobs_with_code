"""
Step 1: Download USAJOBS historical parquet files for 2021-2025,
filter for CDC jobs, and save a combined CDC-only parquet.
"""

import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

BASE_URL = "https://github.com/abigailhaddad/usajobs_historical/raw/main/data/"
YEARS = [2021, 2022, 2023, 2024, 2025]
OUTPUT_FILE = DATA_DIR / "cdc_jobs_2021_2025.parquet"


def download_and_filter_year(year: int) -> pd.DataFrame:
    """Download a single year's parquet and filter for CDC rows."""
    url = f"{BASE_URL}historical_jobs_{year}.parquet"
    print(f"Downloading {year}...")
    df = pd.read_parquet(url)
    print(f"  {year}: {len(df):,} total jobs")

    # Look for CDC in agency/department/subelement names
    cdc_mask = (
        df["hiringAgencyName"].str.contains("Centers for Disease Control", case=False, na=False)
        | df["hiringAgencyName"].str.contains("CDC", case=True, na=False)
        | df["hiringDepartmentName"].str.contains("Centers for Disease Control", case=False, na=False)
    )
    cdc_df = df[cdc_mask].copy()
    print(f"  {year}: {len(cdc_df):,} CDC jobs")
    return cdc_df


def main():
    frames = []
    for year in YEARS:
        cdc_df = download_and_filter_year(year)
        frames.append(cdc_df)

    combined = pd.concat(frames, ignore_index=True)

    # Deduplicate by usajobsControlNumber (keep first occurrence)
    before = len(combined)
    combined = combined.drop_duplicates(subset=["usajobsControlNumber"], keep="first")
    after = len(combined)
    print(f"\nDeduplication: {before:,} -> {after:,} ({before - after:,} duplicates removed)")

    # Build USAJOBS URL
    combined["usajobs_url"] = "https://www.usajobs.gov/job/" + combined["usajobsControlNumber"].astype(str)

    combined.to_parquet(OUTPUT_FILE, index=False)
    print(f"\nSaved {len(combined):,} CDC jobs to {OUTPUT_FILE}")

    # Summary stats
    print("\n--- Summary ---")
    print(f"Unique agency names in CDC data:")
    for name in sorted(combined["hiringAgencyName"].dropna().unique()):
        count = (combined["hiringAgencyName"] == name).sum()
        print(f"  {name}: {count:,}")
    print(f"\nDate range: {combined['positionOpenDate'].min()} to {combined['positionOpenDate'].max()}")
    print(f"Unique positions: {combined['positionTitle'].nunique():,}")
    print(f"\nSample USAJOBS URLs:")
    for url in combined["usajobs_url"].head(5):
        print(f"  {url}")


if __name__ == "__main__":
    main()
