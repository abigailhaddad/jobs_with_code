# CDC Job Listings: Coding Tools & Tasks

An analysis of CDC job postings on USAJOBS (2021-2025), identifying which positions require programming languages, software tools, and coding-related tasks.

## Methodology

### Data source

Job listings come from a [historical archive of USAJOBS postings](https://github.com/abigailhaddad/usajobs_historical). The dataset is filtered to jobs posted by the Centers for Disease Control and Prevention, deduplicated by control number.

### Scraping

Each job's full posting text is scraped from USAJOBS and saved locally. This captures the complete duties, qualifications, and requirements sections that aren't available in the structured metadata alone.

### LLM extraction

Each job posting is sent to OpenAI's `gpt-5-nano` model via the Batch API with a structured output schema. The model extracts two things:

- **Coding tools**: Programming languages and software that involve coding (e.g., Python, R, SAS, SQL, Docker). General office software like Excel and Tableau are excluded unless scripting/VBA is specified.
- **Coding tasks**: Activities that indicate hands-on coding or technical work (e.g., data analysis, machine learning, software development, ETL). General management and communication tasks are excluded.

Tool and task names are normalized by the model (e.g., "python3" becomes "Python", "Cleans and prepares datasets" becomes "data cleaning").

### Web viewer

The results are compiled into a static JSON file and displayed in a filterable table. Filters are available per column for title, series, year, grade, location, and specific tools/tasks.

## Pipeline

The analysis runs as a sequential pipeline:

1. `01_download_and_filter.py` - Downloads yearly USAJOBS parquet files, filters for CDC
2. `02_scrape_job_pages.py` - Scrapes full job text from USAJOBS (resumable)
3. `03_prepare_batch.py` - Builds OpenAI Batch API input from scraped text
4. `04_submit_batch.py` - Submits, polls, and downloads batch results
5. `05_build_web_data.py` - Combines metadata and LLM results into `web/data/cdc_jobs.json`

`run_pipeline.sh` runs steps 2-5 end to end.

## Limitations

- LLM extraction is imperfect. Some tools or tasks may be missed or incorrectly identified.
- The "Has Coding" flag means the LLM found at least one coding tool or task -- it does not mean coding is a primary duty of the role.
