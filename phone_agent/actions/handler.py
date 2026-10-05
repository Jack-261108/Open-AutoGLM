"""Action handler for processing AI model outputs."""

import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable

from phone_agent.config.timing import TIMING_CONFIG
from phone_agent.device_factory import get_device_factory


@dataclass
class ActionResult:
    """Result of an action execution."""

    success: bool
    should_finish: bool
    message: str | None = None
    requires_confirmation: bool = False
    observation: str | None = None


class ActionHandler:
    """
    Handles execution of actions from AI model output.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
        confirmation_callback: Optional callback for sensitive action confirmation.
            Should return True to proceed, False to cancel.
        takeover_callback: Optional callback for takeover requests (login, captcha).
        interact_callback: Optional callback for user interaction choices.
        call_api_callback: Optional callback for external API / summarization calls.
        model_client: Optional model client for internal summarization.
    """

    def __init__(
        self,
        device_id: str | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
        interact_callback: Callable[[str], str] | None = None,
        call_api_callback: Callable[[str, list[dict[str, Any]]], str] | None = None,
        model_client: Any = None,
        device_factory: Any = None,
    ):
        self.device_id = device_id
        self.confirmation_callback = confirmation_callback or self._default_confirmation
        self.takeover_callback = takeover_callback or self._default_takeover
        self.interact_callback = interact_callback or self._default_interact
        self.call_api_callback = call_api_callback
        self.model_client = model_client
        self.device_factory = device_factory
        self.notes: list[dict[str, Any]] = []

    def _get_device_factory(self) -> Any:
        """Get the device factory instance (injected or global)."""
        return self.device_factory if self.device_factory is not None else get_device_factory()

    def clear_notes(self) -> None:
        """Clear recorded notes."""
        self.notes.clear()

    def execute(
        self, action: dict[str, Any], screen_width: int, screen_height: int
    ) -> ActionResult:
        """
        Execute an action from the AI model.

        Args:
            action: The action dictionary from the model.
            screen_width: Current screen width in pixels.
            screen_height: Current screen height in pixels.

        Returns:
            ActionResult indicating success and whether to finish.
        """
        action_type = action.get("_metadata")

        if action_type == "finish":
            return ActionResult(
                success=True, should_finish=True, message=action.get("message")
            )

        if action_type != "do":
            return ActionResult(
                success=False,
                should_finish=True,
                message=f"Unknown action type: {action_type}",
            )

        action_name = action.get("action")
        if not isinstance(action_name, str):
            return ActionResult(
                success=False,
                should_finish=False,
                message="Action name must be a string",
            )
        handler_method = self._get_handler(action_name)

        if handler_method is None:
            return ActionResult(
                success=False,
                should_finish=False,
                message=f"Unknown action: {action_name}",
            )

        try:
            return handler_method(action, screen_width, screen_height)
        except Exception as e:
            return ActionResult(
                success=False, should_finish=False, message=f"Action failed: {e}"
            )

    def _get_handler(self, action_name: str) -> Callable | None:
        """Get the handler method for an action."""
        handlers = {
            "Launch": self._handle_launch,
            "Tap": self._handle_tap,
            "Type": self._handle_type,
            "Type_Name": self._handle_type,
            "Swipe": self._handle_swipe,
            "Back": self._handle_back,
            "Home": self._handle_home,
            "Double Tap": self._handle_double_tap,
            "Long Press": self._handle_long_press,
            "Wait": self._handle_wait,
            "Take_over": self._handle_takeover,
            "Note": self._handle_note,
            "Call_API": self._handle_call_api,
            "Interact": self._handle_interact,
            "Set_Clipboard": self._handle_set_clipboard,
            "Set Clipboard": self._handle_set_clipboard,
            "Get_Clipboard": self._handle_get_clipboard,
            "Get Clipboard": self._handle_get_clipboard,
            "Force_Stop": self._handle_force_stop,
            "Force Stop": self._handle_force_stop,
            "Clear_Data": self._handle_clear_data,
            "Clear Data": self._handle_clear_data,
        }
        return handlers.get(action_name)

    def _convert_relative_to_absolute(
        self, element: list[int], screen_width: int, screen_height: int
    ) -> tuple[int, int]:
        """Convert relative coordinates (0-1000) to absolute pixels."""
        x = int(element[0] / 1000 * screen_width)
        y = int(element[1] / 1000 * screen_height)
        return x, y

    def _handle_launch(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle app launch action."""
        app_name = action.get("app")
        if not app_name:
            return ActionResult(False, False, "No app name specified")

        device_factory = self._get_device_factory()
        success = device_factory.launch_app(app_name, self.device_id)
        if success:
            return ActionResult(True, False)
        return ActionResult(False, False, f"App not found: {app_name}")

    def _handle_tap(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle tap action."""
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)

        # Check for sensitive operation
        if "message" in action:
            if not self.confirmation_callback(action["message"]):
                return ActionResult(
                    success=False,
                    should_finish=True,
                    message="User cancelled sensitive operation",
                )

        device_factory = self._get_device_factory()
        device_factory.tap(x, y, self.device_id)
        return ActionResult(True, False)

    def _handle_type(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle text input action."""
        text = action.get("text", "")

        device_factory = self._get_device_factory()

        original_ime: str | None = None
        try:
            # Switch to ADB keyboard. iOS returns "" and has no IME to switch.
            original_ime = device_factory.detect_and_set_adb_keyboard(self.device_id)
            if original_ime:
                time.sleep(TIMING_CONFIG.action.keyboard_switch_delay)

            # Clear existing text and type new text
            device_factory.clear_text(self.device_id)
            time.sleep(TIMING_CONFIG.action.text_clear_delay)

            # Handle multiline text by splitting on newlines
            device_factory.type_text(text, self.device_id)
            time.sleep(TIMING_CONFIG.action.text_input_delay)
        finally:
            # Always restore the original keyboard once we captured an IME id, so
            # a failure during clear/type does not leave the device stuck on the
            # ADB keyboard. An empty IME string would clear the active input
            # method rather than restore it, so we skip restore in that case.
            if original_ime:
                try:
                    device_factory.restore_keyboard(original_ime, self.device_id)
                except Exception:
                    # Best-effort restore; the original failure is more important.
                    pass
                time.sleep(TIMING_CONFIG.action.keyboard_restore_delay)

            try:
                device_factory.hide_keyboard(self.device_id)
            except Exception:
                pass

        return ActionResult(True, False)

    def _handle_swipe(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle swipe action."""
        start = action.get("start")
        end = action.get("end")

        if not start or not end:
            return ActionResult(False, False, "Missing swipe coordinates")

        start_x, start_y = self._convert_relative_to_absolute(start, width, height)
        end_x, end_y = self._convert_relative_to_absolute(end, width, height)

        device_factory = self._get_device_factory()
        device_factory.swipe(start_x, start_y, end_x, end_y, device_id=self.device_id)
        return ActionResult(True, False)

    def _handle_back(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle back button action."""
        device_factory = self._get_device_factory()
        device_factory.back(self.device_id)
        return ActionResult(True, False)

    def _handle_home(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle home button action."""
        device_factory = self._get_device_factory()
        device_factory.home(self.device_id)
        return ActionResult(True, False)

    def _handle_double_tap(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle double tap action."""
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)
        device_factory = self._get_device_factory()
        device_factory.double_tap(x, y, self.device_id)
        return ActionResult(True, False)

    def _handle_long_press(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle long press action."""
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)
        device_factory = self._get_device_factory()
        device_factory.long_press(x, y, device_id=self.device_id)
        return ActionResult(True, False)

    def _handle_wait(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle wait action."""
        duration_str = action.get("duration", "1 seconds")
        try:
            duration = float(duration_str.replace("seconds", "").strip())
        except ValueError:
            duration = 1.0

        time.sleep(duration)
        return ActionResult(True, False)

    def _handle_takeover(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle takeover request (login, captcha, etc.)."""
        message = action.get("message", "User intervention required")
        self.takeover_callback(message)
        return ActionResult(True, False)

    def _handle_note(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle note action (recording page content)."""
        device_factory = self._get_device_factory()
        screenshot_data = None
        current_app = ""
        capture_error: Exception | None = None
        try:
            screenshot = device_factory.get_screenshot(self.device_id)
            screenshot_data = getattr(screenshot, "base64_data", None)
        except Exception as exc:
            capture_error = exc
        try:
            current_app = device_factory.get_current_app(self.device_id) or ""
        except Exception as exc:
            if capture_error is None:
                capture_error = exc

        if not screenshot_data:
            detail = (
                f"Note capture failed: {capture_error}"
                if capture_error
                else "Note capture failed: screenshot missing"
            )
            return ActionResult(
                success=False,
                should_finish=False,
                message=detail,
                observation=detail,
            )

        note_entry = {
            "index": len(self.notes) + 1,
            "message": action.get("message", ""),
            "timestamp": time.time(),
            "image_base64": screenshot_data,
            "app": current_app,
        }
        self.notes.append(note_entry)
        obs = f"Page noted (note #{len(self.notes)} recorded)."
        return ActionResult(
            success=True,
            should_finish=False,
            message=action.get("message"),
            observation=obs,
        )

    def _format_notes(self) -> str:
        """Render every recorded note, not just the latest one."""
        lines: list[str] = []
        for note in self.notes:
            index = note.get("index", "?")
            app = note.get("app") or ""
            message = note.get("message") or ""
            lines.append(f"- Note #{index} (app: {app}): {message}")
        return "\n".join(lines)

    def _summarize_with_model_client(self, instruction: str) -> str:
        """Summarize notes or screen using model_client."""
        from phone_agent.model.client import MessageBuilder

        messages = [
            MessageBuilder.create_system_message(
                "You are an assistant that summarizes recorded mobile screen information according to instructions."
            ),
        ]
        if self.notes:
            messages.append(
                MessageBuilder.create_user_message(
                    text=(
                        f"Instruction: {instruction}\n\n"
                        f"Recorded notes ({len(self.notes)}):\n"
                        f"{self._format_notes()}"
                    )
                )
            )
            for note in self.notes:
                image = note.get("image_base64")
                if not image:
                    continue
                messages.append(
                    MessageBuilder.create_user_message(
                        text=f"Screenshot for note #{note.get('index', '?')}",
                        image_base64=image,
                    )
                )
        else:
            messages.append(
                MessageBuilder.create_user_message(
                    text=f"Instruction: {instruction}",
                )
            )

        try:
            response = self.model_client.request(messages)
            return getattr(response, "raw_content", "") or getattr(response, "thinking", "") or getattr(response, "action", "")
        except Exception as exc:
            return f"Model summarization error: {exc}"

    def _handle_call_api(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle API call action (summarization or external service call)."""
        instruction = action.get("instruction", "")

        if self.call_api_callback is not None:
            try:
                summary = self.call_api_callback(instruction, self.notes)
            except Exception as e:
                return ActionResult(
                    success=False,
                    should_finish=False,
                    message=f"Call_API callback failed: {e}",
                    observation=f"Call_API error: {e}",
                )
        elif self.model_client is not None:
            summary = self._summarize_with_model_client(instruction)
        else:
            if self.notes:
                summary = (
                    f"Summarized {len(self.notes)} recorded notes according to "
                    f"instruction: {instruction}\n{self._format_notes()}"
                )
            else:
                summary = f"API instruction processed: {instruction}"

        return ActionResult(
            success=True,
            should_finish=False,
            message=instruction,
            observation=f"API result for instruction '{instruction}':\n{summary}",
        )

    def _handle_interact(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle interaction request (user choice needed)."""
        message = action.get("message", "")
        user_choice = self.interact_callback(message)
        obs = f"User choice: {user_choice}" if user_choice else "User provided no response."
        return ActionResult(
            success=True,
            should_finish=False,
            message=message or "User interaction handled",
            observation=obs,
        )

    def _handle_set_clipboard(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle setting system clipboard."""
        text = action.get("text", "")
        device_factory = self._get_device_factory()
        device_factory.set_clipboard(text, self.device_id)
        return ActionResult(
            success=True,
            should_finish=False,
            message=f"Copied {len(text)} chars to clipboard",
            observation=f"Clipboard set with {len(text)} characters.",
        )

    def _handle_get_clipboard(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle reading system clipboard."""
        device_factory = self._get_device_factory()
        content = device_factory.get_clipboard(self.device_id)
        return ActionResult(
            success=True,
            should_finish=False,
            message="Read clipboard content",
            observation=f"Clipboard content:\n{content}",
        )

    def _handle_force_stop(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle force stopping an app."""
        app = action.get("app")
        if not app:
            return ActionResult(False, False, "No app specified to force stop")
        device_factory = self._get_device_factory()
        device_factory.force_stop_app(app, self.device_id)
        return ActionResult(
            success=True,
            should_finish=False,
            message=f"Force stopped {app}",
            observation=f"Application {app} force stopped.",
        )

    def _handle_clear_data(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle clearing app data."""
        app = action.get("app")
        if not app:
            return ActionResult(False, False, "No app specified to clear data")
        device_factory = self._get_device_factory()
        device_factory.clear_app_data(app, self.device_id)
        return ActionResult(
            success=True,
            should_finish=False,
            message=f"Cleared data for {app}",
            observation=f"Application data and cache cleared for {app}.",
        )

    def _send_keyevent(self, keycode: str) -> None:
        """Send a keyevent to the device."""
        from phone_agent.device_factory import DeviceType
        from phone_agent.hdc.connection import _run_hdc_command

        device_factory = self._get_device_factory()

        # Handle HDC devices with HarmonyOS-specific keyEvent command
        if device_factory.device_type == DeviceType.HDC:
            hdc_prefix = ["hdc", "-t", self.device_id] if self.device_id else ["hdc"]
            
            # Map common keycodes to HarmonyOS keyEvent codes
            # KEYCODE_ENTER (66) -> 2054 (HarmonyOS Enter key code)
            if keycode == "KEYCODE_ENTER" or keycode == "66":
                _run_hdc_command(
                    hdc_prefix + ["shell", "uitest", "uiInput", "keyEvent", "2054"],
                    capture_output=True,
                    text=True,
                )
            else:
                # For other keys, try to use the numeric code directly
                # If keycode is a string like "KEYCODE_ENTER", convert it
                try:
                    # Try to extract numeric code from string or use as-is
                    if keycode.startswith("KEYCODE_"):
                        # For now, only handle ENTER, other keys may need mapping
                        if "ENTER" in keycode:
                            _run_hdc_command(
                                hdc_prefix + ["shell", "uitest", "uiInput", "keyEvent", "2054"],
                                capture_output=True,
                                text=True,
                            )
                        else:
                            # Fallback to ADB-style command for unsupported keys
                            subprocess.run(
                                hdc_prefix + ["shell", "input", "keyevent", keycode],
                                capture_output=True,
                                text=True,
                            )
                    else:
                        # Assume it's a numeric code
                        _run_hdc_command(
                            hdc_prefix + ["shell", "uitest", "uiInput", "keyEvent", str(keycode)],
                            capture_output=True,
                            text=True,
                        )
                except Exception:
                    # Fallback to ADB-style command
                    subprocess.run(
                        hdc_prefix + ["shell", "input", "keyevent", keycode],
                        capture_output=True,
                        text=True,
                    )
        else:
            # ADB devices use standard input keyevent command
            cmd_prefix = ["adb", "-s", self.device_id] if self.device_id else ["adb"]
            subprocess.run(
                cmd_prefix + ["shell", "input", "keyevent", keycode],
                capture_output=True,
                text=True,
            )

    @staticmethod
    def _default_confirmation(message: str) -> bool:
        """Default confirmation callback using console input."""
        response = input(f"Sensitive operation: {message}\nConfirm? (Y/N): ")
        return response.upper() == "Y"

    @staticmethod
    def _default_takeover(message: str) -> None:
        """Default takeover callback using console input."""
        input(f"{message}\nPress Enter after completing manual operation...")

    @staticmethod
    def _default_interact(message: str) -> str:
        """Default interaction callback using console input."""
        prompt = (
            f"User interaction required: {message}\nYour choice: "
            if message
            else "User interaction required.\nYour choice: "
        )
        return input(prompt)


def parse_action(response: str) -> dict[str, Any]:
    """
    Parse and validate one complete DSL action from the model response.

    Args:
        response: A complete ``do(...)`` or ``finish(...)`` expression.

    Returns:
        Parsed and schema-validated action dictionary.

    Raises:
        ValueError: If the response violates the DSL or action schema.
    """
    from phone_agent.model.response_parser import parse_action_text

    return parse_action_text(response)


def do(**kwargs) -> dict[str, Any]:
    """Helper function for creating 'do' actions."""
    kwargs["_metadata"] = "do"
    return kwargs


def finish(**kwargs) -> dict[str, Any]:
    """Helper function for creating 'finish' actions."""
    kwargs["_metadata"] = "finish"
    return kwargs
