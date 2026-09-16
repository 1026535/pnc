"""Canonical typed resource-cost row shared by detail-panel producers.

One ``ResourceCost`` is the numeric record measured beside a resource icon in
an owned detail panel (research node detail, building upgrade/construction
detail). The resource identity stays optional: producers publish the measured
amounts even when the icon cannot be matched to a known resource.
"""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.app.pnc.domain.policy_models import ResourceType
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.vision.image.models import Bounds


@dataclass(frozen=True, slots=True)
class ResourceCost:
    """One resource requirement row measured inside a typed detail panel."""

    resource_type: ResourceType | None
    available: int | None
    required: int | None
    text_bounds: Bounds

    def __post_init__(self) -> None:
        """Keep cost rows numeric and bounded; resource type stays optional."""

        if self.resource_type is not None and not isinstance(self.resource_type, ResourceType):
            raise TypeError("ResourceCost.resource_type must be a ResourceType or None.")
        for field_name in ("available", "required"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise SelectorResolutionError(
                    f"ResourceCost.{field_name} must be a non-negative integer or None.",
                    value=value,
                )
        if not isinstance(self.text_bounds, Bounds):
            raise TypeError("ResourceCost.text_bounds must be Bounds.")
