# Config Directory

`config/` is the single place for non-sensitive, human-editable settings.

## Change Here Often

- `sources.yaml`
  - enable or disable a source
  - change polling frequency
  - update symbols, topics, limits, regions
  - maintain the `trusted_sources` catalog used as the trusted-source whitelist
- `scoring_rules.yaml`
  - adjust news sorter thresholds
- `routes.yaml`
  - adjust route descriptions or future route metadata

## Change Here Sometimes

- `sources.yaml -> service`
  - default database path
  - default poll interval
  - retry and backoff settings
- `app.yaml`
  - app-level defaults and metadata

## Do Not Put Secrets Here

Keep API keys and secrets in environment variables, for example:

- `FINNHUB_API_KEY`

`.env.example` documents which environment variables are expected.

## Adding a New Source

1. Add a new adapter under `sources/`
2. Register it in `sources/factory.py`
3. Add a new entry to `sources.yaml`
4. Keep source-specific odd fields inside `params`

## Trusted Source Catalog

Use `sources.yaml -> trusted_sources` for trusted sources that should be allowed or referenced by analysis workflows even when they are not directly ingestible yet.

- `primary`: official data, official databases, central banks, regulators, and original policy releases
- `secondary`: wire services, financial media, and transparent research datasets

Adding a source to `trusted_sources` does not enable polling. Polling still requires a supported entry under `sources`.

## Compatibility Notes

- The canonical ingest config path is `config/sources.yaml`
- The legacy path `configs/feeds.yaml` is still accepted by the loader as a compatibility alias when the new file exists
