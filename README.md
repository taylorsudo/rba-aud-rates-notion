# Notion Upserter — RBA AUD Rates (Latest Only)

Maintains **one row per currency** in a Notion database. Each currency’s page is updated daily from the RBA 4pm AEST feed produced by [rba-aud-rates](https://github.com/taylorsudo/rba-aud-rates/).

## Notion database

Create **Rates (Latest)** with these properties:

- **Name** — Title
- **Currency** — Select
- **AUD per Unit** — Number
- **Per AUD** — Number
- **Updated** — Date

Upsert key = **Currency**. One row per currency (e.g., USD, EUR, JPY …).

## Trigger

This repo listens for:

```yaml
on:
  repository_dispatch:
    types: [rates_updated]
```