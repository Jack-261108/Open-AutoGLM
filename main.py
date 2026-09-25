#!/usr/bin/env python3
"""
Phone Agent CLI - AI-powered phone automation.

Usage:
    python main.py [OPTIONS]

Environment Variables:
    PHONE_AGENT_BASE_URL: Model API base URL (default: http://localhost:8000/v1)
    PHONE_AGENT_MODEL: Model name (default: autoglm-phone-9b)
    PHONE_AGENT_API_KEY: API key for model authentication (default: EMPTY)
    PHONE_AGENT_MAX_STEPS: Maximum steps per task (default: 100)
    PHONE_AGENT_DEVICE_ID: ADB device ID for multi-device setups
"""

import argparse
import os
import shutil
import subprocess
import sys
from typing import Any

from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.cli import add_model_arguments, resolve_model_config
from phone_agent.agent_ios import IOSAgentConfig, IOSPhoneAgent
from phone_agent.config.apps import list_supported_apps
from phone_agent.config.apps_harmonyos import list_supported_apps as list_harmonyos_apps
from phone_agent.config.apps_ios import list_supported_apps as list_ios_apps
from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type
from phone_agent.model import ModelClient
from phone_agent.xctest import XCTestConnection
from phone_agent.xctest import list_devices as list_ios_devices


