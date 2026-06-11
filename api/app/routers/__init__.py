"""API route modules (brief 07, Q3).

``app.main`` was a ~1,100-line module holding every route, schema, and helper.
Routes are split here by concern:

- :mod:`app.routers.health` — ``/health``
- :mod:`app.routers.feed` — ``/feed`` and ``/cluster/{id}``
- :mod:`app.routers.submit` — ``/submit/link``
- :mod:`app.routers.metrics` — ``/stats`` and the public counter endpoints
- :mod:`app.routers.admin` — every ``/admin/*`` route (auth enforced on the router)
"""
