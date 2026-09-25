"""Action handler for iOS automation using WebDriverAgent."""

from typing import Any, Callable

from phone_agent.actions.handler import ActionHandler, ActionResult
from phone_agent.device_factory import DeviceFactory, DeviceType


class IOSActionHandler(ActionHandler):
    """iOS action handler.

    Gesture, input, and note/API behavior come from ActionHandler.
    This subclass only supplies an iOS DeviceFactory and the verbose logs.
    """

    def __init__(
        self,
        wda_url: str = "http://localhost:8100",
        session_id: str | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
        interact_callback: Callable[[str], str] | None = None,
        call_api_callback: Callable[[str, list[dict[str, Any]]], str] | None = None,
        model_client: Any = None,
        verbose: bool = True,
    ):
        self.wda_url = wda_url
        self.session_id = session_id
        self.verbose = verbose
        super().__init__(
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
            interact_callback=interact_callback,
            call_api_callback=call_api_callback,
            model_client=model_client,
            device_factory=DeviceFactory(
                DeviceType.IOS,
                wda_url=wda_url,
                session_id=session_id,
            ),
        )

    def _handle_tap(self, action: dict, width: int, height: int) -> ActionResult:
        element = action.get("element")
        if self.verbose and element:
            x, y = self._convert_relative_to_absolute(element, width, height)
            print(f"Physically tap on ({x}, {y})")
        return super()._handle_tap(action, width, height)

    def _handle_swipe(self, action: dict, width: int, height: int) -> ActionResult:
        start = action.get("start")
        end = action.get("end")
        if self.verbose and start and end:
            start_x, start_y = self._convert_relative_to_absolute(start, width, height)
            end_x, end_y = self._convert_relative_to_absolute(end, width, height)
            print(
                f"Physically scroll from ({start_x}, {start_y}) "
                f"to ({end_x}, {end_y})"
            )
        return super()._handle_swipe(action, width, height)
