"""Pure offline Pet Workshop solver: policy, effort and validation.

The package is I/O-free by construction: every module derives facts only
from the typed ``WorkshopState``, the packaged catalog and the policy.
``validate_intent`` is the single canonical legality check shared by
planning and later executor revalidation; ``default_policy`` returns the
solver's policy instance.
"""

from pnc_automation.app.automation.pet_workshop.policy import default_policy
from pnc_automation.app.automation.pet_workshop.validation import validate_intent

__all__ = [
    "default_policy",
    "validate_intent",
]
