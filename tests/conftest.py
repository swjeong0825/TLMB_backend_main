"""Root pytest config: disable rate limiting before ``app`` is imported."""

from __future__ import annotations

import os

os.environ["RATELIMIT_ENABLED"] = "false"
