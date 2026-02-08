# CDC Job Listings: Coding Tools & Tasks

**[Live site](https://jobswithcode.netlify.app/)**

An analysis of CDC job postings on USAJOBS (2021-2025), identifying which positions require programming languages, software tools, and coding-related tasks.

## Methodology

### Data source

Job listings come from a [historical archive of USAJOBS postings](https://github.com/abigailhaddad/usajobs_historical). The dataset is filtered to jobs posted by the Centers for Disease Control and Prevention, deduplicated by control number.

### Scraping

Each job's full posting text is scraped from USAJOBS and saved locally. This captures the complete duties, qualifications, and requirements sections that aren't available in the structured metadata alone.

### LLM extraction

Each job posting is sent to OpenAI's `gpt-5-nano` model via the Batch API with a structured output schema. The model extracts two things:

- **Coding tools**: Specific, named programming languages and software tools mentioned in the listing (e.g., Python, R, SAS, SQL, Docker). General office software (Excel, Power BI, SharePoint) and generic categories ("statistical software") are excluded.
- **Coding tasks**: Short phrases quoted directly from the listing that describe coding or programming work. The model is instructed not to paraphrase or summarize -- task text should appear verbatim in the listing.

### Verification

Each extracted tool and task name is checked against the original scraped job text via case-insensitive substring matching. Items that don't appear in the source text are flagged as unverified and shown in red in the web viewer.

### Post-processing

An exclude list in `05_build_web_data.py` removes known false positives:
- **Tools**: HVAC/building control systems (Johnson Controls GX9100, CCT, GPL, LCT), non-coding software (SharePoint, Lectora)
- **Tasks**: Generic single words (analysis, collection, processing), medical "coding" (ICD classification, not programming), HVAC-related tasks (ladder logic, BAS reprogramming)

### Web viewer

The results are compiled into a static JSON file and displayed in a filterable table. Filters are available per column for title, series, year, grade, location, and specific tools/tasks. Separate "Has Tools" and "Has Tasks" columns allow filtering for jobs with coding tools, coding tasks, or both independently.

## Pipeline

The analysis runs as a sequential pipeline:

1. `01_download_and_filter.py` - Downloads yearly USAJOBS parquet files, filters for CDC
2. `02_scrape_job_pages.py` - Scrapes full job text from USAJOBS (resumable)
3. `03_prepare_batch.py` - Builds OpenAI Batch API input from scraped text
4. `04_submit_batch.py` - Submits, polls, and downloads batch results
5. `05_build_web_data.py` - Combines metadata and LLM results into `web/data/cdc_jobs.json`, applies verification and exclude lists

`run_pipeline.sh` runs steps 2-5 end to end. Supports `--limit N` to cap batch size and is resumable (detects in-flight batches).

## Limitations

- LLM extraction is imperfect. Some tools or tasks may be missed or incorrectly identified.
- Unverified items (shown in red) indicate the model may have paraphrased or hallucinated -- the extracted text was not found verbatim in the listing.
- "Has Tools" / "Has Tasks" means the LLM found at least one coding tool or task -- it does not mean coding is a primary duty of the role.
