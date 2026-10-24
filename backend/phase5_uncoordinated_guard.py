"""Safety lock for legacy scripts that change what the live service serves directly.

Normal publication goes through ``phase5_publish_release.py`` /
``phase5_coordinated_publication.py``, which journal every step and can roll back.
The scripts that call this guard skip that protection, so they refuse to run unless
the operator deliberately sets ``ARK_ALLOW_UNCOORDINATED_PUBLICATION=yes``.
"""

from __future__ import annotations

import os

ACK_VARIABLE = "ARK_ALLOW_UNCOORDINATED_PUBLICATION"


def require_uncoordinated_ack(script_name: str) -> None:
    """Exit with an explanation unless the operator explicitly acknowledged the risk."""
    if os.environ.get(ACK_VARIABLE, "").strip().lower() == "yes":
        return
    raise SystemExit(
        f"{script_name} changes the live serving state directly and bypasses the journaled, "
        "rollback-capable publication workflow (phase5_publish_release.py). Refusing to run. "
        f"If you really intend this, set {ACK_VARIABLE}=yes for this one command."
    )
