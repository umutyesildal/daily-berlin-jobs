# Repository guide

## Local verification

- Python tests: `PYTHONPATH=src python -m unittest discover -s tests -v`
- Web checks, from `web/`: `npm ci`, `npm test`, `npm run typecheck`, and `npm run build`
- Catalog audit: `PYTHONPATH=src python scripts/catalog.py audit catalog/companies.yaml`
- `scripts/smoke_postgres.py` requires PostgreSQL and is run in CI.

## GitHub Actions cost

GitHub Actions runs cost money. Do not dispatch workflows to verify changes; batch changes into one PR, avoid extra pushes, and let the daily schedule pick up merged changes.

## Code locations

- Production scrapers live in `src/daily_jobs/scrapers/done/`.
- ATS discovery code lives in `src/daily_jobs/discovery/`.
- Database migrations live in `db/migrations/`.
- The web agent API lives in `web/app/api/v1/`; the MCP endpoint is `web/app/api/mcp/`.
