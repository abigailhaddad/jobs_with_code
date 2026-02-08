"""
Step 3: Prepare an OpenAI Batch API input file (.jsonl) from scraped job text files.
Each job becomes one request asking gpt-5-nano to extract coding tools/languages.

Checks which jobs already have results and only includes new ones.

Usage:
    python 03_prepare_batch.py                # prepare batch for all unprocessed jobs
    python 03_prepare_batch.py --limit 5      # only include 5 jobs (for testing)
    python 03_prepare_batch.py --status        # show what's done vs remaining
"""

import argparse
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
SCRAPED_DIR = DATA_DIR / "scraped_jobs"
RESULTS_DIR = DATA_DIR / "batch_results"
BATCH_INPUT = DATA_DIR / "batch_input.jsonl"

MODEL = "gpt-5-nano-2025-08-07"

# Pydantic schema for structured output (OpenAI JSON Schema format)
RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "coding_extraction",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "coding_tools": {
                    "type": "array",
                    "description": "Programming languages and software tools that involve coding mentioned in the job listing.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "The name of the tool or language, normalized (e.g. 'Python' not 'python/Python3')"
                            },
                            "category": {
                                "type": "string",
                                "enum": [
                                    "programming_language",
                                    "statistical_software",
                                    "data_tool",
                                    "devops_tool",
                                    "framework_library",
                                    "database",
                                    "other_coding_tool"
                                ],
                                "description": "Category of the tool"
                            }
                        },
                        "required": ["name", "category"],
                        "additionalProperties": False
                    }
                },
                "coding_tasks": {
                    "type": "array",
                    "description": "Activities or tasks mentioned in the listing that indicate coding or technical/analytical work.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "task": {
                                "type": "string",
                                "description": "Short normalized label for the task, e.g. 'data cleaning', 'machine learning'"
                            },
                            "category": {
                                "type": "string",
                                "enum": [
                                    "data_analysis",
                                    "data_engineering",
                                    "software_development",
                                    "devops_sysadmin",
                                    "modeling_statistics",
                                    "cybersecurity",
                                    "other_technical"
                                ],
                                "description": "Category of the task"
                            }
                        },
                        "required": ["task", "category"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["coding_tools", "coding_tasks"],
            "additionalProperties": False
        }
    }
}

SYSTEM_PROMPT = """You extract two things from federal job listings:

1. **coding_tools**: Specific, named programming languages and software tools mentioned BY NAME in the text.
2. **coding_tasks**: Short phrases QUOTED DIRECTLY from the listing that describe coding or programming work.

CRITICAL RULES:
- Only extract things that ACTUALLY APPEAR in the text. Every tool name must be a direct match to text in the listing. Every task must be a short phrase taken directly from the listing, not your paraphrase or summary.
- Do NOT infer, paraphrase, or generalize. If the listing says "develops and maintains web applications using ASP.NET", the tool is "ASP.NET" and the task is "develops and maintains web applications" — do NOT output "software development" or "web development" as tasks unless those exact words appear.
- Do NOT output category names as values (e.g. never output "software_development", "data_engineering", "modeling statistics", "devops sysadmin").

---

CODING TOOLS — MUST be a specific named product or language that appears in the text. INCLUDE:
- Programming languages: Python, R, JavaScript, Java, C++, SQL, SAS, Stata, MATLAB, Go, Rust, Shell/Bash, etc.
- Statistical software: SAS, Stata, SPSS, SUDAAN, R, etc.
- DevOps tools: Docker, Kubernetes, Terraform, Ansible, Jenkins, Git, etc.
- Frameworks/libraries: React, Django, Flask, TensorFlow, PyTorch, Pandas, NumPy, Spring, .NET, ASP.NET, etc.
- Databases (only if specifically named): SQL Server, PostgreSQL, MySQL, MongoDB, Oracle, DynamoDB, etc.
- Development tools: Jupyter, VS Code, RStudio, GitHub, GitLab, etc.

CODING TOOLS — DO NOT INCLUDE:
- Microsoft Excel, Power BI, Tableau, Alteryx — NEVER include these
- SharePoint — NEVER include SharePoint, it is not a coding tool
- Microsoft Office (Word, PowerPoint, Outlook)
- Google Workspace (Docs, Sheets, Slides)
- Adobe Acrobat, Teams, Zoom, Slack
- Generic cloud platform names UNLESS the listing actually names them as a tool used in the role
- Hardware, building control systems, or non-software tools (e.g. "Johnson Controls", HVAC systems)
- Generic categories: "statistical software", "database", "spreadsheets", "programming languages", "coding tools"
- Project management tools (MS Project, Smartsheet) unless API/scripting mentioned

---

CODING TASKS — Short phrases taken DIRECTLY from the listing text. Include phrases that describe:
- Writing, developing, or maintaining software or code
- Programming, scripting, or automation
- Database development or query writing
- Statistical programming or computational modeling
- Building data pipelines, ETL processes
- Machine learning, NLP, or AI development

CODING TASKS — DO NOT INCLUDE:
- Your own paraphrases or summaries. The task text must appear in the listing.
- Generic descriptions you inferred: "data engineering", "data pipeline development", "machine learning model development", "data wrangling with code", "data analysis with code"
- Non-coding work: data collection, data interpretation, program evaluation, policy analysis, budget analysis, report writing, surveillance, literature review

---

Return empty lists if nothing matches — most CDC jobs do NOT involve coding and should have empty lists.

Tool names should match the capitalization used in the listing (e.g. 'Python', 'SQL Server', 'SAS'). Task phrases should be quoted exactly as they appear in the listing."""


def get_scraped_jobs() -> list[Path]:
    """Get all scraped job text files."""
    if not SCRAPED_DIR.exists():
        return []
    return sorted(SCRAPED_DIR.glob("*.txt"))


def get_already_processed() -> set[str]:
    """Get control numbers that already have results."""
    if not RESULTS_DIR.exists():
        return set()
    return {p.stem for p in RESULTS_DIR.glob("*.json")}


def build_request(control_number: str, job_text: str) -> dict:
    """Build a single batch API request line."""
    # Truncate very long job texts to stay within token limits
    max_chars = 12000
    if len(job_text) > max_chars:
        job_text = job_text[:max_chars] + "\n\n[truncated]"

    return {
        "custom_id": control_number,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract coding tools and coding tasks from this job listing:\n\n{job_text}"}
            ],
            "response_format": RESPONSE_SCHEMA
        }
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Max jobs to include in batch (for testing)")
    parser.add_argument("--status", action="store_true",
                        help="Just show status")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    scraped = get_scraped_jobs()
    processed = get_already_processed()
    remaining = [p for p in scraped if p.stem not in processed]

    print(f"Scraped job files: {len(scraped):,}")
    print(f"Already processed: {len(processed):,}")
    print(f"Remaining: {len(remaining):,}")

    if args.status:
        return

    if not remaining:
        print("All scraped jobs already have results!")
        return

    to_process = remaining[:args.limit] if args.limit else remaining
    print(f"\nBuilding batch input for {len(to_process):,} jobs...")

    with open(BATCH_INPUT, "w") as f:
        for job_file in to_process:
            cn = job_file.stem
            text = job_file.read_text(encoding="utf-8")
            request = build_request(cn, text)
            f.write(json.dumps(request) + "\n")

    size_mb = BATCH_INPUT.stat().st_size / (1024 * 1024)
    print(f"Wrote {BATCH_INPUT} ({len(to_process):,} requests, {size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
