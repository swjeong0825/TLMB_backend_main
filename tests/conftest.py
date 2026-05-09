"""Root pytest config: disable rate limiting before ``app`` is imported.

Setting ``RATELIMIT_ENABLED=false`` in the env is *not* sufficient on its own:
slowapi's ``Limiter.__init__`` re-reads the same env var via Starlette's
``Config(".env")`` and assigns the raw string back onto ``self.enabled``. The
string ``"false"`` is truthy, so the rate limiter would still fire. We force
``limiter.enabled = False`` post-construction to make the disable actually
take effect.
"""

from __future__ import annotations

import os

os.environ["RATELIMIT_ENABLED"] = "false"


def pytest_configure(config) -> None:  # noqa: ARG001 (pytest hook)
    """Force-disable the rate limiter once the app module has loaded.

    Imported lazily so ``app.rate_limit`` constructs its limiter against the
    env var first; we then overwrite the (incorrectly-typed) string back to
    a real ``False`` bool.
    """
    from app.rate_limit import limiter

    limiter.enabled = False
