# API Competitor Research

Competitor research dashboard covering 1 June 2026 onward. Full domains appear in the dashboard, filters and CSV exports. The API favicon is embedded in index.html.

## Daily cloud refresh

.github/workflows/refresh.yml runs scripts/refresh.py every day at 20:00 UTC (04:00 Asia/Manila the following day), independently of the laptop. GitHub Actions commits refreshed index.html and research-data.json to main; Vercel deploys the commit. The workflow also supports manual runs from the Actions tab. GitHub scheduled runs may start later during queue congestion.

The collector checks publisher archives, article dates, SQM newsletters and release PDFs, and public news-index discoveries. Existing records are preserved on failed requests. The dashboard shows the latest attempt and source availability; an accessible archive with no new posts is distinct from a source failure. Domain.com.au returned HTTP 403 during the initial cloud test; its backfilled research remains available. Public news-index discoveries require review and are excluded from the verified dated timeline. No authenticated social API is connected.

## Data and coverage

Month filters, pagination and CSV export cover all matching rows. Metadata-only entries are not full-article analyses. Full article bodies are not stored. Public-source coverage is bounded, not a complete measure of publishing activity, social reach or share of voice. Undated posts and conflicting PDF dates remain outside the verified timeline. Rolling source URLs count once. research-data.json contains the records, coverage counts, crawl history and lastRefresh source statuses.

Deploy as a static Vercel project using Other with no build command. No paid API keys are required.
