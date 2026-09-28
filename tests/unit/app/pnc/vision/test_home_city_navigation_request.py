"""Home acquisition requests scene evidence without unrelated HUD OCR."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from pnc_automation.app.automation.engine.core_runtime import CoreRuntime
from pnc_automation.app.automation.engine.core_workflow import WorkflowContext
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.visual_screen_recognizer import VisualRecognition
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrService
from tests.support.pnc.observations import make_observation


class HomeCityNavigationRequestTests(unittest.TestCase):
    def test_scope_requests_camera_and_guards_without_semantic_ocr(self):
        request = ObservationRequest.home_city_navigation()
        self.assertTrue(request.include_home_city_camera)
        self.assertTrue(request.include_popup_guard)
        self.assertTrue(request.include_loading_guard)
        self.assertEqual(frozenset({ScreenType.PNC_HOME_CITY}), request.candidate_screen_types)
        self.assertEqual(frozenset(), request.ocr_screen_types)
        self.assertFalse(ObservationRequest.source_screen_retry(
            ScreenType.PNC_HOME_CITY,
        ).include_home_city_camera)

    def test_narrow_enrichment_uses_canonical_surface_without_ocr(self):
        image = Image.new("RGB", (900, 1600))
        camera = Mock()
        enricher = PncObservationEnricher(home_city_camera=camera)
        context = Mock(spec=ObservationOcrContext)
        surface = object()
        with patch(
            "pnc_automation.app.pnc.vision.pnc_observation_enricher."
            "build_home_city_spatial_surface", return_value=surface,
        ) as build:
            additions = enricher.enrich(
                image, ScreenType.PNC_HOME_CITY, {},
                ObservationRequest.home_city_navigation(),
                ocr_context=context, ocr_regions={},
            )
        self.assertIs(surface, additions.spatial_surface)
        self.assertEqual((), additions.screen_evidence)
        build.assert_called_once_with(
            image=image, lines=(), selector_registry=None, camera=camera,
        )
        self.assertEqual([], context.mock_calls)

    def test_narrow_request_cannot_supply_home_evidence_on_another_screen(self):
        enricher = PncObservationEnricher(home_city_camera=Mock())
        context = Mock(spec=ObservationOcrContext)
        with patch(
            "pnc_automation.app.pnc.vision.pnc_observation_enricher."
            "build_home_city_spatial_surface",
        ) as build:
            for screen in (ScreenType.UNKNOWN, ScreenType.PNC_WORLD_MAP, ScreenType.PNC_POPUP):
                with self.subTest(screen=screen):
                    additions = enricher.enrich(
                        Image.new("RGB", (900, 1600)), screen, {},
                        ObservationRequest.home_city_navigation(),
                        ocr_context=context, ocr_regions={},
                    )
                    self.assertIsNone(additions.spatial_surface)
                    self.assertEqual((), additions.screen_evidence)
        build.assert_not_called()
        self.assertEqual([], context.mock_calls)

    def test_guard_denial_prevents_camera_enrichment(self):
        image = Image.new("RGB", (900, 1600), "white")
        recognizer = Mock()
        recognizer.recognize.return_value = VisualRecognition(evidence=(
            ScreenEvidence(ScreenType.PNC_HOME_CITY, "home_anchor", "home"),
        ))
        backend = Mock(spec=OcrService)
        guard = Mock(spec=PncObservationEnricher)
        guard.detect_interruption.return_value = ObservationAdditions(
            guard_verdict=GuardVerdict.UNRESOLVED,
        )
        perception = NavigationPerception(
            recognizer, guard, ScreenClassifier(),
            lambda capture: ObservationOcrContext(capture.image, backend, None, "test"),
        )
        result = perception.build(
            CapturedScreenshot(None, image, "PNG", ephemeral_captured_at=datetime.now(UTC)),
            include_content=True, request=ObservationRequest.home_city_navigation(),
        )
        self.assertFalse(result.decision.action_eligible)
        self.assertIsNone(result.spatial_surface)
        guard.enrich.assert_not_called()
        guard.detect_interruption.assert_called_once()

    def test_workflow_acquisition_and_discovery_use_narrow_callback(self):
        home = make_observation(ScreenType.PNC_HOME_CITY)
        runtime = SimpleNamespace(
            navigation=Mock(), observe=Mock(return_value=home),
            observation_count=0, last_observation=home,
        )
        context = WorkflowContext(runtime, last_observation=home)
        context.open_building(HomeCityObjectId.INSTITUTE)
        context.discover_home_city()
        for call in (
            runtime.navigation.open_building.call_args,
            runtime.navigation.discover_home_city.call_args,
        ):
            self.assertIs(home, call.kwargs["observe_content"]("proof"))
        self.assertEqual(2, runtime.observe.call_count)
        for call in runtime.observe.call_args_list:
            self.assertTrue(call.kwargs["include_content"])
            self.assertEqual(ObservationRequest.home_city_navigation(), call.kwargs["request"])

    def test_popup_recovery_restores_requested_home_camera_scope(self):
        popup = make_observation(ScreenType.PNC_POPUP)
        recovered = make_observation(ScreenType.PNC_HOME_CITY)
        refreshed = make_observation(ScreenType.PNC_HOME_CITY)
        executor = Mock()
        executor.recover_interruption_if_required.return_value = recovered
        runtime = CoreRuntime(
            runtime=Mock(), navigation=Mock(), artifact_directory="unused",
            trace_path=Path("unused"), _perception=Mock(), _run_id="test",
            _observed_action_executor=executor,
        )
        request = ObservationRequest.home_city_navigation()
        with patch.object(CoreRuntime, "_observe_once", side_effect=[popup, refreshed]) as observe:
            result = runtime.observe("home", include_content=True, request=request)
        self.assertIs(refreshed, result)
        self.assertEqual(2, observe.call_count)
        self.assertEqual(
            {"include_content": True, "request": request}, observe.call_args.kwargs,
        )


if __name__ == "__main__":
    unittest.main()
