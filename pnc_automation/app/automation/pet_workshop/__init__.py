"""Pure offline Pet Workshop solver: policy, effort, validation, planning.

The package is I/O-free by construction: every module derives facts only
from the typed ``WorkshopState``, the packaged catalog and the policy.
``plan_next`` is the one-step planner; ``validate_intent`` is the single
canonical legality check shared by planning and later executor
revalidation; ``default_policy`` returns the solver's policy instance.
"""

from pnc_automation.app.automation.pet_workshop.planner import plan_next
from pnc_automation.app.automation.pet_workshop.policy import default_policy
from pnc_automation.app.automation.pet_workshop.validation import validate_intent

__all__ = [
    "default_policy",
    "plan_next",
    "validate_intent",
]
