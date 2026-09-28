"""Navigation workshop routes tests."""

from datetime import UTC, datetime, timedelta
import unittest

from pnc_automation.app.automation.engine.navigation_core import (
    NavigationCore,
    reviewed_navigation_edges,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.navigation.core_frames import Actuator
from tests.support.pnc.navigation.core_mail import mail_frame


class PetWorkshopInnerRouteTests(unittest.TestCase):
    def test_inner_transitions_require_current_measured_controls(self):
        routes = (
            (ScreenType.PNC_ILLUSORY_BEAST_MANOR,
             UiElementId.PNC_ILLUSORY_BEAST_MANOR_PET_WORKSHOP_BUTTON,
             ScreenType.PNC_PET_WORKSHOP),
            (ScreenType.PNC_PET_WORKSHOP, UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
             ScreenType.PNC_ILLUSORY_BEAST_MANOR),
            (ScreenType.PNC_ILLUSORY_BEAST_MANOR, UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
             ScreenType.PNC_HOME_CITY),
        )
        for source, selector, destination in routes:
            for present in (True, False):
                with self.subTest(source=source, destination=destination, present=present):
                    now = datetime.now(UTC)
                    frames = iter(
                        mail_frame(
                            screen,
                            selector=selector if present and index < 2 else None,
                            captured_at=now + timedelta(seconds=index),
                        )
                        for index, screen in enumerate((source, source, destination, destination))
                    )
                    actuator = Actuator()
                    core = NavigationCore(
                        actuator, lambda _: next(frames), reviewed_navigation_edges(),
                        sleep=lambda _: None,
                    )
                    if present:
                        self.assertEqual(destination, core.navigate(destination).screen_type)
                        self.assertEqual([selector], [action.selector_id for action in actuator.actions])
                    else:
                        with self.assertRaisesRegex(RuntimeError, "current-frame visual evidence"):
                            core.navigate(destination)
                        self.assertEqual([], actuator.actions)

    def test_workshop_return_confirms_manor_before_returning_home(self):
        screens = (
            ScreenType.PNC_PET_WORKSHOP, ScreenType.PNC_PET_WORKSHOP,
            ScreenType.PNC_ILLUSORY_BEAST_MANOR, ScreenType.PNC_ILLUSORY_BEAST_MANOR,
            ScreenType.PNC_ILLUSORY_BEAST_MANOR,
            ScreenType.PNC_HOME_CITY, ScreenType.PNC_HOME_CITY,
        )
        now = datetime.now(UTC)
        frames = iter(
            mail_frame(
                screen, selector=UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                captured_at=now + timedelta(seconds=index),
            )
            for index, screen in enumerate(screens)
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator, lambda _: next(frames), reviewed_navigation_edges(), sleep=lambda _: None,
        )

        self.assertEqual(ScreenType.PNC_HOME_CITY, core.navigate(ScreenType.PNC_HOME_CITY).screen_type)
        self.assertEqual(
            [UiElementId.PNC_BACK_BUTTON_TOP_LEFT] * 2,
            [action.selector_id for action in actuator.actions],
        )
        self.assertIsNone(next(frames, None))

    def test_home_cannot_bypass_building_acquisition_with_inner_route(self):
        actuator = Actuator()
        core = NavigationCore(
            actuator, lambda _: mail_frame(ScreenType.PNC_HOME_CITY),
            reviewed_navigation_edges(), sleep=lambda _: None,
        )

        with self.assertRaisesRegex(RuntimeError, "No reviewed route"):
            core.navigate(ScreenType.PNC_PET_WORKSHOP)
        self.assertEqual([], actuator.actions)
