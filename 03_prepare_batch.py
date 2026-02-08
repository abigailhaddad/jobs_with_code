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

1. **coding_tools**: Specific, named programming languages and software tools that involve writing code.
2. **coding_tasks**: Activities described in the listing that specifically require writing or maintaining code.

THE KEY QUESTION: Does this job require someone to actually write code? We are trying to distinguish roles that involve hands-on programming from roles that merely use data or technology.

---

CODING TOOLS — MUST be a specific named product or language. INCLUDE:
- Programming languages: Python, R, JavaScript, Java, C++, SQL, SAS, Stata, MATLAB, Go, Rust, Shell/Bash, etc.
- Statistical/analytical software that involves writing code: SAS, Stata, SPSS (syntax), R, etc.
- DevOps/infrastructure: Docker, Kubernetes, Terraform, Ansible, Jenkins, Git, AWS CLI, etc.
- Frameworks/libraries: React, Django, Flask, TensorFlow, PyTorch, Pandas, NumPy, Spring, .NET, etc.
- Databases (only if specifically named): SQL Server, PostgreSQL, MySQL, MongoDB, Oracle, DynamoDB, etc.
- Other coding tools: Jupyter, VS Code, RStudio, GitHub, GitLab, etc.
- Markup/config that's code-adjacent: HTML, CSS, XML, YAML, JSON

CODING TOOLS — DO NOT INCLUDE:
- Generic categories: "statistical software", "database", "spreadsheets", "relational databases", "data visualization", "programming languages", "coding tools". Only include specific named tools.
- Microsoft Excel — NEVER include Excel, even "advanced Excel", unless VBA/macros are explicitly specified
- Microsoft Office (Word, PowerPoint, Outlook)
- Power BI — NEVER include Power BI, it is a drag-and-drop BI tool, not a coding tool
- Tableau, Alteryx, and other BI/visualization tools used without code
- Google Workspace (Docs, Sheets, Slides)
- Adobe Acrobat, SharePoint, Teams, Zoom, Slack
- General project management tools (MS Project, Smartsheet) unless API/scripting mentioned

---

CODING TASKS — INCLUDE only activities that require actually writing or maintaining code:
- Data engineering: ETL, data pipeline development, database administration, data wrangling with code
- Statistics/modeling with code: statistical modeling, machine learning, predictive modeling, NLP, epidemiological modeling, biostatistics (only when the listing implies coding, not just interpreting results)
- Software: software development, web development, API development, scripting, automation, code review, testing
- DevOps/infra: system administration, cloud infrastructure, CI/CD, network engineering
- Security: vulnerability assessment, penetration testing, security monitoring
- Other technical: bioinformatics, geospatial analysis (with code), genomic sequencing analysis, scientific computing

CODING TASKS — DO NOT INCLUDE. These are common in CDC listings but do NOT imply coding:
- General data work that doesn't require code: data collection, data interpretation, data synthesis, data compilation, data presentation, data quality assessment, data management (unless it specifies using code/databases)
- Analysis that doesn't require code: program evaluation, policy analysis, budget analysis, cost-benefit analysis, qualitative analysis, epidemiologic study design, literature review, outbreak investigations, surveillance (unless it specifies statistical software or programming)
- General management/admin: project management, budget management, policy development, report writing
- Communication: presenting findings, writing reports, stakeholder engagement

---

Return empty lists if nothing matches — most CDC jobs do NOT involve coding and should have empty lists.

Normalize names to lowercase with spaces (e.g. 'data analysis' not 'Data analysis' or 'data_analysis'). Tool names should be properly capitalized (e.g. 'Python' not 'python', 'SQL Server' not 'sql server')."""


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
