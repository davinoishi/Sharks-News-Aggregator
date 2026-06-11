"""Enrichment building blocks (brief 07, Q4).

``api/app/tasks/enrich.py`` was a ~1,240-line module mixing entity extraction,
relevance/event classification, the clustering algorithm, and the NHL opponent
team table. It is split here into focused modules:

- :mod:`app.enrichment.teams` — NHL opponent table + game-id extraction
- :mod:`app.enrichment.entities` — entity extraction and team filtering
- :mod:`app.enrichment.classify` — keyword + LLM relevance/event/tag classification
- :mod:`app.enrichment.clustering` — tokenization, similarity scoring, match-or-create

The Celery task in ``app.tasks.enrich`` stays a thin orchestrator and re-exports
these helpers so existing imports (and queued task messages) keep working.
"""
