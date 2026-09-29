"""Tracing context ownership for the bounded target and anchor pools."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from contextvars import ContextVar, copy_context
from dataclasses import replace
from pathlib import Path
import threading
import unittest
from unittest import mock

import numpy as np

from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof,
    HomeCityCameraStatus,
)
from pnc_automation.app.pnc.vision.home_city_camera import localization
from pnc_automation.app.pnc.vision.home_city_camera.catalog import (
    load_home_city_camera_catalog,
)
from pnc_automation.app.pnc.vision.home_city_camera.localization import (
    HomeCityCameraLocalizer,
)
from pnc_automation.core.infra.diagnostics.performance import (
    PerformanceReportWriter,
    current_performance_run,
)
from pnc_automation.core.vision.template.template_matcher import (
    OpenCvTemplateMatcher,
    PreparedFrame,
)


class HomeCameraWorkerContextTests(unittest.TestCase):
    """Each traced task inherits the caller and owns an independent context."""

    def setUp(self) -> None:
        self.matcher = mock.Mock(spec=OpenCvTemplateMatcher)
        catalog = load_home_city_camera_catalog()
        self.catalog = replace(catalog, targets=catalog.targets[:3])
        self.localizer = HomeCityCameraLocalizer(
            matcher=self.matcher, catalog=self.catalog
        )
        self.frame = PreparedFrame(
            pixels=np.zeros((5, 7, 3), dtype=np.uint8),
            original_size=(7, 5),
            reference_size=(7, 5),
        )

    def _check_contexts(
        self,
        task_ids: tuple[object, ...],
        invoke: Callable[[Callable[[object], None]], None],
    ) -> None:
        """Exercise enabled isolation and disabled no-copy behavior without matching."""
        for enabled in (False, True):
            with self.subTest(tracing=enabled):
                marker = ContextVar("home_camera_worker_marker", default="worker")
                token = marker.set("parent")
                run = PerformanceReportWriter(Path("unused-context-report")).begin_run(
                    "fake_camera"
                )
                barrier = threading.Barrier(2)
                rendezvous = set(task_ids[:2])
                seen: list[object] = []

                def recorded(key: object) -> None:
                    self.assertIs(run if enabled else None, current_performance_run())
                    if enabled:
                        self.assertEqual("parent", marker.get())
                        marker.set(str(key))
                        if key in rendezvous:
                            barrier.wait(timeout=2)
                    seen.append(key)

                try:
                    with (
                        run.activate() if enabled else nullcontext(),
                        mock.patch.object(
                            localization, "copy_context", wraps=copy_context
                        ) as copied,
                    ):
                        invoke(recorded)
                    self.assertEqual(len(task_ids) if enabled else 0, copied.call_count)
                    self.assertCountEqual(task_ids, seen)
                    self.assertEqual("parent", marker.get())
                    self.assertIsNone(current_performance_run())
                finally:
                    marker.reset(token)

    def test_target_pool_inherits_tracing_with_one_context_per_task(self) -> None:
        proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="fake worker context",
            translation=(-532, 222),
            zoom=1.0,
            frame_size=(7, 5),
        )

        def invoke(recorded):
            def candidates(_frame, target, *, proof):
                recorded(target.object_id)
                return ()

            with mock.patch.object(
                self.localizer, "match_target_candidates", side_effect=candidates
            ):
                self.assertEqual(
                    (), self.localizer.matched_target_objects(self.frame, proof=proof)
                )

        self._check_contexts(
            tuple(target.object_id for target in self.catalog.targets), invoke
        )

    def test_anchor_pool_inherits_tracing_with_one_context_per_task(self) -> None:
        normalization = self.catalog.normalization
        assert normalization is not None
        spec = replace(normalization.zoom_anchors[0], scales=(0.98, 1.0, 1.02))

        def invoke(recorded):
            def match(*_args, template_scale, **_kwargs):
                recorded(template_scale)
                return None

            self.matcher.find_best_match_coarse_to_fine.side_effect = match
            self.assertIsNone(
                self.localizer._match_anchor_spec(
                    self.frame, self.frame, normalization, spec
                )
            )

        self._check_contexts(spec.scales, invoke)
