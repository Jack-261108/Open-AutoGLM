# Open-AutoGLM

[中文阅读.](./README.md)

<div align="center">
<img src=resources/logo.svg width="20%"/>
</div>
<p align="center">
    👋 Join our<a href="resources/WECHAT.md" target="_blank"> Wechat</a> community
</p>
<p align="center">
    👋 Follow AutoGLM Autotyper <a href="https://x.com/Autotyper_Agent?s=20" target="_blank">X</a> account
</p>

## Quick Start

You can use Claude Code with [GLM Coding Plan](https://z.ai/subscribe) and enter the following prompt to quickly deploy this project:

```
Access the documentation and install AutoGLM for me
https://raw.githubusercontent.com/zai-org/Open-AutoGLM/refs/heads/main/README_en.md
```

## Project Introduction

Phone Agent is a mobile intelligent assistant framework built on AutoGLM. It understands phone screen content in a multimodal manner and helps users complete tasks through automated operations. The system controls devices via ADB (Android Debug Bridge), perceives screens using vision-language models, and generates and executes operation workflows through intelligent planning. Users simply describe their needs in natural language, such as "Open eBay and search for wireless earphones." and Phone Agent will automatically parse the intent, understand the current interface, plan the next action, and complete the entire workflow. The system also includes a sensitive operation confirmation mechanism and supports manual takeover during login or verification code scenarios. Additionally, it provides remote ADB debugging capabilities, allowing device connection via WiFi or network for flexible remote control and development.

> ⚠️ This project is for research and learning purposes only. It is strictly prohibited to use for illegal information acquisition, system interference, or any illegal activities. Please carefully review the [Terms of Use](resources/privacy_policy_en.txt).

## Integration with Other Automation Tools

### Midscene.js

[Midscene.js](https://midscenejs.com/en/index.html) is an open-source, vision-model-driven UI automation SDK that supports JavaScript or YAML flow syntax for cross-platform automation.

Midscene.js already supports AutoGLM; see the [Midscene.js integration guide](https://midscenejs.com/model-common-config.html#auto-glm) to quickly try AutoGLM automation on both iOS and Android devices.

### Claude Code (MCP Server)

This project ships an MCP server that exposes Android screenshot and control capabilities to MCP clients such as Claude Code. Claude's vision and reasoning "watch the screen and decide", while this project "executes the actions" — step by step completing intelligent tasks like playing board games (e.g. military chess) or filling forms.

**Prerequisites** (no model deployment needed):

1. adb installed with an Android device connected (see [Environment Setup](#environment-setup) below)
2. This project installed: `pip install -e .` (brings in the `mcp` dependency)
3. ADB Keyboard recommended (only needed by the `type_text` tool)

**Register with Claude Code**:

```bash
claude mcp add phone-agent -- phone-agent mcp

# Pick a specific device (when several are connected)
claude mcp add phone-agent -- phone-agent mcp --device-id <adb-device-id>

# Remote / Network service mode (for device farms / cloud devices, endpoint /mcp)
phone-agent mcp --listen 0.0.0.0:8000
```

Then check the connection with `/mcp` inside Claude Code and simply give it a task.

**Tool overview** (coordinates are pixels, origin at the top-left of the screenshot; scaled coordinates are mapped back automatically):

| Tool | Parameters | Description |
|------|------------|-------------|
| `screenshot` | max_dimension?, quality=80 | Capture the screen (image + resolution + current app). For fast games, pass `max_dimension=1080` or `800` to downscale and compress to JPEG, saving up to 90% transfer size and 60% visual tokens |
| `get_current_app` | - | Focused app (name + package) |
| `tap` | x, y | Tap |
| `double_tap` | x, y | Double tap |
| `long_press` | x, y, duration_ms=1000 | Long press |
| `swipe` | start_x, start_y, end_x, end_y, duration_ms? | Swipe (duration auto-calculated when omitted) |
| `move_piece` | from_x, from_y, to_x, to_y, interval_ms=300 | Board game move: taps start then target in a single turn, eliminating a roundtrip |
| `type_text` | text, clear=False | Type text (needs ADB Keyboard; clear=True empties the field first) |
| `get_clipboard` | - | Get current text from system clipboard |
| `set_clipboard` | text | Set text into system clipboard (ideal for pasting long text, tokens, or URLs) |
| `batch_actions` | actions | General action batching: execute a list of sequential actions (e.g. tap, wait, type) in one turn to reduce LLM roundtrips |
| `back` / `home` | - | Back / Home key |
| `launch_app` | app | Launch by built-in name (e.g. "微信") or package name (e.g. `com.tencent.mm`) |
| `force_stop_app` | app | Force stop an app by name or package (e.g. to recover from crashes) |
| `clear_app_data` | app | Clear all data and cache for an app (resets to initial state for testing) |
| `install_app` | path | Install a local APK file onto the device (`-r` reinstall) |
| `get_orientation` | - | Get current screen orientation and rotation status (portrait/landscape, rotation code) |
| `set_orientation` | orientation | Set or lock screen orientation ("portrait", "landscape", or "auto") |
| `wait` | seconds=1.0 | Wait for the screen to change (0.1–30 s) |

**Example: playing military chess**

> Use the phone-agent MCP tools to play military chess on my phone: launch the game with `launch_app` (use its package name — `adb shell pm list packages` — if not in the built-in list). Each round, first call `screenshot(max_dimension=1080)` to inspect the board, reason about the game, then use `move_piece` to make a move (or `tap` to flip a piece); while waiting for the opponent, `wait` 2 seconds and screenshot again. When unsure, describe the board before acting.

**Speed Optimization Tips for Time-Constrained Scenarios**:

- **General Action Batching**: Use `batch_actions` to execute multiple deterministic steps in sequence (e.g. tapping an input field then typing text) in a single turn, eliminating unnecessary screenshot-reasoning roundtrips.
- **Single-turn moves**: Use `move_piece(from_x, from_y, to_x, to_y)` instead of two individual `tap` calls. Both selection and placement happen in one model turn.
- **Lower image size**: Set `export PHONE_AGENT_SCREENSHOT_MAX_DIM=1080` in your environment or call `screenshot(max_dimension=1080)`. Transfer size drops from 2MB to 80KB and visual tokens drop by ~60%, drastically cutting inference latency while coordinates map back to device pixels automatically.

**FAQ**:

- The on-device keyboard switches to ADB Keyboard during the session; the original keyboard is restored as soon as possible
- When a black image is returned, read the accompanying warning: payment and other sensitive screens block screenshots; a disconnected device also yields a black image and recovers automatically once reconnected
- If an action seems to have no effect, take another screenshot to confirm

## Model Download Links

| Model             | Download Links                                                                                                                                             |
|-------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------|
| AutoGLM-Phone-9B  | [🤗 Hugging Face](https://huggingface.co/zai-org/AutoGLM-Phone-9B)<br>[🤖 ModelScope](https://modelscope.cn/models/ZhipuAI/AutoGLM-Phone-9B)               |
| AutoGLM-Phone-9B-Multilingual | [🤗 Hugging Face](https://huggingface.co/zai-org/AutoGLM-Phone-9B-Multilingual)<br>[🤖 ModelScope](https://modelscope.cn/models/ZhipuAI/AutoGLM-Phone-9B-Multilingual) |

`AutoGLM-Phone-9B` is optimized for Chinese mobile applications, while `AutoGLM-Phone-9B-Multilingual` supports English scenarios and is suitable for applications containing English or other language content.

## Environment Setup

### 1. Python Environment

Python 3.10 or higher is recommended.

### 2. Device Debug Tools

Choose the appropriate tool based on your device type:

#### For Android Devices - Using ADB

1. Download the official ADB [installation package](https://developer.android.com/tools/releases/platform-tools) and extract it to a custom path
2. Configure environment variables

- MacOS configuration: In `Terminal` or any command line tool

  ```bash
  # Assuming the extracted directory is ~/Downloads/platform-tools. Adjust the command if different.
  export PATH=${PATH}:~/Downloads/platform-tools
  ```

- Windows configuration: Refer to [third-party tutorials](https://blog.csdn.net/x2584179909/article/details/108319973) for configuration.

#### For HarmonyOS Devices - Using HDC

1. Download HDC tool:
   - From [HarmonyOS SDK](https://developer.huawei.com/consumer/en/download/)
2. Configure environment variables

- MacOS/Linux configuration:

  ```bash
  # Assuming the extracted directory is ~/Downloads/harmonyos-sdk/toolchains. Adjust according to actual path.
  export PATH=${PATH}:~/Downloads/harmonyos-sdk/toolchains
  ```

- Windows configuration: Add the HDC tool directory to the system PATH environment variable

### 3. Android 7.0+ or HarmonyOS Device with `Developer Mode` and `USB Debugging` Enabled

1. Enable Developer Mode: The typical method is to find `Settings > About Phone > Build Number` and tap it rapidly about 10 times until a popup shows "Developer mode has been enabled." This may vary slightly between phones; search online for tutorials if you can't find it.
2. Enable USB Debugging: After enabling Developer Mode, go to `Settings > Developer Options > USB Debugging` and enable it
3. Some devices may require a restart after setting developer options for them to take effect. You can test by connecting your phone to your computer via USB cable and running `adb devices` to see if device information appears. If not, the connection has failed.

**Please carefully check the relevant permissions**

![Permissions](resources/screenshot-20251210-120416.png)

### 4. Install ADB Keyboard (Required for Android Devices Only, for Text Input)

**Note: HarmonyOS devices use native input methods and do not require ADB Keyboard.**

If you are using an Android device:

Download the [installation package](https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk) and install it on the corresponding Android device.
Note: After installation, you need to enable `ADB Keyboard` in `Settings > Input Method` or `Settings > Keyboard List` for it to work.(or use command `adb shell ime enable com.android.adbkeyboard/.AdbIME`[How-to-use](https://github.com/senzhk/ADBKeyBoard/blob/master/README.md#how-to-use))

## Deployment Preparation

### 1. Install Dependencies

```bash
pip install -r requirements.txt 
pip install -e .
```

### 2. Configure ADB or HDC

#### For Android Devices

Make sure your **USB cable supports data transfer**, not just charging.

Ensure ADB is installed and connect the device via **USB cable**:

```bash
# Check connected devices
adb devices

# Output should show your device, e.g.:
# List of devices attached
# emulator-5554   device
```

#### For HarmonyOS Devices

Make sure your **USB cable supports data transfer**, not just charging.

Ensure HDC is installed and connect the device via **USB cable**:

```bash
# Check connected devices
hdc list targets

# Output should show your device, e.g.:
# 7001005458323933328a01bce01c2500
```

### 3. Start Model Service

You can choose to deploy the model service yourself or use a third-party model service provider.

#### Option A: Use Third-Party Model Services

If you don't want to deploy the model yourself, you can use the following third-party services that have already deployed our model:

**1. z.ai**

- Documentation: https://docs.z.ai/api-reference/introduction
- `--base-url`: `https://api.z.ai/api/paas/v4`
- `--model`: `autoglm-phone-multilingual`
- `--apikey`: Apply for your own API key on the z.ai platform

**2. Novita AI**

- Documentation: https://novita.ai/models/model-detail/zai-org-autoglm-phone-9b-multilingual
- `--base-url`: `https://api.novita.ai/openai`
- `--model`: `zai-org/autoglm-phone-9b-multilingual`
- `--apikey`: Apply for your own API key on the Novita AI platform

**3. Parasail**

- Documentation: https://www.saas.parasail.io/serverless?name=auto-glm-9b-multilingual
- `--base-url`: `https://api.parasail.io/v1`
- `--model`: `parasail-auto-glm-9b-multilingual`
- `--apikey`: Apply for your own API key on the Parasail platform

Example usage with third-party services:

```bash
# Using z.ai
python main.py --base-url https://api.z.ai/api/paas/v4 --model "autoglm-phone-multilingual" --apikey "your-z-ai-api-key" "Open Chrome browser"

# Using Novita AI
python main.py --base-url https://api.novita.ai/openai --model "zai-org/autoglm-phone-9b-multilingual" --apikey "your-novita-api-key" "Open Chrome browser"

# Using Parasail
python main.py --base-url https://api.parasail.io/v1 --model "parasail-auto-glm-9b-multilingual" --apikey "your-parasail-api-key" "Open Chrome browser"
```

> 💡 All third-party services above implement the OpenAI Chat Completions compatible protocol, so the default `--provider openai` works out of the box. Any OpenAI-compatible service (DashScope, custom vLLM/SGLang, etc.) can be wired up the same way. For other protocols (Anthropic Messages, Ollama), see the [Multi-Model Providers](#multi-model-providers) section below.

#### Option B: Deploy Model Yourself

If you prefer to deploy the model locally or on your own server:

1. Download the model and install the inference engine framework according to the `For Model Deployment` section in `requirements.txt`.
2. Start via SGlang / vLLM to get an OpenAI-format service. Here's a vLLM deployment solution; please strictly follow the startup parameters we provide:

- vLLM:

```shell
python3 -m vllm.entrypoints.openai.api_server \
 --served-model-name autoglm-phone-9b-multilingual \
 --allowed-local-media-path /   \
 --mm-encoder-tp-mode data \
 --mm_processor_cache_type shm \
 --mm_processor_kwargs "{\"max_pixels\":5000000}" \
 --max-model-len 25480  \
 --chat-template-content-format string \
 --limit-mm-per-prompt "{\"image\":10}" \
 --model zai-org/AutoGLM-Phone-9B-Multilingual \
 --port 8000
```

- This model has the same architecture as `GLM-4.1V-9B-Thinking`. For detailed information about model deployment, you can also check [GLM-V](https://github.com/zai-org/GLM-V) for model deployment and usage guides.

- After successful startup, the model service will be accessible at `http://localhost:8000/v1`. If you deploy the model on a remote server, access it using that server's IP address.

### 4. Check Model Deployment

After starting the model service, you can use the following command to verify the deployment:

```bash
python scripts/check_deployment_en.py --base-url http://localhost:8000/v1 --model autoglm-phone-9b-multilingual
```

If using a third-party model service:

```bash
# Novita AI
python scripts/check_deployment_en.py --base-url https://api.novita.ai/openai --model zai-org/autoglm-phone-9b-multilingual --apikey your-novita-api-key

# Parasail
python scripts/check_deployment_en.py --base-url https://api.parasail.io/v1 --model parasail-auto-glm-9b-multilingual --apikey your-parasail-api-key
```

Upon successful execution, the script will display the model's inference result and token statistics, helping you confirm whether the model deployment is working correctly.

## Using AutoGLM

### Command Line

Set the `--base-url` and `--model` parameters according to your deployed model. For example:

```bash
# Android device - Interactive mode
python main.py --base-url http://localhost:8000/v1 --model "autoglm-phone-9b-multilingual"

# Android device - Specify task
python main.py --base-url http://localhost:8000/v1 "Open Maps and search for nearby coffee shops"

# HarmonyOS device - Interactive mode
python main.py --device-type hdc --base-url http://localhost:8000/v1 --model "autoglm-phone-9b-multilingual"

# HarmonyOS device - Specify task
python main.py --device-type hdc --base-url http://localhost:8000/v1 "Open Maps and search for nearby coffee shops"

# Use API key for authentication
python main.py --apikey sk-xxxxx

# Use English system prompt
python main.py --lang en --base-url http://localhost:8000/v1 "Open Chrome browser"

# List supported apps (Android)
python main.py --list-apps

# List supported apps (HarmonyOS)
python main.py --device-type hdc --list-apps
```

#### iOS Devices

iOS devices can be driven either through `main.py` with `--device-type ios`, or via the dedicated `ios.py` entry point:

```bash
# iOS device - specify a task
python ios.py --base-url http://localhost:8000/v1 --model "autoglm-phone-9b-multilingual" "Open Safari and search for iPhone tips"

# iOS device - custom WebDriverAgent URL (WiFi debugging)
python ios.py --wda-url http://192.168.1.100:8100

# List connected iOS devices
python ios.py --list-devices

# Show WebDriverAgent status
python ios.py --wda-status
```

For iOS environment setup, see the [iOS Setup Guide](docs/ios_setup/ios_setup.md).

### Python API

```python
from phone_agent import PhoneAgent
from phone_agent.model import ModelConfig

# Configure model
model_config = ModelConfig(
    base_url="http://localhost:8000/v1",
    model_name="autoglm-phone-9b-multilingual",
)

# Create Agent
agent = PhoneAgent(model_config=model_config)

try:
    # Execute task
    result = agent.run("Open eBay and search for wireless earphones")
    print(result)
finally:
    # Explicitly release the model client and device handles
    agent.close()
```

> ⚠️ `PhoneAgent` owns the model client and device handles internally. Wrap usage in `try/finally` and call `agent.close()` to avoid leaking connections on long-running or error paths. If you inject a custom client via `model_client=`, `agent.close()` will NOT close it — the caller is responsible for it.

## Multi-Model Providers

Besides the default `openai` (OpenAI Chat Completions compatible) protocol, this project supports two additional provider protocols. Switch explicitly with `--provider`; the project never guesses the protocol from URL or model name.

| provider | Protocol | Use case |
|---|---|---|
| `openai` (default) | OpenAI Chat Completions | AutoGLM family, z.ai, ModelScope, DashScope gui-plus, local vLLM/SGLang, any OpenAI-compatible service |
| `anthropic` | Anthropic Messages | Official Anthropic API and proxies that strictly implement the Messages protocol |
| `ollama` | Ollama `/api/chat` | Local Ollama models (must support vision) |

### CLI Usage

```bash
# Using Anthropic
python main.py \
  --provider anthropic \
  --base-url https://api.anthropic.com \
  --model "claude-sonnet-4-6" \
  --api-key "$ANTHROPIC_API_KEY" \
  "Open Chrome and search for Python tutorials"

# Using local Ollama
python main.py \
  --provider ollama \
  --base-url http://localhost:11434 \
  --model "llama3.2-vision" \
  "Open Maps and search for nearby coffee shops"
```

All entry points (`main.py` and `ios.py`) support the following arguments and environment variables, with precedence **CLI > env vars > provider defaults**:

| Argument | Environment variable | Description |
|---|---|---|
| `--provider` | `PHONE_AGENT_PROVIDER` | Provider: `openai` / `anthropic` / `ollama` |
| `--tool-mode` | `PHONE_AGENT_TOOL_MODE` | Tool calling mode: `auto` / `native` / `text` |
| `--base-url` | `PHONE_AGENT_BASE_URL` | Provider service URL (defaults differ per provider) |
| `--model` | `PHONE_AGENT_MODEL` | Model name |
| `--api-key` | `PHONE_AGENT_API_KEY` | API key (backwards-compatible alias `--apikey`; passing both raises a conflict) |

### Tool Calling Modes (`tool_mode`)

| Mode | Behavior |
|---|---|
| `auto` (default) | Sends native tool definitions first. If the server rejects `tools` with a 400/422 error whose error field points exactly at `tools`/`tool_choice` before any content has been streamed, retries once without tools. If the server accepts tools but the model returns text, no retry — parse as hybrid text. |
| `native` | Always sends native tool definitions; fails immediately if the server rejects them. |
| `text` | Never sends native tool definitions. Only uses prompt + text DSL (`do(...)` / `finish(...)`), XML, or JSON output. |

`auto` or `native` is recommended for general cloud models. Use `text` for local models with unstable formatting.

### Python API Example

```python
import os
from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig, ModelClient

# Anthropic example
anthropic_config = ModelConfig(
    provider="anthropic",
    model_name="claude-sonnet-4-6",
    api_key=os.environ["ANTHROPIC_API_KEY"],
    tool_mode="auto",
)

# Ollama example (localhost is the host running this Python process, not the phone)
ollama_config = ModelConfig(
    provider="ollama",
    model_name="llama3.2-vision",
    base_url="http://localhost:11434",
    tool_mode="auto",
)

# Inject a ModelClient for custom transport or testing
agent = PhoneAgent(
    model_config=anthropic_config,
    agent_config=AgentConfig(lang="en"),
    model_client=ModelClient(anthropic_config, verbose=True),
)
try:
    agent.run("Open Chrome and visit github.com")
finally:
    agent.close()
```

### Key Constraints

- **Models from all providers must support image input** so screenshots can reach the model. If the server explicitly rejects images, the error is surfaced as a readable message rather than silently degrading to text.
- `--base-url` must be an absolute http/https URL with no embedded credentials; trailing slashes are stripped automatically.
- `openai` allows an empty API key (`"EMPTY"` or omitted — whether a key is required depends on the server); `anthropic` requires a non-empty key other than `"EMPTY"`; `ollama` does not accept an API key — use `extra_headers` for proxy authentication.
- `frequency_penalty` is only supported by `openai`. For `anthropic` and `ollama`, `None` or `0.0` are treated as "not set"; any other value raises a configuration error.
- `extra_body` cannot override reserved fields such as `model`/`messages`/`tools`/`tool_choice`/`stream`. Ollama's `extra_body.options` cannot override `num_predict`/`temperature`/`top_p` generated from `ModelConfig` fields.
- API keys are only taken from CLI, environment variables, or caller code. They are masked in logs and exceptions — never persist them in command history or long-lived files.

### Dependencies

The project pins the following lower bounds, shared across all three provider adapters:

| Dependency | Lower bound | Used by |
|---|---|---|
| `openai` | `>=2.9.0` | OpenAI-compatible adapter |
| `anthropic` | `>=0.117.1` | Anthropic Messages adapter (raw streaming event interface) |
| `httpx` | `>=0.28.1` | Direct Ollama native protocol calls |



## Remote Debugging

Phone Agent supports remote ADB/HDC debugging via WiFi/network, allowing device control without a USB connection.

### Configure Remote Debugging

#### Enable Wireless Debugging on Phone

##### Android Devices

Ensure the phone and computer are on the same WiFi network, as shown below:

![Enable Wireless Debugging](resources/screenshot-20251210-120630.png)

##### HarmonyOS Devices

Ensure the phone and computer are on the same WiFi network:
1. Go to `Settings > System & Updates > Developer Options`
2. Enable `USB Debugging` and `Wireless Debugging`
3. Note the displayed IP address and port number

#### Use Standard ADB/HDC Commands on Computer

```bash
# Android device - Connect via WiFi, replace with the IP address and port shown on your phone
adb connect 192.168.1.100:5555

# Verify connection
adb devices
# Should show: 192.168.1.100:5555    device

# HarmonyOS device - Connect via WiFi
hdc tconn 192.168.1.100:5555

# Verify connection
hdc list targets
# Should show: 192.168.1.100:5555
```

### Device Management Commands

#### Android Devices (ADB)

```bash
# List all connected devices
adb devices

# Connect to remote device
adb connect 192.168.1.100:5555

# Disconnect specific device
adb disconnect 192.168.1.100:5555

# Execute task on specific device
python main.py --device-id 192.168.1.100:5555 --base-url http://localhost:8000/v1 --model "autoglm-phone-9b-multilingual" "Open TikTok and browse videos"
```

#### HarmonyOS Devices (HDC)

```bash
# List all connected devices
hdc list targets

# Connect to remote device
hdc tconn 192.168.1.100:5555

# Disconnect specific device
hdc tdisconn 192.168.1.100:5555

# Execute task on specific device
python main.py --device-type hdc --device-id 192.168.1.100:5555 --base-url http://localhost:8000/v1 --model "autoglm-phone-9b-multilingual" "Open TikTok and browse videos"
```

### Python API Remote Connection

#### Android Devices (ADB)

```python
from phone_agent.adb import ADBConnection, list_devices

# Create connection manager
conn = ADBConnection()

# Connect to remote device
success, message = conn.connect("192.168.1.100:5555")
print(f"Connection status: {message}")

# List connected devices
devices = list_devices()
for device in devices:
    print(f"{device.device_id} - {device.connection_type.value}")

# Enable TCP/IP on USB device
success, message = conn.enable_tcpip(5555)
ip = conn.get_device_ip()
print(f"Device IP: {ip}")

# Disconnect
conn.disconnect("192.168.1.100:5555")
```

#### HarmonyOS Devices (HDC)

```python
from phone_agent.hdc import HDCConnection, list_devices

# Create connection manager
conn = HDCConnection()

# Connect to remote device
success, message = conn.connect("192.168.1.100:5555")
print(f"Connection status: {message}")

# List connected devices
devices = list_devices()
for device in devices:
    print(f"{device.device_id} - {device.connection_type.value}")

# Disconnect
conn.disconnect("192.168.1.100:5555")
```

### Remote Connection Troubleshooting

**Connection Refused:**

- Ensure the device and computer are on the same network
- Check if the firewall is blocking port 5555
- Confirm TCP/IP mode is enabled: `adb tcpip 5555`

**Connection Dropped:**

- WiFi may have disconnected; use `--connect` to reconnect
- Some devices disable TCP/IP after restart; re-enable via USB

**Multiple Devices:**

- Use `--device-id` to specify which device to use
- Or use `--list-devices` to view all connected devices

## Configuration

### Custom SYSTEM PROMPT

The system provides both Chinese and English prompts, switchable via the `--lang` parameter:

- `--lang cn` - Chinese prompt (default), config file: `phone_agent/config/prompts_zh.py`
- `--lang en` - English prompt, config file: `phone_agent/config/prompts_en.py`

You can directly modify the corresponding config files to enhance model capabilities in specific domains or disable certain apps by injecting app names.

### Environment Variables

| Variable                    | Description               | Default Value              |
|-----------------------------|---------------------------|----------------------------|
| `PHONE_AGENT_PROVIDER`       | Model provider (`openai` / `anthropic` / `ollama`) | `openai` |
| `PHONE_AGENT_TOOL_MODE`     | Tool calling mode (`auto` / `native` / `text`) | `auto` |
| `PHONE_AGENT_BASE_URL`      | Model API URL (defaults differ per provider) | See [Multi-Model Providers](#multi-model-providers) |
| `PHONE_AGENT_MODEL`         | Model name                | `autoglm-phone-9b` (only `openai`) |
| `PHONE_AGENT_API_KEY`       | API key for authentication| `EMPTY`                    |
| `PHONE_AGENT_MAX_STEPS`     | Maximum steps per task    | `100`                      |
| `PHONE_AGENT_DEVICE_ID`     | ADB/HDC/iOS device ID     | (auto-detect)              |
| `PHONE_AGENT_DEVICE_TYPE`   | Device type (`adb` / `hdc` / `ios`)| `adb`                    |
| `PHONE_AGENT_LANG`          | Language (`cn` or `en`)   | `en`                       |
| `PHONE_AGENT_WDA_URL`       | WebDriverAgent URL (iOS only) | `http://localhost:8100` |

> Precedence: **CLI arguments > environment variables > provider defaults**.

### Model Configuration

```python
from phone_agent.model import ModelConfig

config = ModelConfig(
    base_url="http://localhost:8000/v1",
    api_key="EMPTY",  # API key (if required)
    model_name="autoglm-phone-9b-multilingual",  # Model name
    max_tokens=2048,  # Maximum output tokens
    temperature=0.1,  # Sampling temperature; None maps to the OpenAI-path effective default (0.0 for openai/anthropic/ollama)
    top_p=0.85,  # Nucleus sampling probability; None uses 0.85 for openai/ollama, anthropic omits the field
    frequency_penalty=0.2,  # Frequency penalty; only sent by openai (None uses 0.2), anthropic/ollama treat as unset
    extra_body={},  # Extra fields appended to the request body
    lang="en",  # UI prompt language
    provider="openai",  # openai / anthropic / ollama
    tool_mode="auto",  # auto / native / text
    timeout=120.0,  # Per-request timeout in seconds
    extra_headers=None,  # Custom headers (e.g. proxy auth); masked in logs
)
```

Default `base_url` per provider:

| provider | Default `base_url` | Notes |
|---|---|---|
| `openai` | `http://localhost:8000/v1` | SDK appends resource paths |
| `anthropic` | `https://api.anthropic.com` | SDK handles Messages path |
| `ollama` | `http://localhost:11434` | Adapter appends `/api/chat`, `/api/tags` |

### Agent Configuration

```python
from phone_agent.agent import AgentConfig  # Android/HarmonyOS
from phone_agent.agent_ios import IOSAgentConfig  # iOS

config = AgentConfig(
    max_steps=100,  # Maximum steps per task
    device_id=None,  # ADB/HDC device ID (None for auto-detect)
    lang="en",  # Language: cn (Chinese) or en (English)
    system_prompt=None,  # Custom system prompt (None = read default by lang)
    verbose=True,  # Print debug info (including thinking process and actions)
)

# iOS-specific fields
ios_config = IOSAgentConfig(
    max_steps=100,
    wda_url="http://localhost:8100",  # WebDriverAgent URL
    device_id=None,  # iOS UDID
    lang="en",
    verbose=True,
)
```

### Injecting a Model Client

For testing or custom transports, construct a `ModelClient` and inject it into the Agent:

```python
from phone_agent import PhoneAgent
from phone_agent.model import ModelClient, ModelConfig

model_config = ModelConfig(provider="openai")
model_client = ModelClient(model_config, verbose=True)
model_client.check_connection()  # Explicit pre-flight check

agent = PhoneAgent(model_config=model_config, model_client=model_client)
try:
    agent.run("Open WeChat")
finally:
    agent.close()         # Does NOT close the injected model_client
    model_client.close()  # Caller owns the injected client
```

Without `model_client=` injected, `PhoneAgent` creates and owns a `ModelClient` internally, and `agent.close()` closes it for you.

### Verbose Mode Output

When `verbose=True`, the Agent outputs detailed information at each step:

```
==================================================
💭 Thinking Process:
--------------------------------------------------
Currently on the system desktop, need to launch eBay app first
--------------------------------------------------
🎯 Executing Action:
{
  "_metadata": "do",
  "action": "Launch",
  "app": "eBay"
}
==================================================

... (continues to next step after executing action)

==================================================
💭 Thinking Process:
--------------------------------------------------
eBay is now open, need to tap the search box
--------------------------------------------------
🎯 Executing Action:
{
  "_metadata": "do",
  "action": "Tap",
  "element": [499, 182]
}
==================================================

🎉 ================================================
✅ Task Completed: Successfully opened eBay and searched for 'wireless earphones'
==================================================
```

This allows you to clearly see the AI's reasoning process and specific operations at each step.

## Supported Apps

### Android Apps

Phone Agent supports 50+ mainstream Chinese applications:

| Category                 | Apps                                                                                   |
|--------------------------|----------------------------------------------------------------------------------------|
| Social & Messaging       | X, Tiktok, WhatsApp, Telegram, FacebookMessenger, GoogleChat, Quora, Reddit, Instagram |
| Productivity & Office    | Gmail, GoogleCalendar, GoogleDrive, GoogleDocs, GoogleTasks, Joplin                    |
| Life, Shopping & Finance | Amazon shopping, Temu, Bluecoins, Duolingo, GoogleFit, ebay                            |
| Utilities & Media        | GoogleClock, Chrome, GooglePlayStore, GooglePlayBooks, FilesbyGoogle                   |
| Travel & Navigation      | GoogleMaps, Booking.com, Trip.com, Expedia, OpenTracks                                 |

Run `python main.py --list-apps` to see the complete list.

### HarmonyOS Apps

Phone Agent supports 60+ HarmonyOS native apps and system apps:

| Category                 | Apps                                                                                   |
|--------------------------|----------------------------------------------------------------------------------------|
| Social & Messaging       | WeChat, QQ, Weibo, Feishu, Enterprise WeChat                                          |
| E-commerce & Shopping    | Taobao, JD.com, Pinduoduo, Vipshop, Dewu, Xianyu                                      |
| Food & Delivery          | Meituan, Meituan Waimai, Dianping, Haidilao                                           |
| Travel & Navigation      | 12306, Didi, Tongcheng, Amap, Baidu Maps                                              |
| Video & Entertainment    | Bilibili, Douyin, Kuaishou, Tencent Video, iQIYI, Mango TV                            |
| Music & Audio            | QQ Music, Qishui Music, Ximalaya                                                       |
| Lifestyle & Social       | Xiaohongshu, Zhihu, Toutiao, 58.com, China Mobile                                     |
| AI & Tools               | Doubao, WPS, UC Browser, CamScanner, Meitu                                            |
| System Apps              | Browser, Calendar, Camera, Clock, Cloud, File Manager, Gallery, Contacts, SMS, Settings |
| Huawei Services          | AppGallery, Music, Video, Books, Themes, Weather                                       |

Run `python main.py --device-type hdc --list-apps` to see the complete list.

## Available Actions

The Agent can perform the following actions:

| Action         | Description                              |
|----------------|------------------------------------------|
| `Launch`       | Launch an app                            |  
| `Tap`          | Tap at specified coordinates             |
| `Type`         | Input text                               |
| `Swipe`        | Swipe the screen                         |
| `Back`         | Go back to previous page                 |
| `Home`         | Return to home screen                    |
| `Long Press`   | Long press                               |
| `Double Tap`   | Double tap                               |
| `Wait`         | Wait for page to load                    |
| `Take_over`    | Request manual takeover (login/captcha)  |

## Custom Callbacks

Handle sensitive operation confirmation and manual takeover:

```python
def my_confirmation(message: str) -> bool:
    """Sensitive operation confirmation callback"""
    return input(f"Confirm execution of {message}? (y/n): ").lower() == "y"


def my_takeover(message: str) -> None:
    """Manual takeover callback"""
    print(f"Please complete manually: {message}")
    input("Press Enter after completion...")


agent = PhoneAgent(
    confirmation_callback=my_confirmation,
    takeover_callback=my_takeover,
)
```

## Examples

Check the `examples/` directory for more usage examples:

- `basic_usage.py` - Five examples: basic task, custom callbacks, single-step debugging, batch tasks, and remote device. File docstring also includes Anthropic / Ollama `ModelConfig` snippets.
- `demo_thinking.py` - Demonstrates verbose mode that prints thinking and action side by side.

## Development

### Set Up Development Environment

Development requires dev dependencies:

```bash
pip install -e ".[dev]"
```

### Run Tests

```bash
# Run all tests
pytest tests/

# Only model-layer tests
pytest tests/model/

# Only Agent or CLI tests
pytest tests/agent/ tests/cli/
```

Tests cover the three provider adapters, unified response parsing, configuration validation, Agent lifecycle, and CLI routing — all mock-based, with no real model service required.

### Design Documents

- [`docs/specs/2026-07-22-multi-model-provider-design.md`](docs/specs/2026-07-22-multi-model-provider-design.md) — Multi-model provider adapter design (OpenAI-compatible / Anthropic / Ollama, unified response parsing, tool modes, and dependency injection)
- [`docs/ios_setup/ios_setup.md`](docs/ios_setup/ios_setup.md) — iOS environment setup guide

### Complete Project Structure

```
Open-AutoGLM/
├── main.py                  # CLI entry point (Android / HarmonyOS / iOS)
├── ios.py                   # CLI entry point (iOS-specific, equivalent to --device-type ios)
├── phone_agent/
│   ├── __init__.py          # Package exports (PhoneAgent / IOSPhoneAgent)
│   ├── agent.py             # PhoneAgent main class (Android/HarmonyOS)
│   ├── agent_ios.py         # IOSPhoneAgent main class
│   ├── cli.py               # Shared model CLI option parsing
│   ├── device_factory.py    # Device type factory (adb / hdc / ios)
│   ├── adb/                 # ADB utilities
│   │   ├── connection.py    # Remote/local connection management
│   │   ├── screenshot.py    # Screen capture
│   │   ├── input.py         # Text input (ADB Keyboard)
│   │   └── device.py        # Device control (tap, swipe, etc.)
│   ├── hdc/                 # HarmonyOS HDC utilities
│   ├── xctest/              # iOS XCTest / WebDriverAgent client
│   ├── actions/             # Action handling
│   │   ├── handler.py       # Android/HarmonyOS action executor
│   │   └── handler_ios.py   # iOS action executor
│   ├── config/              # Configuration
│   │   ├── apps.py          # Android app mappings
│   │   ├── apps_harmonyos.py # HarmonyOS app mappings
│   │   ├── apps_ios.py      # iOS app mappings
│   │   ├── prompts_zh.py    # Chinese system prompts
│   │   └── prompts_en.py    # English system prompts
│   └── model/               # Multi-provider model layer
│       ├── client.py        # ModelConfig / ModelResponse / ModelClient facade
│       ├── base.py          # ModelAdapter protocol, shared exceptions
│       ├── openai_compatible.py  # OpenAI Chat Completions adapter
│       ├── anthropic.py     # Anthropic Messages adapter
│       ├── ollama.py        # Ollama /api/chat adapter
│       ├── response_parser.py # Native tool call / DSL / XML / JSON parsing
│       └── tool_schema.py   # phone_action / finish tool schemas
├── examples/                # Python API examples
├── scripts/                 # Deployment check scripts
├── tests/                   # Automated tests
│   ├── agent/               # Agent flows and lifecycle
│   ├── cli/                 # CLI entry points and platform routing
│   └── model/               # Model-layer unit tests
└── docs/
    ├── ios_setup/           # iOS environment setup
    └── specs/               # Design documents (multi-provider design)
```

## FAQ

Here are some common issues and their solutions:

### Device Not Found

Try resolving by restarting the ADB service:

```bash
adb kill-server
adb start-server
adb devices
```

If the device is still not recognized, please check:
1. Whether USB debugging is enabled
2. Whether the USB cable supports data transfer (some cables only support charging)
3. Whether you have tapped "Allow" on the authorization popup on your phone
4. Try a different USB port or cable

### Can Open Apps but Cannot Tap

Some devices require both debugging options to be enabled:
- **USB Debugging**
- **USB Debugging (Security Settings)**

Please check in `Settings → Developer Options` that both options are enabled.

### Text Input Not Working

1. Ensure ADB Keyboard is installed on the device
2. Enable it in Settings > System > Language & Input > Virtual Keyboard
3. The Agent will automatically switch to ADB Keyboard when input is needed

### Screenshot Failed (Black Screen)

This usually means the app is displaying a sensitive page (payment, password, banking apps). The Agent will automatically detect this and request manual takeover.

### Windows Encoding Issues
Error message like `UnicodeEncodeError gbk code`

Solution: Add the environment variable before running the code: `PYTHONIOENCODING=utf-8`

### Interactive Mode Not Working in Non-TTY Environment
Error like: `EOF when reading a line`

Solution: Use non-interactive mode to specify tasks directly, or switch to a TTY-mode terminal application.

### Citation

If you find our work helpful, please cite the following papers:

```bibtex
@article{liu2024autoglm,
  title={Autoglm: Autonomous foundation agents for guis},
  author={Liu, Xiao and Qin, Bo and Liang, Dongzhu and Dong, Guang and Lai, Hanyu and Zhang, Hanchen and Zhao, Hanlin and Iong, Iat Long and Sun, Jiadai and Wang, Jiaqi and others},
  journal={arXiv preprint arXiv:2411.00820},
  year={2024}
}
@article{xu2025mobilerl,
  title={MobileRL: Online Agentic Reinforcement Learning for Mobile GUI Agents},
  author={Xu, Yifan and Liu, Xiao and Liu, Xinghan and Fu, Jiaqi and Zhang, Hanchen and Jing, Bohao and Zhang, Shudan and Wang, Yuting and Zhao, Wenyi and Dong, Yuxiao},
  journal={arXiv preprint arXiv:2509.18119},
  year={2025}
}
```

---

## Automated Deployment Guide (For AI Assistants)

> **This section is specifically designed for AI assistants (such as Claude Code) to automate the deployment of Open-AutoGLM.**
>
> If you are a human reader, you can skip this section and follow the documentation above.

---

### Project Overview

Open-AutoGLM is a phone agent framework:
- **Input**: User's natural language instructions (e.g., "Open WhatsApp and send a message to John")
- **Output**: Automatically operates the user's Android phone to complete tasks
- **Mechanism**: Screenshot → Vision model understands interface → Outputs tap coordinates → ADB executes actions → Loop

The architecture consists of two parts:
1. **Agent Code** (this repository): Runs on the user's computer, responsible for calling models, parsing actions, and controlling the phone
2. **Vision Model Service**: Can be a remote API or deployed locally

---

### Pre-Deployment Checklist

Before starting deployment, confirm the following items with the user:

#### Hardware Requirements
- [ ] User has an Android phone (Android 7.0+)
- [ ] User has a USB cable that supports data transfer (not just charging)
- [ ] Phone and computer can be connected via USB cable

#### Phone Configuration
- [ ] Phone has Developer Mode enabled (Settings → About Phone → Tap Build Number 7 times)
- [ ] Phone has USB Debugging enabled (Settings → Developer Options → USB Debugging)
- [ ] Some models require enabling "USB Debugging (Security Settings)" as well
- [ ] ADB Keyboard app is installed (Download: https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk)
- [ ] ADB Keyboard is enabled in system settings (Settings → Language & Input → Enable ADB Keyboard)

#### Model Service Confirmation (Choose One)

**Ask the user explicitly: Do you already have access to an AutoGLM model service?**

- **Option A: Use an already-deployed model service (Recommended)**
  - User provides the model service URL (e.g., `http://xxx.xxx.xxx.xxx:8000/v1`)
  - No local GPU required, no model download needed
  - Use this URL directly as the `--base-url` parameter

- **Option B: Deploy model locally (High system requirements)**
  - Requires NVIDIA GPU (24GB+ VRAM recommended)
  - Requires installation of vLLM or SGLang
  - Requires downloading approximately 20GB of model files
  - **If the user is a beginner or unsure, strongly recommend Option A**

---

### Deployment Process

#### Phase 1: Environment Setup

```bash
# 1. Install ADB tools
# MacOS:
brew install android-platform-tools
# Or download manually: https://developer.android.com/tools/releases/platform-tools

# Windows: Download, extract, and add to PATH environment variable

# 2. Verify ADB installation
adb version
# Should output version information

# 3. Connect phone and verify
# Connect phone via USB cable, tap "Allow USB debugging" on phone
adb devices
# Should output device list, e.g.:
# List of devices attached
# XXXXXXXX    device
```

**If `adb devices` shows empty list or unauthorized:**
1. Check if authorization popup appeared on phone, tap "Allow"
2. Check if USB debugging is enabled
3. Try a different cable or USB port
4. Run `adb kill-server && adb start-server` and retry

#### Phase 2: Install Agent

```bash
# 1. Clone repository (if not already cloned)
git clone https://github.com/zai-org/Open-AutoGLM.git
cd Open-AutoGLM

# 2. Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
pip install -e .
```

**Note: No need to clone model repository; models are called via API.**

#### Phase 3: Configure Model Service

**If user chooses Option A (using already-deployed model):**

You can use the following third-party model services:

1. **z.ai**
   - Documentation: https://docs.z.ai/api-reference/introduction
   - `--base-url`: `https://api.z.ai/api/paas/v4`
   - `--model`: `autoglm-phone-multilingual`
   - `--apikey`: Apply for your own API key on the z.ai platform

2. **Novita AI**
   - Documentation: https://novita.ai/models/model-detail/zai-org-autoglm-phone-9b-multilingual
   - `--base-url`: `https://api.novita.ai/openai`
   - `--model`: `zai-org/autoglm-phone-9b-multilingual`
   - `--apikey`: Apply for your own API key on the Novita AI platform

3. **Parasail**
   - Documentation: https://www.saas.parasail.io/serverless?name=auto-glm-9b-multilingual
   - `--base-url`: `https://api.parasail.io/v1`
   - `--model`: `parasail-auto-glm-9b-multilingual`
   - `--apikey`: Apply for your own API key on the Parasail platform

Example usage:

```bash
# Using z.ai
python main.py --base-url https://api.z.ai/api/paas/v4 --model "autoglm-phone-multilingual" --apikey "your-z-ai-api-key" "Open Chrome browser"

# Using Novita AI
python main.py --base-url https://api.novita.ai/openai --model "zai-org/autoglm-phone-9b-multilingual" --apikey "your-novita-api-key" "Open Chrome browser"

# Using Parasail
python main.py --base-url https://api.parasail.io/v1 --model "parasail-auto-glm-9b-multilingual" --apikey "your-parasail-api-key" "Open Chrome browser"
```

Or use the URL provided by the user directly and skip local model deployment steps.

**If user chooses Option B (deploy model locally):**

```bash
# 1. Install vLLM
pip install vllm

# 2. Start model service (will auto-download model, ~20GB)
python3 -m vllm.entrypoints.openai.api_server \
  --served-model-name autoglm-phone-9b-multilingual \
  --allowed-local-media-path / \
  --mm-encoder-tp-mode data \
  --mm_processor_cache_type shm \
  --mm_processor_kwargs "{\"max_pixels\":5000000}" \
  --max-model-len 25480 \
  --chat-template-content-format string \
  --limit-mm-per-prompt "{\"image\":10}" \
  --model zai-org/AutoGLM-Phone-9B-Multilingual \
  --port 8000

# Model service URL: http://localhost:8000/v1
```

#### Phase 4: Verify Deployment

```bash
# Execute in the Open-AutoGLM directory
# Replace {MODEL_URL} with the actual model service address

python main.py --base-url {MODEL_URL} --model "autoglm-phone-9b-multilingual" "Open Gmail and send an email to File Transfer Assistant: Deployment successful"
```

**Expected Result:**
- Phone automatically opens Gmail
- Automatically searches for recipient
- Automatically sends the message "Deployment successful"

---

### Troubleshooting

| Error Symptom | Possible Cause | Solution |
|---------------|----------------|----------|
| `adb devices` shows nothing | USB debugging not enabled or cable issue | Check developer options, replace cable |
| `adb devices` shows unauthorized | Phone not authorized | Tap "Allow USB debugging" on phone |
| Can open apps but cannot tap | Missing security debugging permission | Enable "USB Debugging (Security Settings)" |
| Chinese/text input corrupted or missing | ADB Keyboard not enabled | Enable ADB Keyboard in system settings |
| Screenshot returns black screen | Sensitive page (payment/banking) | Normal behavior, system will handle automatically |
| Cannot connect to model service | Wrong URL or service not running | Check URL, confirm service is running |
| `ModuleNotFoundError` | Dependencies not installed | Run `pip install -r requirements.txt` |

---

### Deployment Key Points

1. **Prioritize confirming phone connection**: Before installing any code, ensure `adb devices` can see the device
2. **Don't skip ADB Keyboard**: Without it, text input will fail
3. **Model service is an external dependency**: Agent code doesn't include the model; a separate model service is required
4. **Check phone settings first for permission issues**: Most problems are due to incomplete phone-side configuration
5. **Test with simple tasks after deployment**: Recommend using "Open Gmail and send message to File Transfer Assistant" as acceptance criteria

---

### Command Quick Reference

```bash
# Check ADB connection
adb devices

# Restart ADB service
adb kill-server && adb start-server

# Install dependencies
pip install -r requirements.txt && pip install -e .

# Run Agent (interactive mode)
python main.py --base-url {MODEL_URL} --model "autoglm-phone-9b-multilingual"

# Run Agent (single task)
python main.py --base-url {MODEL_URL} --model "autoglm-phone-9b-multilingual" "your task description"

# View supported apps list
python main.py --list-apps
```

---

**Deployment success indicator: The phone can automatically execute user's natural language instructions.**
