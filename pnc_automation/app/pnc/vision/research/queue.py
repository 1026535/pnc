"""Research queue row parsing."""

from __future__ import annotations

from PIL import Image

from pnc_automation.app.pnc.domain.research import ResearchQueueRow
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.app.pnc.vision.research.parsing import _QUEUE_ROW_TITLE_PATTERN, queue_row
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


def queue_additions(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> ObservationAdditions:
    """Parse the accepted research-queue panel into explicit row states."""

    header = next((line for line in lines if normalize_ocr_text(line.text) == "RESEARCHQUEUE"), None)
    rows: list[ResearchQueueRow] = []
    if header is not None:
        body = sorted(
            (line for line in lines if line.bounds.y > header.bounds.y),
            key=lambda line: (line.bounds.y, line.bounds.x),
        )
        title_lines = [
            line for line in body
            if _QUEUE_ROW_TITLE_PATTERN.match(normalize_ocr_text(line.text)) is not None
        ]
        for index, title_line in enumerate(title_lines):
            next_top = title_lines[index + 1].bounds.y if index + 1 < len(title_lines) else image.height
            row_lines = tuple(line for line in body if title_line.bounds.y <= line.bounds.y < next_top)
            rows.append(queue_row(image=image, title_line=title_line, row_lines=row_lines))
    return ObservationAdditions(research_queue_rows=tuple(rows))
