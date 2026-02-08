"""
Step 5: Combine parquet metadata + batch results into a single JSON for the web viewer.

Usage:
    python 05_build_web_data.py
    python 05_build_web_data.py --status   # just show counts
"""

import argparse
import json
import pandas as pd
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent / "data"
PARQUET_FILE = DATA_DIR / "cdc_jobs_2021_2025.parquet"
RESULTS_DIR = DATA_DIR / "batch_results"
SCRAPED_DIR = DATA_DIR / "scraped_jobs"
WEB_DATA_DIR = Path(__file__).parent / "web" / "data"

# Tools to exclude from results (not coding tools, even if mentioned in listings)
EXCLUDED_TOOLS = {
    "Johnson Controls GX9100",
    "CCT",
    "GPL",
    "LCT",
    "SharePoint",
    "Lectora",
}

# Tasks to exclude (too generic, not coding, or HVAC/building automation)
EXCLUDED_TASKS = {
    "classification",
    "analysis",
    "collection",
    "linkage",
    "mining",
    "processing",
    "coding",  # in CDC context this means medical coding (ICD codes), not programming
    "re-programming",
    "re-programming of BAS field controller logic and supervisory controller logic",
    "modifying hardware and software of Building Automation Systems (BACS) and Direct Digital Controls Systems (DDC)",
    "graphical programming (such as Johnson Controls GX9100, CCT, GPL or LCT)",
    "line coding (such as basic)",
    "ladder logic",
    "Analyze problems and identifies solutions.",
    "Evaluate commercial off the shelf software and applications to determine the merits relative to meeting the organization's needs.",
}


