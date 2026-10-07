# VSA AI Commerce Layer

> Work in progress. The full write-up (architecture, before/after, decisions, production notes) lands with the final submission.

An external layer that makes an existing business understandable **and purchasable** by AI assistants, from a natural-language request to a checkout link. The first business on it is the Victory Skating / VSA 6-Month Double Axel Club, read from its Tilda landing page.

## Run the checks

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest
uv run ruff check . && uv run mypy
```

## Layout

```
src/vsa_commerce/
  domain/        business-agnostic schema and rules: sessions, availability, owner rules
  catalog/       per-business catalog snapshots
  connectors/    one class per source platform (Tilda today)
  extraction/    LLM extraction for unstructured sources, with grounding checks
  sync/          refresh a snapshot from its source, with a field-level diff
data/<business>/ catalog snapshot, owner rules, source config
tests/           mirrors src/; fixtures include saved source pages and non-skating catalogs
```
