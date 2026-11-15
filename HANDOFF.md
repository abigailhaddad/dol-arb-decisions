# Handoff

## What runs
`.github/workflows/refresh.yml`, Mondays 11:20 UTC. Re-reads both ARB lists on dol.gov (about 360 requests, one a second), rebuilds the table, fetches the text of any new decision, merges into the two Hugging Face files by `decision_id`, and uploads only if something changed. No LLM.

## What you need
- A repository secret `HF_TOKEN` with write access to `abigailhaddad/dol-arb-decisions`. Not set yet. Without it the run finishes without uploading and prints a notice.
- The explorer site is a config in `dataset-explorer` (`configs/dol-arb.json`), deployed to the Cloudflare Pages project `dol-arb-decisions` by that repo's workflow. It reads the parquet from Hugging Face when the page loads.

## What breaks
- **DOL changes the page markup.** Parsing returns far fewer rows, the run stops (it refuses a build under 95% of the published row count, or a merge that shrinks the table), and GitHub emails you.
- **The CDN starts refusing the default `requests` User-Agent.** Every fetch 403s and the crawl stops on the first one.
- **A new month page is linked from an HTML comment.** DOL keeps future months commented out in the index. The crawler strips comments, so a month appears only once DOL uncomments it.

## What the data is not
No outcome and no judges. No OCR: scanned PDFs without a text layer have empty text (`text_status = "no text layer"`). Rows where DOL's list attaches a link to the wrong caption keep what the list says; `file_number_in_caption = False` marks the ones where the file's ARB number isn't in the caption.
