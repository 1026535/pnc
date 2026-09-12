"""Generic template matching services."""

from pnc_automation.core.vision.template.template_matcher import (
    DecodedTemplateCache,
    OpenCvTemplateMatcher,
    PreparedFrame,
)

__all__ = ["DecodedTemplateCache", "OpenCvTemplateMatcher", "PreparedFrame"]

