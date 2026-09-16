"""Phase-owned result acknowledgments preserve facts without replaying recruits."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.engine.core_hero_hall_session import CoreHeroHallSession
from pnc_automation.app.automation.engine.core_workflow import WorkflowContext, WorkflowEffect
from pnc_automation.app.automation.engine.navigation_core import NavigationCore, NavigationPolicy
from pnc_automation.app.pnc.domain.hero_recruit_result import HeroRecruitResult, HeroRecruitResultPhase
from pnc_automation.app.pnc.domain.observation import Observation, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from tests.support.pnc.observations import make_observation


def _result(phase: HeroRecruitResultPhase) -> Observation:
    """Bind synthetic content and measured controls to one fresh result frame."""

    presentation = phase == HeroRecruitResultPhase.HERO_PRESENTATION
    layout = "hero_recruit_presentation" if presentation else "hero_recruit_fragments"
    selector = UiElementId.PNC_HERO_RESULT_CONFIRM if presentation else UiElementId.PNC_HERO_RESULT_CLOSE
    frame = make_observation(
        ScreenType.PNC_HERO_RECRUIT_RESULT, visible_ids=(selector,), artifact_path=Path(layout + ".png"),
    )
    return replace(
        frame, decision=replace(frame.decision, layout_id=layout),
        visible_elements={key: replace(value, source_layout_id=layout, action_point=value.bounds.center())
                          for key, value in frame.visible_elements.items()},
        hero_recruit_result=HeroRecruitResult(
            phase=phase, title_text="Albertus" if presentation else "Albertus Frag.",
            quantity=None if presentation else 10, star_count=2 if presentation else None,
            frame_ref=frame.frame_ref, source_screen=frame.screen_type, source_layout_id=layout,
        ),
    )


def _menu(*, attempts: int = 4, free: bool = False) -> Observation:
    visible = (UiElementId.PNC_HERO_HALL_RECRUIT_BANNER,)
    if free:
        visible += (UiElementId.PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON,)
    return make_observation(
        ScreenType.PNC_HERO_HALL, visible_ids=visible,
        visible_texts={UiElementId.PNC_HERO_HALL_RECRUIT_BANNER: f"Daily attempts:{attempts}"},
        artifact_path=Path("hero_hall.png"),
    )


class HeroRecruitResultNavigationTests(unittest.TestCase):
    def _session(self, frames: list[Observation]) -> tuple[CoreHeroHallSession, Mock]:
        captures = Mock(side_effect=frames)
        actuator = Mock()
        actuator.execute_action.return_value = True
        runtime = SimpleNamespace(
            observation_count=0, last_observation=None,
            runtime=SimpleNamespace(require_observed_action_executor=lambda _: actuator),
        )
        def capture(label, *, include_content=False):
            self.assertTrue(include_content)
            frame = captures(label)
            runtime.observation_count += 1
            runtime.last_observation = frame
            return frame
        runtime.observe = capture
        context = WorkflowContext(runtime, last_observation=None, effect=WorkflowEffect.NONSPENDING_STATE_CHANGE)
        observer = Mock(side_effect=context._observe_hero_hall)
        navigation = NavigationCore(
            actuator=actuator, observe=observer, edges=(),
            policy=NavigationPolicy(max_observations=4), sleep=lambda _: None,
        )
        runtime.navigation = navigation
        return CoreHeroHallSession(runtime, observer, Mock()), actuator

    def test_saved_result_chain_retains_each_phase_before_its_single_acknowledgment(self):
        presentation = _result(HeroRecruitResultPhase.HERO_PRESENTATION)
        fragment1 = _result(HeroRecruitResultPhase.FRAGMENT_RESULT)
        fragment2 = _result(HeroRecruitResultPhase.FRAGMENT_RESULT)
        menu1, menu2 = _menu(), _menu()
        session, actuator = self._session([presentation, fragment1, fragment2, menu1, menu2])
        retained = []
        def acknowledge(action, before):
            retained.append(before in session.result_observations)
            return True
        actuator.execute_action.side_effect = acknowledge
        result = session.observe_hero_hall("reconcile_saved_result")
        self.assertEqual(menu2, result)
        self.assertEqual([True, True], retained)
        self.assertEqual([UiElementId.PNC_HERO_RESULT_CONFIRM, UiElementId.PNC_HERO_RESULT_CLOSE],
                         [call.args[0].selector_id for call in actuator.execute_action.call_args_list])
        self.assertEqual((presentation, fragment2), session.result_observations)
        self.assertEqual(("hero_recruit_presentation.png", "hero_recruit_fragments.png", "hero_hall.png"),
                         session.artifact_paths())

    def test_wrong_phase_ocr_control_and_unbound_facts_cannot_acknowledge(self):
        source = _result(HeroRecruitResultPhase.HERO_PRESENTATION)
        selector = UiElementId.PNC_HERO_RESULT_CONFIRM
        invalid = (
            replace(source, visible_elements={}),
            replace(source, visible_elements={selector: replace(source.require(selector),
                source_kind=VisibleElementSourceKind.OCR)}),
            replace(source, hero_recruit_result=replace(source.hero_recruit_result, frame_ref=None)),
            replace(source, hero_recruit_result=replace(source.hero_recruit_result,
                phase=HeroRecruitResultPhase.FRAGMENT_RESULT)),
        )
        for frame in invalid:
            with self.subTest(frame=frame.hero_recruit_result):
                session, actuator = self._session([])
                with self.assertRaises(RuntimeError):
                    session.runtime.navigation.acknowledge_hero_recruit_result(frame, observe_content=session.observe)
                actuator.execute_action.assert_not_called()

    def test_paid_recruit_control_never_substitutes_for_close(self):
        source = _result(HeroRecruitResultPhase.FRAGMENT_RESULT)
        paid = make_observation(ScreenType.PNC_HERO_RECRUIT_RESULT,
                                visible_ids=(UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON,))
        source = replace(source, visible_elements=paid.visible_elements)
        session, actuator = self._session([source])
        with self.assertRaises(RuntimeError):
            session.observe_hero_hall("paid_result")
        actuator.execute_action.assert_not_called()

    def test_animation_settles_only_after_this_session_dispatched_once(self):
        before, dispatch = _menu(attempts=5, free=True), _menu(attempts=5, free=True)
        unknown = make_observation(ScreenType.UNKNOWN)
        presentation1 = _result(HeroRecruitResultPhase.HERO_PRESENTATION)
        presentation2 = _result(HeroRecruitResultPhase.HERO_PRESENTATION)
        fragment1 = _result(HeroRecruitResultPhase.FRAGMENT_RESULT)
        fragment2 = _result(HeroRecruitResultPhase.FRAGMENT_RESULT)
        menu1, menu2 = _menu(), _menu()
        session, actuator = self._session(
            [before, dispatch, unknown, presentation1, presentation2, fragment1, fragment2, menu1, menu2],
        )
        session.observe_hero_hall("pre")
        session.recruit_free_single()
        self.assertEqual(menu2, session.observe_hero_hall("post"))
        self.assertEqual([UiElementId.PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON,
                          UiElementId.PNC_HERO_RESULT_CONFIRM, UiElementId.PNC_HERO_RESULT_CLOSE],
                         [call.args[0].selector_id for call in actuator.execute_action.call_args_list])

    def test_unknown_saved_state_does_not_settle_or_send_any_input(self):
        session, actuator = self._session([make_observation(ScreenType.UNKNOWN)])
        with self.assertRaises(ValueError):
            session.observe_hero_hall("old_uncertain_receipt")
        self.assertEqual(1, session.observe.call_count)
        actuator.execute_action.assert_not_called()

    def test_repeated_phase_exhausts_confirmation_without_another_tap(self):
        source = _result(HeroRecruitResultPhase.HERO_PRESENTATION)
        repeats = [_result(HeroRecruitResultPhase.HERO_PRESENTATION) for _ in range(4)]
        session, actuator = self._session([source, *repeats])
        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            session.observe_hero_hall("unresponsive_confirmation")
        self.assertEqual(1, actuator.execute_action.call_count)
