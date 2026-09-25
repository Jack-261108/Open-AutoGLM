"""Main PhoneAgent class for orchestrating phone automation."""

import json
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Literal

from phone_agent.actions import ActionHandler
from phone_agent.actions.handler import finish, parse_action
from phone_agent.config import get_messages, get_system_prompt
from phone_agent.device_factory import DeviceFactory, DeviceType, get_device_factory
from phone_agent.model import ModelClient, ModelClientProtocol, ModelConfig
from phone_agent.model.client import MessageBuilder

AccessibilityMode = Literal["auto", "on", "off"]
_UI_ELEMENTS_MARKER = "\n\n** UI Elements **\n"


@dataclass
class AgentConfig:
    """Configuration for the PhoneAgent."""

    max_steps: int = 100
    device_id: str | None = None
    device_type: DeviceType = DeviceType.ADB
    wda_url: str = "http://localhost:8100"
    session_id: str | None = None
    accessibility: AccessibilityMode = "auto"
    lang: str = "cn"
    system_prompt: str | None = None
    verbose: bool = True

    def __post_init__(self):
        if type(self.max_steps) is not int or self.max_steps < 1:
            raise ValueError("max_steps must be a positive integer")
        if self.accessibility not in ("auto", "on", "off"):
            raise ValueError("accessibility must be auto, on, or off")
        if self.system_prompt is None:
            self.system_prompt = get_system_prompt(self.lang)


@dataclass
class StepResult:
    """Result of a single agent step."""

    success: bool
    finished: bool
    action: dict[str, Any] | None
    thinking: str
    message: str | None = None
    observation: str | None = None


def _drop_ui_elements(message: dict[str, Any]) -> dict[str, Any]:
    """Remove the accessibility list after the model has seen it."""
    content = message.get("content")
    if not isinstance(content, list):
        return message
    for item in content:
        text = item.get("text")
        if item.get("type") != "text" or not isinstance(text, str):
            continue
        split_at = text.rfind(_UI_ELEMENTS_MARKER)
        if split_at >= 0:
            item["text"] = text[:split_at]
    return message


