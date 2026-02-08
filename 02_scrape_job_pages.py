"""
Step 2: Scrape USAJOBS pages for CDC job postings.
Saves each job as a separate text file in data/scraped_jobs/{control_number}.txt.
Resumable - checks which files already exist and skips them.

Usage:
    python 02_scrape_job_pages.py              # scrape all remaining
    python 02_scrape_job_pages.py --limit 5    # scrape only 5 jobs (for testing)
    python 02_scrape_job_pages.py --status      # just print progress, don't scrape
"""

import argparse
import pandas as pd
import requests
import time
import json
from pathlib import Path
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).parent / "data"
INPUT_FILE = DATA_DIR / "cdc_jobs_2021_2025.parquet"
SCRAPED_DIR = DATA_DIR / "scraped_jobs"

REQUEST_DELAY = 1.0


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (research project; CDC job analysis)",
        "Accept": "text/html,application/xhtml+xml",
    })
    return session


def extract_job_text(html: str) -> str:
    """Extract the main content text from a USAJOBS job page."""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.find("div", {"role": "main"}) or soup.body
    if main:
        return main.get_text(separator="\n", strip=True)
    return soup.get_text(separator="\n", strip=True)


def scrape_job(session: requests.Session, control_number: int) -> tuple[str | None, int]:
    """Scrape a single USAJOBS posting. Returns (text, http_status)."""
    url = f"https://www.usajobs.gov/job/{control_number}"
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 200:
            return extract_job_text(resp.text), 200
        return None, resp.status_code
    except requests.RequestException:
        return None, 0


def already_scraped(control_number: int) -> bool:
    return (SCRAPED_DIR / f"{control_number}.txt").exists()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Max jobs to scrape this run (for testing)")
    parser.add_argument("--status", action="store_true",
                        help="Just print progress, don't scrape")
    args = parser.parse_args()

    SCRAPED_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(INPUT_FILE)
    all_cns = df["usajobsControlNumber"].tolist()
    done = [cn for cn in all_cns if already_scraped(cn)]
    remaining = [cn for cn in all_cns if not already_scraped(cn)]

    print(f"Total CDC jobs: {len(all_cns):,}")
    print(f"Already scraped: {len(done):,}")
    print(f"Remaining: {len(remaining):,}")

    if args.status:
        return

    if not remaining:
        print("All jobs already scraped!")
        return

    to_scrape = remaining[:args.limit] if args.limit else remaining
    print(f"\nScraping {len(to_scrape):,} jobs this run...")

    session = make_session()
    successes = 0
    failures = 0

    for i, cn in enumerate(to_scrape):
        text, status = scrape_job(session, cn)
        if text:
            (SCRAPED_DIR / f"{cn}.txt").write_text(text, encoding="utf-8")
            successes += 1
            print(".", end="", flush=True)
        else:
            failures += 1
            print(f"X({status})", end="", flush=True)

        if (i + 1) % 50 == 0:
            print(f" [{i+1}/{len(to_scrape)}]")

        time.sleep(REQUEST_DELAY)

    print(f"\n\nDone. {successes:,} saved, {failures:,} failed.")


if __name__ == "__main__":
    main()
