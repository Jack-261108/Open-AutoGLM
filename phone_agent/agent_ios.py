"""iOS PhoneAgent class for orchestrating iOS phone automation."""

from dataclasses import dataclass
from typing import Any, Callable

from phone_agent.actions.handler import finish, parse_action
from phone_agent.actions.handler_ios import IOSActionHandler
from phone_agent.agent import AgentConfig, PhoneAgent, StepResult
from phone_agent.device_factory import DeviceType
from phone_agent.model import ModelClient, ModelClientProtocol, ModelConfig
from phone_agent.xctest import XCTestConnection, get_current_app, get_screenshot

__all__ = ["IOSPhoneAgent", "IOSAgentConfig", "StepResult"]


@dataclass
class IOSAgentConfig(AgentConfig):
    """Configuration for the iOS PhoneAgent."""

    device_type: DeviceType = DeviceType.IOS
    wda_url: str = "http://localhost:8100"
    session_id: str | None = None
    device_id: str | None = None  # iOS device UDID


class IOSPhoneAgent(PhoneAgent):
    """
    AI-powered agent for automating iOS phone interactions.

    The agent uses a vision-language model to understand screen content
    and decide on actions to complete user tasks via WebDriverAgent.

    Args:
        model_config: Configuration for the AI model.
        agent_config: Configuration for the iOS agent behavior.
        confirmation_callback: Optional callback for sensitive action confirmation.
        takeover_callback: Optional callback for takeover requests.
        interact_callback: Optional callback for user interaction choices.
        call_api_callback: Optional callback for external API / summarization calls.
        model_client: Optional custom model client.
    """

    def __init__(
        self,
        model_config: ModelConfig | None = None,
        agent_config: IOSAgentConfig | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
        interact_callback: Callable[[str], str] | None = None,
        call_api_callback: Callable[[str, list[dict[str, Any]]], str] | None = None,
        model_client: ModelClientProtocol | None = None,
    ):
        config = agent_config or IOSAgentConfig()

        # Initialize WDA connection and create session if needed
        self.wda_connection = XCTestConnection(wda_url=config.wda_url)

        # Auto-create session if not provided
        if config.session_id is None:
            success, session_id = self.wda_connection.start_wda_session()
            if success and session_id != "session_started":
                config.session_id = session_id
                if config.verbose:
                    print(f"✅ Created WDA session: {session_id}")
            elif config.verbose:
                print(f"⚠️  Using default WDA session (no explicit session ID)")

        # Create model client via module ModelClient if not injected
        if model_client is None:
            owned_client = ModelClient(
                model_config or ModelConfig(), verbose=config.verbose
            )
            resolved_client = owned_client
            owned_ref = owned_client
        else:
            resolved_client = model_client
            owned_ref = None

        super().__init__(
            model_config=model_config,
            agent_config=config,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
            interact_callback=interact_callback,
            call_api_callback=call_api_callback,
            model_client=resolved_client,
        )
        self._owned_model_client = owned_ref

        # Retain explicit IOSActionHandler instance for backward compatibility
        self.action_handler = IOSActionHandler(
            wda_url=config.wda_url,
            session_id=config.session_id,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
            interact_callback=interact_callback,
            call_api_callback=call_api_callback,
            model_client=self.model_client,
            verbose=config.verbose,
        )

    def _capture_screen_and_app(self) -> tuple[Any, str, str]:
        """Capture screenshot and current app (preserves agent_ios module monkeypatches)."""
        screenshot = get_screenshot(
            wda_url=self.agent_config.wda_url,
            session_id=self.agent_config.session_id,
            device_id=self.agent_config.device_id,
        )
        current_app = get_current_app(
            wda_url=self.agent_config.wda_url,
            session_id=self.agent_config.session_id,
        )
        return screenshot, current_app, self._capture_ui_text(screenshot)

    def _parse_model_action(self, response: Any) -> Any:
        """Parse action using module-scoped parse_action."""
        return response.parsed_action or parse_action(response.action)

    def _fallback_finish(self, err: str) -> Any:
        """Create fallback finish using module-scoped finish."""
        return finish(message=err)
