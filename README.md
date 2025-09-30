# Notion Upserter for RBA AUD Rates

Consumes `rates-latest.json` from the companion repo (**[rba-aud-rates](https://github.com/taylorsudo/rba-aud-rates)**) and upserts rows into a Notion database.  
**Default:** only USD→AUD is written, with Name = `YYYY-MM-DD USD→AUD`.  

## Trigger
- Listens for `repository_dispatch` (`event_type: rates_updated`) from [rba-aud-rates](https://github.com/taylorsudo/rba-aud-rates).
- Also supports manual `workflow_dispatch`.

## Notion schema (property names)
- **Name** (Title) – e.g., `2025-09-29 USD→AUD`
- **Date** (Date)
- **Currency** (Select) – `USD` by default
- **AUD per Unit** (Number) – AUD per 1 USD
- **Per AUD** (Number) – USD per 1 AUD (direct from RBA)

## Configuration
Set in **Settings → Secrets and variables → Actions**:

**Secrets**
- `NOTION_API_TOKEN`
- `NOTION_DATABASE_ID`

**Variables (optional)**
- `RATES_JSON_URL` – default fallback; normally provided by [rba-aud-rates](https://github.com/taylorsudo/rba-aud-rates) payload.

**Env in workflow**
- `CURRENCY_FILTER` (default `USD`).  
  Change to `USD,EUR,JPY` to include more later.

## Local test
```bash
export NOTION_API_TOKEN=***
export NOTION_DATABASE_ID=***
export RATES_JSON_URL=https://<owner>.github.io/rba-aud-rates/rates-latest.json
export CURRENCY_FILTER=USD
python3 scripts/push_to_notion.py
```
