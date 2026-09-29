"""Research producer facade over tree, detail and queue owners."""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.research import ResearchDetail, ResearchNodeFacts, ResearchNodeId, ResearchQueueRow, ResearchQueueState, research_category_for_layout
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.app.pnc.vision.research.detail import detail_additions as build_detail_additions
from pnc_automation.app.pnc.vision.research.queue import queue_additions as build_queue_additions
from pnc_automation.app.pnc.vision.research.tree import NodeCandidate, build_tree_additions, node_candidate, read_node_level
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

_RESEARCH_DETAIL_LAYOUT_ID = "research_tree_node_detail"
_RESEARCH_MAX_DETAIL_LAYOUT_ID = "research_tree_node_detail_max"


@dataclass(frozen=True, slots=True)
class ResearchContentProducer:
    """Produce typed research rows, detail facts and queue facts under proof."""

    matcher: OpenCvTemplateMatcher = field(default_factory=OpenCvTemplateMatcher)

    def additions_for_tree(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
        ocr_context: ObservationOcrContext,
        layout_id: str | None,
    ) -> ObservationAdditions:
        """Dispatch accepted tree, detail and queue layouts to their owners."""

        if layout_id in {_RESEARCH_DETAIL_LAYOUT_ID, _RESEARCH_MAX_DETAIL_LAYOUT_ID}:
            return self.detail_additions(
                image=image,
                lines=lines,
                ocr_context=ocr_context,
                max_level_panel=layout_id == _RESEARCH_MAX_DETAIL_LAYOUT_ID,
            )
        category = research_category_for_layout(layout_id)
        if category is not None:
            return self.tree_additions(image=image, lines=lines, ocr_context=ocr_context, category=category)
        return ObservationAdditions()

    def tree_additions(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
        ocr_context: ObservationOcrContext,
        category: ResearchCategory | None = None,
    ) -> ObservationAdditions:
        """Publish measured tree rows under the independently proved category."""

        return build_tree_additions(
            image=image,
            lines=lines,
            ocr_context=ocr_context,
            category=category,
            matcher=self.matcher,
        )

    def detail_additions(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
        ocr_context: ObservationOcrContext,
        max_level_panel: bool = False,
    ) -> ObservationAdditions:
        """Publish read-only detail facts and measured controls."""

        return build_detail_additions(
            image=image,
            lines=lines,
            ocr_context=ocr_context,
            max_level_panel=max_level_panel,
            matcher=self.matcher,
        )

    def queue_additions(self, *, image: Image.Image, lines: tuple[OcrLine, ...]) -> ObservationAdditions:
        """Publish explicit idle/active/unknown queue rows."""

        return build_queue_additions(image=image, lines=lines)

    def _node_candidate(
        self,
        *,
        image: Image.Image,
        component: Bounds,
        ocr_context: ObservationOcrContext,
        category: ResearchCategory | None,
    ) -> NodeCandidate | None:
        """Retain the tested private candidate seam on the producer facade."""

        return node_candidate(image=image, component=component, ocr_context=ocr_context, category=category)

    def _read_node_level(
        self,
        *,
        image: Image.Image,
        icon_bounds: Bounds,
        ocr_context: ObservationOcrContext,
    ) -> tuple[int | None, int | None, bool] | None:
        """Retain the tested private level-reading seam on the facade."""

        return read_node_level(image=image, icon_bounds=icon_bounds, ocr_context=ocr_context)


__all__ = [
    "ResearchContentProducer",
    "ResearchDetail",
    "ResearchNodeFacts",
    "ResearchNodeId",
    "ResearchQueueRow",
    "ResearchQueueState",
]