def safe_str(val) -> str:
    """Convert a value to string, treating NaN/None as empty string."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val)


def load_batch_result(cn: str) -> dict:
    """Load a single batch result JSON."""
    path = RESULTS_DIR / f"{cn}.json"
    if not path.exists():
        return {"coding_tools": [], "coding_tasks": []}
    return json.loads(path.read_text())


def load_scraped_text(cn: str) -> str:
    """Load the scraped job text for verification."""
    path = SCRAPED_DIR / f"{cn}.txt"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def normalize_for_matching(s: str) -> str:
    """Normalize a string for matching: strip quotes, collapse whitespace, unescape."""
    import re
    # Strip surrounding quotes the model may have added
    s = s.strip().strip('"').strip("'").strip('"').strip('"')
    # Unescape quotes
    s = s.replace('\\"', '"').replace("\\'", "'")
    # Collapse whitespace (handles newlines in scraped text)
    s = re.sub(r'\s+', ' ', s)
    return s.lower()


def verify_in_text(name: str, text: str) -> bool:
    """Check if a tool/task name appears in the scraped job text."""
    if not text or not name:
        return False
    return normalize_for_matching(name) in normalize_for_matching(text)


def parse_locations(loc_json: str) -> str:
    """Parse PositionLocations JSON array into readable string."""
    try:
        locs = json.loads(loc_json)
        parts = []
        for loc in locs:
            city = loc.get("positionLocationCity", "")
            state = loc.get("positionLocationState", "")
            if city and state:
                parts.append(f"{city}, {state}")
            elif city:
                parts.append(city)
            elif state:
                parts.append(state)
        return "; ".join(parts) if parts else ""
    except (json.JSONDecodeError, TypeError):
        return str(loc_json) if loc_json else ""


def parse_series(cat_json: str) -> str:
    """Parse JobCategories JSON array into series codes."""
    try:
        cats = json.loads(cat_json)
        return ", ".join(c.get("series", "") for c in cats if c.get("series"))
    except (json.JSONDecodeError, TypeError):
        return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    df = pd.read_parquet(PARQUET_FILE)
    result_files = set(p.stem for p in RESULTS_DIR.glob("*.json")) if RESULTS_DIR.exists() else set()

    if args.status:
        print(f"Total CDC jobs: {len(df):,}")
        print(f"Batch results available: {len(result_files):,}")
        matched = sum(1 for cn in df["usajobsControlNumber"].astype(str) if cn in result_files)
        print(f"Matched: {matched:,}")
        return

    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)

    entries = []
    all_tools = set()
    all_tasks = set()
    tools_counter = {}
    tasks_counter = {}
    years = set()
    unverified_count = 0
    total_checked = 0

    for _, row in df.iterrows():
        cn = str(row["usajobsControlNumber"])
        result = load_batch_result(cn)
        scraped_text = load_scraped_text(cn)

        tools = result.get("coding_tools", [])
        tasks = result.get("coding_tasks", [])

        tool_names = [t["name"] for t in tools if t.get("name") not in EXCLUDED_TOOLS]
        task_names = [(t["name"] if "name" in t else t.get("task", "")) for t in tasks
                      if (t.get("name") or t.get("task", "")) not in EXCLUDED_TASKS]

        def clean_name(s: str) -> str:
            """Strip surrounding quotes the model may have added."""
            return s.strip().strip('"').strip("'").strip('\u201c').strip('\u201d')

        # Verify each tool/task against scraped text
        verified_tools = []
        for name in tool_names:
            name = clean_name(name)
            if not name:
                continue
            verified = verify_in_text(name, scraped_text)
            verified_tools.append({"name": name, "verified": verified})
            if not verified:
                unverified_count += 1
            total_checked += 1

        verified_tasks = []
        for name in task_names:
            name = clean_name(name)
            if not name:
                continue
            verified = verify_in_text(name, scraped_text)
            verified_tasks.append({"name": name, "verified": verified})
            if not verified:
                unverified_count += 1
            total_checked += 1

        for t in tool_names:
            all_tools.add(t)
            tools_counter[t] = tools_counter.get(t, 0) + 1
        for t in task_names:
            all_tasks.add(t)
            tasks_counter[t] = tasks_counter.get(t, 0) + 1

        year = str(row["positionOpenDate"])[:4] if pd.notna(row["positionOpenDate"]) else ""
        years.add(year)

        location = parse_locations(row.get("PositionLocations", ""))
        series = parse_series(row.get("JobCategories", ""))

        entry = {
            "control_number": cn,
            "title": safe_str(row.get("positionTitle")),
            "series": series,
            "sub_element": safe_str(row.get("hiringSubelementName")),
            "open_date": safe_str(row.get("positionOpenDate")),
            "close_date": safe_str(row.get("positionCloseDate")),
            "year": year,
            "pay_scale": safe_str(row.get("payScale")),
            "min_grade": safe_str(row.get("minimumGrade")),
            "max_grade": safe_str(row.get("maximumGrade")),
            "location": location,
            "work_schedule": safe_str(row.get("workSchedule")),
            "appointment_type": safe_str(row.get("appointmentType")),
            "url": safe_str(row.get("usajobs_url")) or f"https://www.usajobs.gov/job/{cn}",
            "coding_tools": verified_tools,
            "coding_tasks": verified_tasks,
            "has_coding": len(tools) > 0 or len(tasks) > 0,
            "has_result": cn in result_files,
        }
        entries.append(entry)

    # Sort tools/tasks by frequency
    top_tools = sorted(tools_counter.items(), key=lambda x: -x[1])
    top_tasks = sorted(tasks_counter.items(), key=lambda x: -x[1])

    jobs_with_coding = sum(1 for e in entries if e["has_coding"])
    jobs_with_results = sum(1 for e in entries if e["has_result"])

    output = {
        "stats": {
            "total_jobs": len(entries),
            "jobs_analyzed": jobs_with_results,
            "jobs_with_coding": jobs_with_coding,
            "unique_tools": len(all_tools),
            "unique_tasks": len(all_tasks),
            "years": sorted(y for y in years if y),
        },
        "top_tools": [{"name": name, "count": count} for name, count in top_tools[:50]],
        "top_tasks": [{"name": name, "count": count} for name, count in top_tasks[:50]],
        "metadata": {
            "generated_date": datetime.now().isoformat(),
        },
        "entries": entries,
    }

    out_path = WEB_DATA_DIR / "cdc_jobs.json"
    out_path.write_text(json.dumps(output), encoding="utf-8")
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"Wrote {out_path} ({len(entries):,} entries, {size_mb:.1f} MB)")
    print(f"  Analyzed: {jobs_with_results:,}")
    print(f"  With coding tools/tasks: {jobs_with_coding:,}")
    print(f"  Unique tools: {len(all_tools)}, Unique tasks: {len(all_tasks)}")
    if total_checked:
        print(f"  Verified: {total_checked - unverified_count}/{total_checked} ({unverified_count} unverified)")
    if top_tools:
        print(f"  Top tools: {', '.join(f'{n} ({c})' for n, c in top_tools[:10])}")
    if top_tasks:
        print(f"  Top tasks: {', '.join(f'{n} ({c})' for n, c in top_tasks[:10])}")


if __name__ == "__main__":
    main()