def check_system_requirements(
    device_type: DeviceType = DeviceType.ADB,
    device_id: str | None = None,
    wda_url: str = "http://localhost:8100",
) -> bool:
    """
    Check system requirements before running the agent.

    Checks:
    1. ADB/HDC/iOS tools installed
    2. At least one device connected
    3. ADB Keyboard installed on the device (for ADB only)
    4. WebDriverAgent running (for iOS only)

    Args:
        device_type: Type of device tool (ADB, HDC, or IOS).
        wda_url: WebDriverAgent URL (for iOS only).

    Returns:
        True if all checks pass, False otherwise.
    """
    print("🔍 Checking system requirements...")
    print("-" * 50)

    all_passed = True

    # Determine tool name and command
    if device_type == DeviceType.IOS:
        tool_name = "libimobiledevice"
        tool_cmd = "idevice_id"
    else:
        tool_name = "ADB" if device_type == DeviceType.ADB else "HDC"
        tool_cmd = "adb" if device_type == DeviceType.ADB else "hdc"

    # Check 1: Tool installed
    print(f"1. Checking {tool_name} installation...", end=" ")
    if shutil.which(tool_cmd) is None:
        print("❌ FAILED")
        print(f"   Error: {tool_name} is not installed or not in PATH.")
        print(f"   Solution: Install {tool_name}:")
        if device_type == DeviceType.ADB:
            print("     - macOS: brew install android-platform-tools")
            print("     - Linux: sudo apt install android-tools-adb")
            print(
                "     - Windows: Download from https://developer.android.com/studio/releases/platform-tools"
            )
        elif device_type == DeviceType.HDC:
            print(
                "     - Download from HarmonyOS SDK or https://gitee.com/openharmony/docs"
            )
            print("     - Add to PATH environment variable")
        else:  # IOS
            print("     - macOS: brew install libimobiledevice")
            print("     - Linux: sudo apt-get install libimobiledevice-utils")
        all_passed = False
    else:
        # Double check by running version command
        try:
            if device_type == DeviceType.ADB:
                version_cmd = [tool_cmd, "version"]
            elif device_type == DeviceType.HDC:
                version_cmd = [tool_cmd, "-v"]
            else:  # IOS
                version_cmd = [tool_cmd, "-ln"]

            result = subprocess.run(
                version_cmd, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version_line = result.stdout.strip().split("\n")[0]
                print(f"✅ OK ({version_line if version_line else 'installed'})")
            else:
                print("❌ FAILED")
                print(f"   Error: {tool_name} command failed to run.")
                all_passed = False
        except FileNotFoundError:
            print("❌ FAILED")
            print(f"   Error: {tool_name} command not found.")
            all_passed = False
        except subprocess.TimeoutExpired:
            print("❌ FAILED")
            print(f"   Error: {tool_name} command timed out.")
            all_passed = False

    # If ADB is not installed, skip remaining checks
    if not all_passed:
        print("-" * 50)
        print("❌ System check failed. Please fix the issues above.")
        return False

    # Check 2: Device connected
    print("2. Checking connected devices...", end=" ")
    device_ids: list[str] = []
    try:
        if device_type == DeviceType.ADB:
            result = subprocess.run(
                ["adb", "devices"], capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split("\n")
            # Filter out header and empty lines, look for 'device' status
            devices = [
                line for line in lines[1:] if line.strip() and "\tdevice" in line
            ]
        elif device_type == DeviceType.HDC:
            result = subprocess.run(
                ["hdc", "list", "targets"], capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split("\n")
            devices = [line for line in lines if line.strip()]
        else:  # IOS
            ios_devices = list_ios_devices()
            devices = [d.device_id for d in ios_devices]

        if not devices:
            print("❌ FAILED")
            print("   Error: No devices connected.")
            print("   Solution:")
            if device_type == DeviceType.ADB:
                print("     1. Enable USB debugging on your Android device")
                print("     2. Connect via USB and authorize the connection")
                print(
                    "     3. Or connect remotely: python main.py --connect <ip>:<port>"
                )
            elif device_type == DeviceType.HDC:
                print("     1. Enable USB debugging on your HarmonyOS device")
                print("     2. Connect via USB and authorize the connection")
                print(
                    "     3. Or connect remotely: python main.py --device-type hdc --connect <ip>:<port>"
                )
            else:  # IOS
                print("     1. Connect your iOS device via USB")
                print("     2. Unlock device and tap 'Trust This Computer'")
                print("     3. Verify: idevice_id -l")
                print("     4. Or connect via WiFi using device IP")
            all_passed = False
        else:
            if device_type == DeviceType.ADB:
                device_ids = [d.split("\t")[0] for d in devices]
            elif device_type == DeviceType.HDC:
                device_ids = [d.strip() for d in devices]
            else:  # IOS
                device_ids = devices
            print(
                f"✅ OK ({len(devices)} device(s): {', '.join(device_ids[:2])}{'...' if len(device_ids) > 2 else ''})"
            )
    except subprocess.TimeoutExpired:
        print("❌ FAILED")
        print(f"   Error: {tool_name} command timed out.")
        all_passed = False
    except Exception as e:
        print("❌ FAILED")
        print(f"   Error: {e}")
        all_passed = False

    # If no device connected, skip ADB Keyboard check
    if not all_passed:
        print("-" * 50)
        print("❌ System check failed. Please fix the issues above.")
        return False

    # Check 3: ADB Keyboard installed (only for ADB) or WebDriverAgent (for iOS)
    if device_type == DeviceType.ADB:
        print("3. Checking ADB Keyboard...", end=" ")
        try:
            target_device = device_id or (device_ids[0] if device_ids else None)
            cmd = ["adb"]
            if target_device:
                cmd.extend(["-s", target_device])
            cmd.extend(["shell", "ime", "list", "-s"])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                print("❌ FAILED")
                error_msg = (
                    result.stderr.strip()
                    or result.stdout.strip()
                    or f"Command failed with exit code {result.returncode}"
                )
                print(f"   Error: {error_msg}")
                all_passed = False
            else:
                ime_list = result.stdout.strip()

                if "com.android.adbkeyboard/.AdbIME" in ime_list:
                    print("✅ OK")
                else:
                    print("❌ FAILED")
                    print("   Error: ADB Keyboard is not installed on the device.")
                    print("   Solution:")
                    print("     1. Download ADB Keyboard APK from:")
                    print(
                        "        https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk"
                    )
                    print("     2. Install it on your device: adb install ADBKeyboard.apk")
                    print(
                        "     3. Enable it in Settings > System > Languages & Input > Virtual Keyboard"
                    )
                    all_passed = False
        except subprocess.TimeoutExpired:
            print("❌ FAILED")
            print("   Error: ADB command timed out.")
            all_passed = False
        except Exception as e:
            print("❌ FAILED")
            print(f"   Error: {e}")
            all_passed = False
    elif device_type == DeviceType.HDC:
        # For HDC, skip keyboard check as it uses different input method
        print("3. Skipping keyboard check for HarmonyOS...", end=" ")
        print("✅ OK (using native input)")
    else:  # IOS
        # Check WebDriverAgent
        print(f"3. Checking WebDriverAgent ({wda_url})...", end=" ")
        try:
            conn = XCTestConnection(wda_url=wda_url)

            if conn.is_wda_ready():
                print("✅ OK")
                # Get WDA status for additional info
                status = conn.get_wda_status()
                if status:
                    session_id = status.get("sessionId", "N/A")
                    print(f"   Session ID: {session_id}")
            else:
                print("❌ FAILED")
                print("   Error: WebDriverAgent is not running or not accessible.")
                print("   Solution:")
                print("     1. Run WebDriverAgent on your iOS device via Xcode")
                print("     2. For USB: Set up port forwarding: iproxy 8100 8100")
                print(
                    "     3. For WiFi: Use device IP, e.g., --wda-url http://192.168.1.100:8100"
                )
                print("     4. Verify in browser: open http://localhost:8100/status")
                all_passed = False
        except Exception as e:
            print("❌ FAILED")
            print(f"   Error: {e}")
            all_passed = False

    print("-" * 50)

    if all_passed:
        print("✅ All system checks passed!\n")
    else:
        print("❌ System check failed. Please fix the issues above.")

    return all_passed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Phone Agent - AI-powered phone automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with default settings (Android)
    python main.py

    # Specify model endpoint
    python main.py --base-url http://localhost:8000/v1

    # Use API key for authentication
    python main.py --api-key YOUR_API_KEY

    # Run with specific device
    python main.py --device-id emulator-5554

    # Connect to remote device
    python main.py --connect 192.168.1.100:5555

    # List connected devices
    python main.py --list-devices

    # Enable TCP/IP on USB device and get connection info
    python main.py --enable-tcpip

    # List supported apps
    python main.py --list-apps

    # Read the accessibility tree on every step
    python main.py --accessibility on

    # iOS specific examples
    # Run with iOS device
    python main.py --device-type ios "Open Safari and search for iPhone tips"

    # Use WiFi connection for iOS
    python main.py --device-type ios --wda-url http://192.168.1.100:8100

    # List connected iOS devices
    python main.py --device-type ios --list-devices

    # Check WebDriverAgent status
    python main.py --device-type ios --wda-status

    # Pair with iOS device
    python main.py --device-type ios --pair
        """,
    )

    # Model options
    add_model_arguments(parser)

    parser.add_argument(
        "--max-steps",
        type=int,
        default=int(os.getenv("PHONE_AGENT_MAX_STEPS", "100")),
        help="Maximum steps per task",
    )

    # Device options
    parser.add_argument(
        "--device-id",
        "-d",
        type=str,
        default=os.getenv("PHONE_AGENT_DEVICE_ID"),
        help="ADB device ID",
    )

    parser.add_argument(
        "--connect",
        "-c",
        type=str,
        metavar="ADDRESS",
        help="Connect to remote device (e.g., 192.168.1.100:5555)",
    )

    parser.add_argument(
        "--disconnect",
        type=str,
        nargs="?",
        const="all",
        metavar="ADDRESS",
        help="Disconnect from remote device (or 'all' to disconnect all)",
    )

    parser.add_argument(
        "--list-devices", action="store_true", help="List connected devices and exit"
    )

    parser.add_argument(
        "--enable-tcpip",
        type=int,
        nargs="?",
        const=5555,
        metavar="PORT",
        help="Enable TCP/IP debugging on USB device (default port: 5555)",
    )

    # iOS specific options
    parser.add_argument(
        "--wda-url",
        type=str,
        default=os.getenv("PHONE_AGENT_WDA_URL", "http://localhost:8100"),
        help="WebDriverAgent URL for iOS (default: http://localhost:8100)",
    )

    parser.add_argument(
        "--pair",
        action="store_true",
        help="Pair with iOS device (required for some operations)",
    )

    parser.add_argument(
        "--wda-status",
        action="store_true",
        help="Show WebDriverAgent status and exit (iOS only)",
    )

    # Other options
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress verbose output"
    )

    parser.add_argument(
        "--list-apps", action="store_true", help="List supported apps and exit"
    )

    parser.add_argument(
        "--lang",
        type=str.lower,
        choices=["cn", "en"],
        default=os.getenv("PHONE_AGENT_LANG", "cn").lower(),
        help="Language for system prompt (cn or en, default: cn)",
    )

    parser.add_argument(
        "--device-type",
        type=str,
        choices=["adb", "hdc", "ios"],
        default=os.getenv("PHONE_AGENT_DEVICE_TYPE", "adb"),
        help="Device type: adb for Android, hdc for HarmonyOS, ios for iPhone (default: adb)",
    )

    parser.add_argument(
        "--accessibility",
        type=str.lower,
        choices=["auto", "on", "off"],
        default=os.getenv("PHONE_AGENT_ACCESSIBILITY", "auto").lower(),
        help=(
            "When to read the accessibility tree: auto (only if the screenshot "
            "is unavailable), on (every step), off (never). Default: auto"
        ),
    )

    parser.add_argument(
        "task",
        nargs="?",
        type=str,
        help="Task to execute (interactive mode if not provided)",
    )

    args = parser.parse_args(argv)
    if args.accessibility:
        args.accessibility = args.accessibility.lower()
    if args.accessibility not in {"auto", "on", "off"}:
        parser.error("--accessibility must be one of: auto, on, off")
    if args.lang:
        args.lang = args.lang.lower()
    if args.lang not in {"cn", "en"}:
        parser.error("--lang must be one of: cn, en")
    if args.device_type not in {"adb", "hdc", "ios"}:
        parser.error("--device-type must be one of: adb, hdc, ios")
    if args.device_type == "ios":
        if args.connect is not None or args.disconnect is not None or args.enable_tcpip is not None:
            parser.error("--connect, --disconnect and --enable-tcpip are not supported for iOS")
    elif args.pair or args.wda_status:
        parser.error("--pair and --wda-status are only supported for iOS")
    return args


def handle_ios_device_commands(args) -> bool:
    """
    Handle iOS device-related commands.

    Returns:
        True if a device command was handled (should exit), False otherwise.
    """
    conn = XCTestConnection(wda_url=args.wda_url)

    # Handle --list-devices
    if args.list_devices:
        devices = list_ios_devices()
        if not devices:
            print("No iOS devices connected.")
            print("\nTroubleshooting:")
            print("  1. Connect device via USB")
            print("  2. Unlock device and trust this computer")
            print("  3. Run: idevice_id -l")
        else:
            print("Connected iOS devices:")
            print("-" * 70)
            for device in devices:
                conn_type = device.connection_type.value
                model_info = f"{device.model}" if device.model else "Unknown"
                ios_info = f"iOS {device.ios_version}" if device.ios_version else ""
                name_info = device.device_name or "Unnamed"

                print(f"  ✓ {name_info}")
                print(f"    UUID: {device.device_id}")
                print(f"    Model: {model_info}")
                print(f"    OS: {ios_info}")
                print(f"    Connection: {conn_type}")
                print("-" * 70)
        return True

    # Handle --pair
    if args.pair:
        print("Pairing with iOS device...")
        success, message = conn.pair_device(args.device_id)
        print(f"{'✓' if success else '✗'} {message}")
        return True

    # Handle --wda-status
    if args.wda_status:
        print(f"Checking WebDriverAgent status at {args.wda_url}...")
        print("-" * 50)

        if conn.is_wda_ready():
            print("✓ WebDriverAgent is running")

            status = conn.get_wda_status()
            if status:
                print(f"\nStatus details:")
                value = status.get("value", {})
                print(f"  Session ID: {status.get('sessionId', 'N/A')}")
                print(f"  Build: {value.get('build', {}).get('time', 'N/A')}")

                current_app = value.get("currentApp", {})
                if current_app:
                    print(f"\nCurrent App:")
                    print(f"  Bundle ID: {current_app.get('bundleId', 'N/A')}")
                    print(f"  Process ID: {current_app.get('pid', 'N/A')}")
        else:
            print("✗ WebDriverAgent is not running")
            print("\nPlease start WebDriverAgent on your iOS device:")
            print("  1. Open WebDriverAgent.xcodeproj in Xcode")
            print("  2. Select your device")
            print("  3. Run WebDriverAgentRunner (Product > Test or Cmd+U)")
            print(f"  4. For USB: Run port forwarding: iproxy 8100 8100")

        return True

    return False


def handle_device_commands(args) -> bool:
    """
    Handle device-related commands.

    Returns:
        True if a device command was handled (should exit), False otherwise.
    """
    device_type = (
        DeviceType.ADB
        if args.device_type == "adb"
        else (DeviceType.HDC if args.device_type == "hdc" else DeviceType.IOS)
    )

    # Handle iOS-specific commands
    if device_type == DeviceType.IOS:
        return handle_ios_device_commands(args)

    device_factory = get_device_factory()
    ConnectionClass = device_factory.get_connection_class()
    conn: Any = ConnectionClass()

    # Handle --list-devices
    if args.list_devices:
        devices = device_factory.list_devices()
        if not devices:
            print("No devices connected.")
        else:
            print("Connected devices:")
            print("-" * 60)
            for device in devices:
                status_icon = "✓" if device.status == "device" else "✗"
                conn_type = device.connection_type.value
                model_info = f" ({device.model})" if device.model else ""
                print(
                    f"  {status_icon} {device.device_id:<30} [{conn_type}]{model_info}"
                )
        return True

    # Handle --connect
    if args.connect:
        print(f"Connecting to {args.connect}...")
        success, message = conn.connect(args.connect)
        print(f"{'✓' if success else '✗'} {message}")
        if success:
            # Set as default device
            args.device_id = args.connect
        return not success  # Continue if connection succeeded

    # Handle --disconnect
    if args.disconnect:
        if args.disconnect == "all":
            print("Disconnecting all remote devices...")
            success, message = conn.disconnect()
        else:
            print(f"Disconnecting from {args.disconnect}...")
            success, message = conn.disconnect(args.disconnect)
        print(f"{'✓' if success else '✗'} {message}")
        return True

    # Handle --enable-tcpip
    if args.enable_tcpip:
        port = args.enable_tcpip
        print(f"Enabling TCP/IP debugging on port {port}...")

        success, message = conn.enable_tcpip(port, args.device_id)
        print(f"{'✓' if success else '✗'} {message}")

        if success:
            # Try to get device IP
            ip = conn.get_device_ip(args.device_id)
            if ip:
                print(f"\nYou can now connect remotely using:")
                print(f"  python main.py --connect {ip}:{port}")
                print(f"\nOr via ADB directly:")
                print(f"  adb connect {ip}:{port}")
            else:
                print("\nCould not determine device IP. Check device WiFi settings.")
        return True

    return False


def main(argv: list[str] | None = None) -> None:
    """Main entry point."""
    agent = None
    model_client = None

    try:
        args = parse_args(argv)

        # Set device type globally based on args
        if args.device_type == "adb":
            device_type = DeviceType.ADB
        elif args.device_type == "hdc":
            device_type = DeviceType.HDC
        else:  # ios
            device_type = DeviceType.IOS

        # Set device type globally for non-iOS devices
        if device_type != DeviceType.IOS:
            set_device_type(device_type)

        # Enable HDC verbose mode if using HDC
        if device_type == DeviceType.HDC:
            from phone_agent.hdc import set_hdc_verbose

            set_hdc_verbose(not args.quiet)

        # Handle --list-apps (no system check needed)
        if args.list_apps:
            if device_type == DeviceType.HDC:
                print("Supported HarmonyOS apps:")
                apps = list_harmonyos_apps()
            elif device_type == DeviceType.IOS:
                print("Supported iOS apps:")
                print("\nNote: For iOS apps, Bundle IDs are configured in:")
                print("  phone_agent/config/apps_ios.py")
                print("\nCurrently configured apps:")
                apps = list_ios_apps()
            else:
                print("Supported Android apps:")
                apps = list_supported_apps()

            for app in sorted(apps):
                print(f"  - {app}")

            if device_type == DeviceType.IOS:
                print(
                    "\nTo add iOS apps, find the Bundle ID and add to APP_PACKAGES_IOS dictionary."
                )
            return

        # Handle device commands (these may need partial system checks)
        if handle_device_commands(args):
            return

        # Validate model configuration before accessing devices.
        model_config = resolve_model_config(args, lang=args.lang)

        # Run system requirements check before proceeding
        if not check_system_requirements(
            device_type,
            device_id=args.device_id,
            wda_url=(
                args.wda_url
                if device_type == DeviceType.IOS
                else "http://localhost:8100"
            ),
        ):
            sys.exit(1)

        model_client = ModelClient(model_config, verbose=not args.quiet)
        model_client.check_connection()

        # Create configurations and agent based on device type
        if device_type == DeviceType.IOS:
            agent_config = IOSAgentConfig(
                max_steps=args.max_steps,
                wda_url=args.wda_url,
                device_id=args.device_id,
                verbose=not args.quiet,
                lang=args.lang,
                accessibility=args.accessibility,
            )
            agent = IOSPhoneAgent(
                model_config=model_config,
                agent_config=agent_config,
                model_client=model_client,
            )
        else:
            target_device_id = args.device_id
            if not target_device_id:
                device_factory = get_device_factory()
                devices = device_factory.list_devices()
                if devices:
                    target_device_id = devices[0].device_id

            agent_config = AgentConfig(
                max_steps=args.max_steps,
                device_id=target_device_id,
                device_type=device_type,
                verbose=not args.quiet,
                lang=args.lang,
                accessibility=args.accessibility,
            )
            agent = PhoneAgent(
                model_config=model_config,
                agent_config=agent_config,
                model_client=model_client,
            )

        # Print header
        print("=" * 50)
        if device_type == DeviceType.IOS:
            print("Phone Agent iOS - AI-powered iOS automation")
        else:
            print("Phone Agent - AI-powered phone automation")
        print("=" * 50)
        print(f"Provider: {model_config.provider}")
        print(f"Tool Mode: {model_config.tool_mode}")
        print(f"Model: {model_config.model_name}")
        print(f"Base URL: {model_config.base_url}")
        print(f"Max Steps: {agent_config.max_steps}")
        print(f"Language: {agent_config.lang}")
        print(f"Accessibility: {agent_config.accessibility}")
        print(f"Device Type: {args.device_type.upper()}")

        # Show iOS-specific config
        if device_type == DeviceType.IOS:
            print(f"WDA URL: {args.wda_url}")

        # Show device info
        if device_type == DeviceType.IOS:
            devices = list_ios_devices()
            if agent_config.device_id:
                print(f"Device: {agent_config.device_id}")
            elif devices:
                device = devices[0]
                print(f"Device: {device.device_name or device.device_id[:16]}")
                if device.model and device.ios_version:
                    print(f"        {device.model}, iOS {device.ios_version}")
        else:
            device_factory = get_device_factory()
            devices = device_factory.list_devices()
            if agent_config.device_id:
                print(f"Device: {agent_config.device_id}")
            elif devices:
                print(f"Device: {devices[0].device_id} (auto-detected)")

        print("=" * 50)

        # Run with provided task or enter interactive mode
        if args.task:
            print(f"\nTask: {args.task}\n")
            result = agent.run(args.task)
            print(f"\nResult: {result}")
        else:
            print("\nEntering interactive mode. Type 'quit' to exit.\n")

            while True:
                try:
                    task = input("Enter your task: ").strip()

                    if task.lower() in ("quit", "exit", "q"):
                        print("Goodbye!")
                        break

                    if not task:
                        continue

                    print()
                    result = agent.run(task)
                    print(f"\nResult: {result}\n")
                    agent.reset()

                except EOFError:
                    print("\nGoodbye!")
                    break
                except KeyboardInterrupt:
                    print("\n\nInterrupted. Goodbye!")
                    break
                except Exception as e:
                    print(f"\nError: {e}\n")
                    raise
    except KeyboardInterrupt:
        print("\n\nInterrupted. Goodbye!")
        raise
    finally:
        try:
            if agent is not None:
                agent.close()
        finally:
            if model_client is not None:
                model_client.close()


if __name__ == "__main__":
    main()