class PhoneAgent:
    """
    AI-powered agent for automating Android phone interactions.

    The agent uses a vision-language model to understand screen content
    and decide on actions to complete user tasks.

    Args:
        model_config: Configuration for the AI model.
        agent_config: Configuration for the agent behavior.
        confirmation_callback: Optional callback for sensitive action confirmation.
        takeover_callback: Optional callback for takeover requests.
        interact_callback: Optional callback for user interaction choices.
        call_api_callback: Optional callback for external API / summarization calls.
        model_client: Optional custom model client.

    Example:
        >>> from phone_agent import PhoneAgent
        >>> from phone_agent.model import ModelConfig
        >>>
        >>> model_config = ModelConfig(base_url="http://localhost:8000/v1")
        >>> agent = PhoneAgent(model_config)
        >>> agent.run("Open WeChat and send a message to John")
    """

    def __init__(
        self,
        model_config: ModelConfig | None = None,
        agent_config: AgentConfig | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
        interact_callback: Callable[[str], str] | None = None,
        call_api_callback: Callable[[str, list[dict[str, Any]]], str] | None = None,
        model_client: ModelClientProtocol | None = None,
    ):
        self.model_config = model_config or ModelConfig()
        self.agent_config = agent_config or AgentConfig()

        if model_client is None:
            owned_model_client = ModelClient(
                self.model_config, verbose=self.agent_config.verbose
            )
            self.model_client: ModelClientProtocol = owned_model_client
            self._owned_model_client: ModelClient | None = owned_model_client
        else:
            self.model_client = model_client
            self._owned_model_client = None
        self._model_client_closed = False

        if self.agent_config.device_type == DeviceType.IOS:
            self._ensure_ios_session()
            self.device_factory = DeviceFactory(
                DeviceType.IOS,
                wda_url=self.agent_config.wda_url,
                session_id=self.agent_config.session_id,
            )
        elif self.agent_config.device_type == DeviceType.HDC:
            self.device_factory = DeviceFactory(DeviceType.HDC)
        else:
            self.device_factory = get_device_factory()

        self.action_handler = ActionHandler(
            device_id=self.agent_config.device_id,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
            interact_callback=interact_callback,
            call_api_callback=call_api_callback,
            model_client=self.model_client,
            device_factory=self.device_factory,
        )

        self._context: list[dict[str, Any]] = []
        self._step_count = 0
        self._last_observation: str | None = None

    def run(self, task: str) -> str:
        """
        Run the agent to complete a task.

        Args:
            task: Natural language description of the task.

        Returns:
            Final message from the agent.
        """
        self.reset()

        # First step with user prompt
        result = self._execute_step(task, is_first=True)

        if result.finished:
            return result.message or "Task completed"

        # Continue until finished or max steps reached
        while self._step_count < self.agent_config.max_steps:
            result = self._execute_step(is_first=False)

            if result.finished:
                return result.message or "Task completed"

        return "Max steps reached"

    def step(self, task: str | None = None) -> StepResult:
        """
        Execute a single step of the agent.

        Useful for manual control or debugging.

        Args:
            task: Task description (only needed for first step).

        Returns:
            StepResult with step details.
        """
        is_first = len(self._context) == 0

        if is_first and not task:
            raise ValueError("Task is required for the first step")

        return self._execute_step(task, is_first)

    def reset(self) -> None:
        """Reset the agent state for a new task."""
        self._context = []
        self._step_count = 0
        self._last_observation = None
        if hasattr(self.action_handler, "clear_notes"):
            self.action_handler.clear_notes()

    def close(self) -> None:
        """Close an internally owned model client exactly once."""
        if self._model_client_closed or self._owned_model_client is None:
            return
        self._owned_model_client.close()
        self._model_client_closed = True

    def _ensure_ios_session(self) -> None:
        """Start a WDA session unless IOSPhoneAgent already did."""
        if getattr(self, "wda_connection", None) is not None:
            return
        if self.agent_config.session_id is not None:
            return

        from phone_agent.xctest import XCTestConnection

        connection = XCTestConnection(wda_url=self.agent_config.wda_url)
        self.wda_connection = connection
        success, session_id = connection.start_wda_session()
        if success and session_id != "session_started":
            self.agent_config.session_id = session_id
            if self.agent_config.verbose:
                print(f"✅ Created WDA session: {session_id}")
        elif self.agent_config.verbose:
            print("⚠️  Using default WDA session (no explicit session ID)")

    def _capture_screen_and_app(self) -> tuple[Any, str, str]:
        """Capture screenshot, current app, and compact accessibility text."""
        screenshot = self.device_factory.get_screenshot(self.agent_config.device_id)
        current_app = self.device_factory.get_current_app(self.agent_config.device_id)
        return screenshot, current_app, self._capture_ui_text(screenshot)

    def _capture_ui_text(self, screenshot: Any) -> str:
        """Read the accessibility tree. Empty string keeps screenshot-only behavior."""
        mode = self.agent_config.accessibility
        if mode == "off" or (
            mode == "auto" and not getattr(screenshot, "is_fallback", False)
        ):
            return ""
        getter = getattr(self.device_factory, "get_ui_tree", None)
        if getter is None:
            return ""
        try:
            tree = getter(self.agent_config.device_id)
        except Exception as exc:
            if self.agent_config.verbose:
                print(f"UI tree unavailable: {exc}")
            return ""
        from phone_agent.accessibility import format_ui_tree

        return format_ui_tree(tree)

    def _screen_info(self, current_app: str, screenshot: Any) -> str:
        """Describe the screen. A fallback image is not a real screenshot."""
        if getattr(screenshot, "is_fallback", False):
            return MessageBuilder.build_screen_info(
                current_app, screenshot="unavailable"
            )
        return MessageBuilder.build_screen_info(current_app)

    def _parse_model_action(self, response: Any) -> Any:
        """Parse or resolve the action from model response."""
        return response.parsed_action or parse_action(response.action)

    def _fallback_finish(self, err: str) -> Any:
        """Create a fallback finish action."""
        return finish(message=err)

    def _execute_step(
        self, user_prompt: str | None = None, is_first: bool = False
    ) -> StepResult:
        """Execute a single step of the agent loop."""
        self._step_count += 1

        # Capture current screen state
        screenshot, current_app, ui_text = self._capture_screen_and_app()

        # Build messages
        if is_first:
            system_prompt = self.agent_config.system_prompt
            if system_prompt is None:
                raise ValueError("system_prompt must be initialized")
            self._context.append(MessageBuilder.create_system_message(system_prompt))

            screen_info = self._screen_info(current_app, screenshot)
            text_content = f"{user_prompt}\n\n{screen_info}"
        else:
            screen_info = self._screen_info(current_app, screenshot)
            if self._last_observation:
                text_content = (
                    f"** Previous Action Observation **\n"
                    f"{self._last_observation}\n\n"
                    f"** Screen Info **\n\n{screen_info}"
                )
                self._last_observation = None
            else:
                text_content = f"** Screen Info **\n\n{screen_info}"

        if ui_text:
            text_content = f"{text_content}{_UI_ELEMENTS_MARKER}{ui_text}"

        self._context.append(
            MessageBuilder.create_user_message(
                text=text_content, image_base64=screenshot.base64_data
            )
        )
        user_message_index = len(self._context) - 1
        msgs = get_messages(self.agent_config.lang)

        # Get model response and always remove the request screenshot afterwards.
        try:
            if self.agent_config.verbose:
                print("\n" + "=" * 50)
                print(f"💭 {msgs['thinking']}:")
                print("-" * 50)
            response = self.model_client.request(self._context)
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking="",
                message=f"Model error: {e}",
            )
        finally:
            self._context[user_message_index] = _drop_ui_elements(
                MessageBuilder.remove_images_from_message(
                    self._context[user_message_index]
                )
            )

        # Prefer the normalized action produced by the model layer.
        try:
            action = self._parse_model_action(response)
        except ValueError as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking=response.thinking,
                message=f"Model action parse error: {e}",
            )

        if self.agent_config.verbose:
            print("-" * 50)
            print(f"🎯 {msgs['action']}:")
            print(json.dumps(action, ensure_ascii=False, indent=2))
            print("=" * 50 + "\n")

        # Execute action
        try:
            result = self.action_handler.execute(
                action, screenshot.width, screenshot.height
            )
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            result = self.action_handler.execute(
                self._fallback_finish(str(e)), screenshot.width, screenshot.height
            )

        observation = getattr(result, "observation", None)
        if observation:
            self._last_observation = observation

        # Add assistant response to context
        self._context.append(
            MessageBuilder.create_assistant_message(
                f"<think>{response.thinking}</think><answer>{response.action}</answer>"
            )
        )

        # Check if finished
        finished = action.get("_metadata") == "finish" or result.should_finish

        if finished and self.agent_config.verbose:
            msgs = get_messages(self.agent_config.lang)
            print("\n" + "🎉 " + "=" * 48)
            print(
                f"✅ {msgs['task_completed']}: {result.message or action.get('message', msgs['done'])}"
            )
            print("=" * 50 + "\n")

        return StepResult(
            success=result.success,
            finished=finished,
            action=action,
            thinking=response.thinking,
            message=result.message or action.get("message"),
            observation=observation,
        )

    @property
    def context(self) -> list[dict[str, Any]]:
        """Get the current conversation context."""
        return self._context.copy()

    @property
    def step_count(self) -> int:
        """Get the current step count."""
        return self._step_count
