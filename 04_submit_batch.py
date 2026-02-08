"""
Step 4: Submit the batch input file to OpenAI Batch API, or check status / download results.

Usage:
    python 04_submit_batch.py submit           # upload file and create batch
    python 04_submit_batch.py status           # check batch status
    python 04_submit_batch.py download         # download results and save per-job JSONs
"""

import argparse
import json
import os
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).parent / "data"
BATCH_INPUT = DATA_DIR / "batch_input.jsonl"
BATCH_STATE = DATA_DIR / "batch_state.json"
RESULTS_DIR = DATA_DIR / "batch_results"


def get_client() -> OpenAI:
    return OpenAI(api_key=os.getenv("OPENAI_API_TOKEN"))


def load_state() -> dict:
    if BATCH_STATE.exists():
        return json.loads(BATCH_STATE.read_text())
    return {}


def save_state(state: dict):
    BATCH_STATE.write_text(json.dumps(state, indent=2))


ACTIVE_STATUSES = {"validating", "in_progress", "finalizing"}


def read_input_ids() -> set[str]:
    """Read custom_ids from the current batch input file."""
    if not BATCH_INPUT.exists():
        return set()
    ids = set()
    with open(BATCH_INPUT) as f:
        for line in f:
            ids.add(json.loads(line)["custom_id"])
    return ids


def cmd_submit():
    client = get_client()

    if not BATCH_INPUT.exists():
        print(f"No batch input file found at {BATCH_INPUT}")
        print("Run 03_prepare_batch.py first.")
        return

    input_ids = read_input_ids()
    if not input_ids:
        print("Batch input file is empty, nothing to submit.")
        return

    # Check for an existing batch before creating a new one
    state = load_state()
    if "batch_id" in state:
        try:
            existing = client.batches.retrieve(state["batch_id"])
            saved_ids = set(state.get("custom_ids", []))

            if existing.status in ACTIVE_STATUSES:
                overlap = input_ids & saved_ids
                if overlap:
                    print(f"Batch {existing.id} is already {existing.status} with {len(overlap)} of these jobs — skipping submit.")
                    print(f"Requests: {existing.request_counts.completed}/{existing.request_counts.total} completed")
                    return
                else:
                    print(f"Batch {existing.id} is {existing.status} but for different jobs. Waiting for it to finish first.")
                    print("Run 'python 04_submit_batch.py status' to check, then download and re-run.")
                    return

            if existing.status == "completed" and saved_ids & input_ids:
                # Previous batch has results for some of these jobs — download first
                print(f"Previous batch {existing.id} completed with overlapping jobs. Downloading results first...")
                cmd_download()
                # Re-check: are there still jobs to process?
                already_done = {p.stem for p in RESULTS_DIR.glob("*.json")} if RESULTS_DIR.exists() else set()
                remaining = input_ids - already_done
                if not remaining:
                    print("All jobs from input already have results. Nothing to submit.")
                    return
                print(f"{len(remaining)} jobs still need processing after download.")

            else:
                print(f"Previous batch {existing.id} status: '{existing.status}'. Submitting new batch.")
        except Exception:
            pass  # stale state file, proceed with new submit

    # Count requests
    with open(BATCH_INPUT) as f:
        num_requests = sum(1 for _ in f)
    print(f"Uploading {BATCH_INPUT} ({num_requests:,} requests)...")

    # Upload file
    with open(BATCH_INPUT, "rb") as f:
        file_obj = client.files.create(file=f, purpose="batch")
    print(f"Uploaded file: {file_obj.id}")

    # Create batch
    batch = client.batches.create(
        input_file_id=file_obj.id,
        endpoint="/v1/chat/completions",
        completion_window="24h"
    )
    print(f"Batch created: {batch.id}")
    print(f"Status: {batch.status}")

    save_state({
        "batch_id": batch.id,
        "input_file_id": file_obj.id,
        "num_requests": num_requests,
        "custom_ids": sorted(input_ids),
    })
    print(f"\nSaved batch state to {BATCH_STATE}")
    print("Run 'python 04_submit_batch.py status' to check progress.")


def cmd_status():
    state = load_state()
    if "batch_id" not in state:
        print("No batch submitted yet. Run 'python 04_submit_batch.py submit' first.")
        return

    client = get_client()
    batch = client.batches.retrieve(state["batch_id"])

    print(f"Batch ID: {batch.id}")
    print(f"Status: {batch.status}")
    print(f"Requests: {batch.request_counts.completed}/{batch.request_counts.total} completed, {batch.request_counts.failed} failed")

    if batch.output_file_id:
        print(f"Output file: {batch.output_file_id}")
    if batch.error_file_id:
        print(f"Error file: {batch.error_file_id}")

    if batch.status == "completed":
        print("\nBatch is done! Run 'python 04_submit_batch.py download' to get results.")


def cmd_download():
    state = load_state()
    if "batch_id" not in state:
        print("No batch submitted yet.")
        return

    client = get_client()
    batch = client.batches.retrieve(state["batch_id"])

    if batch.status != "completed":
        print(f"Batch status is '{batch.status}', not 'completed' yet.")
        return

    if not batch.output_file_id:
        print("No output file available.")
        return

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Download output
    print(f"Downloading results from {batch.output_file_id}...")
    content = client.files.content(batch.output_file_id)
    raw_output = DATA_DIR / "batch_output_raw.jsonl"
    raw_output.write_text(content.text)
    print(f"Saved raw output to {raw_output}")

    # Parse and save individual results
    saved = 0
    errors = 0
    for line in content.text.strip().split("\n"):
        result = json.loads(line)
        custom_id = result["custom_id"]
        response = result.get("response")

        if response and response.get("status_code") == 200:
            body = response["body"]
            # Extract the parsed content
            message = body["choices"][0]["message"]
            try:
                parsed = json.loads(message["content"])
            except (json.JSONDecodeError, KeyError):
                parsed = {"raw_content": message.get("content", "")}

            out_file = RESULTS_DIR / f"{custom_id}.json"
            out_file.write_text(json.dumps(parsed, indent=2))
            saved += 1
        else:
            error_info = result.get("error", {})
            print(f"  Failed: {custom_id} - {error_info}")
            errors += 1

    print(f"\nSaved {saved:,} results to {RESULTS_DIR}/")
    if errors:
        print(f"Errors: {errors:,}")

    # Download error file if present
    if batch.error_file_id:
        error_content = client.files.content(batch.error_file_id)
        error_file = DATA_DIR / "batch_errors.jsonl"
        error_file.write_text(error_content.text)
        print(f"Error details saved to {error_file}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["submit", "status", "download"],
                        help="Action to perform")
    args = parser.parse_args()

    if args.command == "submit":
        cmd_submit()
    elif args.command == "status":
        cmd_status()
    elif args.command == "download":
        cmd_download()


if __name__ == "__main__":
    main()
