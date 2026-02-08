# CDC Job Listings Project

One-shot analysis of CDC USAJOBS postings (2021-2025) to extract coding tools and tasks via LLM. Not an ongoing repo.

## Structure

- `01_download_and_filter.py` through `05_build_web_data.py` — sequential pipeline steps
- `run_pipeline.sh` — runs steps 2-5 end to end, supports `--limit N` and resume
- `web/index.html` — static single-page viewer (DataTables, Bootstrap 5, vanilla JS)
- `web/data/cdc_jobs.json` — generated data file consumed by the viewer, committed for Netlify
- `data/` — local data directory (parquet, scraped text files, batch results). Gitignored.

## Key details

- Python 3.14, venv at `.venv/`
- OpenAI API key in `.env` as `OPENAI_API_TOKEN`
- LLM model: `gpt-5-nano-2025-08-07` via OpenAI Batch API
- Structured output schema defined in `03_prepare_batch.py` (RESPONSE_SCHEMA)
- Prompt instructs model to extract direct quotes, not paraphrases
- Web viewer is fully static — no build step, just serve `web/`
- Netlify config in `web/netlify.toml`, publish directory is `web/`
- Column filters use DataTables column search API, `dom: 'lrtip'` omits global search
- Separate "Has Tools" and "Has Tasks" columns with independent Yes/No filters

## Verification and post-processing (05_build_web_data.py)

- Each tool/task is checked against the scraped job text (case-insensitive, whitespace-normalized, quotes stripped)
- Unverified items get `"verified": false` and render in red (`tag-unverified` CSS class)
- `EXCLUDED_TOOLS` set: SharePoint, Lectora, HVAC controls (Johnson Controls GX9100, CCT, GPL, LCT)
- `EXCLUDED_TASKS` set: generic single words (analysis, collection, processing, mining, linkage), medical "coding", HVAC tasks (ladder logic, BAS reprogramming), non-coding evaluations
- Tools/tasks output as `{"name": "...", "verified": true/false}` objects in the JSON

## Column index reference (web/index.html)

0=Title, 1=Series, 2=Year, 3=Grade, 4=Location, 5=Has Tools, 6=Has Tasks, 7=Coding Tools, 8=Coding Tasks, 9=Link (not searchable)

## Future: LLM refinement pass (not yet built)

Potential `06_refine.py` step using a better model to curate the nano results:
1. Collect all unique tool names and task names across all results into two deduplicated lists
2. Single API call to a better model: "which of these are legitimate coding tools / coding tasks?" — get back filtered subsets
3. Filter each job's results to only include approved tools/tasks
4. Local validation: substring match each tool/task against the scraped text, with special handling for ambiguous short names (R, C, Go) that need word-boundary or contextual matching
5. Overwrite per-job result files with cleaned versions
