# Open-AutoGLM

[Readme in English](README_en.md)

<div align="center">
<img src=resources/logo.svg width="20%"/>
</div>
<p align="center">
    👋 加入我们的 <a href="resources/WECHAT.md" target="_blank">微信</a> 社区
</p>
<p align="center">
    👋 关注智谱 AI 输入法 <a href="https://x.com/Autotyper_Agent?s=20" target="_blank">X</a> 账号
</p>
<p align="center">
    🎤 进一步在我们的产品 <a href="https://autoglm.zhipuai.cn/autotyper/" target="_blank">智谱 AI 输入法</a> 体验“用嘴发指令”
</p>
<p align="center">
    <a href="https://mp.weixin.qq.com/s/wRp22dmRVF23ySEiATiWIQ" target="_blank">AutoGLM 实战派</a> 开发者激励活动火热进行中，跑通、二创即可瓜分数万元现金奖池！成果提交 👉 <a href="https://zhipu-ai.feishu.cn/share/base/form/shrcnE3ZuPD5tlOyVJ7d5Wtir8c?from=navigation" target="_blank">入口</a>
</p>

## 懒人版快速安装

你可以使用Claude Code，配置 [GLM Coding Plan](https://bigmodel.cn/glm-coding) 后，输入以下提示词，快速部署本项目。

```
访问文档，为我安装 AutoGLM
https://raw.githubusercontent.com/zai-org/Open-AutoGLM/refs/heads/main/README.md
```

## 项目介绍

Phone Agent 是一个基于 AutoGLM 构建的手机端智能助理框架，它能够以多模态方式理解手机屏幕内容，并通过自动化操作帮助用户完成任务。系统通过
ADB(Android Debug Bridge)来控制设备，以视觉语言模型进行屏幕感知，再结合智能规划能力生成并执行操作流程。用户只需用自然语言描述需求，如“打开小红书搜索美食”，Phone
Agent 即可自动解析意图、理解当前界面、规划下一步动作并完成整个流程。系统还内置敏感操作确认机制，并支持在登录或验证码场景下进行人工接管。同时，它提供远程
ADB 调试能力，可通过 WiFi 或网络连接设备，实现灵活的远程控制与开发。

> ⚠️
> 本项目仅供研究和学习使用。严禁用于非法获取信息、干扰系统或任何违法活动。请仔细审阅 [使用条款](resources/privacy_policy.txt)。

## 与其他自动化工具集成

### Midscene.js

[Midscene.js](https://midscenejs.com/zh/index.html) 是一款由视觉模型驱动的开源 UI 自动化 SDK，支持通过 JavaScript 或 Yaml 格式的流程语法，实现多平台的自动化。

目前 Midscene.js 已完成对 AutoGLM 模型的适配，你可以通过 [Midscene.js 接入指南](https://midscenejs.com/zh/model-common-config.html#auto-glm) 快速体验 AutoGLM 在 iOS 和 Android 设备上的自动化效果。

### Claude Code（MCP Server）

本项目内置了一个 MCP server，可以把 Android 设备的截图与操控能力暴露给 Claude Code 等 MCP 客户端。由 Claude 的视觉与推理能力负责"看屏幕、做决策"，本项目负责"执行动作"，从而一步步完成玩手机游戏（如军旗）、填表单等需要智能规划的任务。

**前置条件**（无需部署模型服务）：

1. 已安装 adb 并连接 Android 设备（参见下方 [Android 环境准备](#android-环境准备)）
2. 已安装本项目：`pip install -e .`（自动带上 `mcp` 依赖）
3. 建议安装 ADB Keyboard（仅 `type_text` 工具需要，参见下方 [安装 ADB Keyboard](#4-安装-adb-keyboard仅-android-设备需要用于文本输入)）

**接入 Claude Code**：

```bash
claude mcp add phone-agent -- phone-agent mcp

# 指定设备（多设备时）
claude mcp add phone-agent -- phone-agent mcp --device-id <adb设备ID>

# 远程 / 局域网服务模式（支持云真机 / 设备机房，默认端点 /mcp）
phone-agent mcp --listen 0.0.0.0:8000
```

之后在 Claude Code 中即可使用 `/mcp` 查看连接状态，直接下达任务。

### 终端实时屏幕镜像插件（Claude Code Live Pane）

为告别自动化过程中的“黑盒盲盒”状态并实时查看设备画面，本项目提供了 Claude Code 侧栏屏幕镜像插件（对标 `mobile-next/mobile-mcp`）：

```bash
claude --plugin-dir ./plugins/phone-mirror
```

进入 Claude Code 后运行 `/phone-mirror [device-id]`，即可在右侧开辟实时屏幕镜像视窗（支持 Ghostty / kitty 终端图形协议）。支持：
- 🖱️ **鼠标点击交互（Click-to-Tap）**：鼠标直接点击终端里的手机画面，即可映射真实像素坐标并在手机上触发点击
- ⌨️ **键盘打字输入（Type-to-Send）**：聚焦画面后在终端敲击键盘，按键与文本自动实时输入到手机
- ⚡ **无闪烁流式刷新**：采用三缓冲轮转与 `$.ui.blit` 原地推流增量换帧，告别终端闪烁
- 🔘 **全套导航按键**：顶部支持 `[ Home ]`、`[ Back ]`、`[ App Switch ]`（多任务）、`[ URL ]`（内嵌网址输入）与 `[ Refresh ]`

**工具一览**（坐标均为像素，原点为截图左上角；缩放截图时坐标自动换算映射）：

| 工具 | 参数 | 说明 |
|------|------|------|
| `screenshot` | max_dimension?, quality=80 | 截图（返回图片 + 分辨率 + 当前应用）。快速对弈场景可设置 `max_dimension=1080` 或 `800`，自动下采样并压缩为 JPEG，大幅降低传输体积与视觉 Token |
| `get_current_app` | - | 当前前台应用（名称 + 包名） |
| `tap` | x, y | 点击 |
| `double_tap` | x, y | 双击 |
| `long_press` | x, y, duration_ms=1000 | 长按 |
| `swipe` | start_x, start_y, end_x, end_y, duration_ms? | 滑动（时长缺省按距离自适应） |
| `move_piece` | from_x, from_y, to_x, to_y, interval_ms=300 | 棋类复合走子：单次调用依次点击起点与终点，省去一轮模型思考往返 |
| `type_text` | text, clear=False | 输入文本（需 ADB Keyboard；clear=True 先清空输入框） |
| `get_clipboard` | - | 获取系统剪贴板文本内容 |
| `set_clipboard` | text | 设置系统剪贴板文本（适合粘贴长文本、Token 或 URL） |
| `batch_actions` | actions | 通用动作批处理：单次调用顺序执行一组连续动作（如点击、等待、输入等），节省多轮思考往返并在遇到错误时立即中断 |
| `back` / `home` | - | 返回键 / 主页键 |
| `launch_app` | app | 启动应用：内置中文名（如"微信"）或包名（如 `com.tencent.mm`） |
| `force_stop_app` | app | 强制停止应用：内置中文名或包名，用于关闭卡死应用或退出重置 |
| `clear_app_data` | app | 清除应用全部数据与缓存：重置为首次安装状态，适用于测试与 Benchmark |
| `install_app` | path | 安装本地 APK 文件到设备中（`-r` 保留数据重新安装） |
| `get_orientation` | - | 获取屏幕方向与旋转模式（横屏/竖屏、旋转角度） |
| `set_orientation` | orientation | 设置/锁定屏幕方向（"portrait" 锁定竖屏 / "landscape" 锁定横屏 / "auto" 恢复自动旋转） |
| `wait` | seconds=1.0 | 等待画面变化（0.1–30 秒） |

**示例：玩军旗**

> 用 phone-agent 的 MCP 工具和我手机上的军旗下棋：先 `launch_app` 启动军旗 App（不在内置列表就用包名，可用 `adb shell pm list packages` 查询），之后每一轮先用 `screenshot(max_dimension=1080)` 看棋盘，推理双方棋子与局势，再用 `move_piece` 走子（或用 `tap` 翻棋）；轮到对方走棋时 `wait` 2 秒后重新截图。不确定局面就先描述棋盘再行动。

**高频对弈/限时操作提速建议**：

- **通用动作批处理**：需要连续执行几个确定性动作时（例如点击输入框后等待并输入文本），优先使用 `batch_actions` 一次性下发，省去多次“截图-推理”的往返延迟。
- **单轮走子**：下棋时优先使用 `move_piece(from_x, from_y, to_x, to_y)` 代替两次单独的 `tap`，一次模型思考即可完成选子与落子。
- **降低图片尺寸**：在环境变量中设置 `export PHONE_AGENT_SCREENSHOT_MAX_DIM=1080`，或在调用 `screenshot(max_dimension=1080)` 时限制尺寸，图片体积从 2MB 骤降至 80KB，视觉 Token 减少 60% 以上，显著加速首字推理（坐标会自动等比换算回真机像素，无需人工换算）。

**常见问题**：

- 会话期间手机输入法被切换为 ADB Keyboard 属预期行为，工具执行后会尽力恢复原输入法
- 截图返回黑图时阅读伴随的警告文本：支付等敏感页面系统禁止截图；设备断连时也会返回黑图，恢复连接后自动恢复
- 怀疑操作没生效时，先再截一张图确认

## 模型下载地址

| Model                         | Download Links                                                                                                                                                         |
|-------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| AutoGLM-Phone-9B              | [🤗 Hugging Face](https://huggingface.co/zai-org/AutoGLM-Phone-9B)<br>[🤖 ModelScope](https://modelscope.cn/models/ZhipuAI/AutoGLM-Phone-9B)                           |
| AutoGLM-Phone-9B-Multilingual | [🤗 Hugging Face](https://huggingface.co/zai-org/AutoGLM-Phone-9B-Multilingual)<br>[🤖 ModelScope](https://modelscope.cn/models/ZhipuAI/AutoGLM-Phone-9B-Multilingual) |

其中，`AutoGLM-Phone-9B` 是针对中文手机应用优化的模型，而 `AutoGLM-Phone-9B-Multilingual` 支持英语场景，适用于包含英文等其他语言内容的应用。

## Android 环境准备

### 1. Python 环境

建议使用 Python 3.10 及以上版本。

### 2. 手机调试命令行工具

根据你的设备类型选择相应的工具：

#### 对于 Android 设备 - 使用 ADB

1. 下载官方 ADB [安装包](https://developer.android.com/tools/releases/platform-tools?hl=zh-cn)，并解压到自定义路径
2. 配置环境变量

- MacOS 配置方法：在 `Terminal` 或者任何命令行工具里

  ```bash
  # 假设解压后的目录为 ~/Downloads/platform-tools。如果不是请自行调整命令。
  export PATH=${PATH}:~/Downloads/platform-tools
  ```

- Windows 配置方法：可参考 [第三方教程](https://blog.csdn.net/x2584179909/article/details/108319973) 进行配置。

#### 对于鸿蒙设备 (HarmonyOS NEXT版本以上) - 使用 HDC

1. 下载 HDC 工具：
   - 从 [HarmonyOS SDK](https://developer.huawei.com/consumer/cn/download/) 下载
2. 配置环境变量

- MacOS/Linux 配置方法：

  ```bash
  # 假设解压后的目录为 ~/Downloads/harmonyos-sdk/toolchains。请根据实际路径调整。
  export PATH=${PATH}:~/Downloads/harmonyos-sdk/toolchains
  ```

- Windows 配置方法：将 HDC 工具所在目录添加到系统 PATH 环境变量

### 3. Android 7.0+ 或 HarmonyOS 设备，并启用 `开发者模式` 和 `USB 调试`

1. 开发者模式启用：通常启用方法是，找到 `设置-关于手机-版本号` 然后连续快速点击 10
   次左右，直到弹出弹窗显示“开发者模式已启用”。不同手机会有些许差别，如果找不到，可以上网搜索一下教程。
2. USB 调试启用：启用开发者模式之后，会出现 `设置-开发者选项-USB 调试`，勾选启用
3. 部分机型在设置开发者选项以后, 可能需要重启设备才能生效. 可以测试一下: 将手机用USB数据线连接到电脑后, `adb devices`
   查看是否有设备信息, 如果没有说明连接失败.

**请务必仔细检查相关权限**

![权限](resources/screenshot-20251209-181423.png)

### 4. 安装 ADB Keyboard(仅 Android 设备需要，用于文本输入)

**注意：鸿蒙设备使用原生输入方法，无需安装 ADB Keyboard。**

如果你使用的是 Android 设备：

下载 [安装包](https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk) 并在对应的安卓设备中进行安装。
注意，安装完成后还需要到 `设置-输入法` 或者 `设置-键盘列表` 中启用 `ADB Keyboard` 才能生效(或使用命令`adb shell ime enable com.android.adbkeyboard/.AdbIME`[How-to-use](https://github.com/senzhk/ADBKeyBoard/blob/master/README.md#how-to-use))

## iPhone 环境准备

如果你使用的是 iPhone 设备，请参考专门的 iOS 配置文档：

📱 [iOS 环境配置指南](docs/ios_setup/ios_setup.md)

该文档详细介绍了如何配置 WebDriverAgent 和 iPhone 设备，以便在 iOS 上使用 AutoGLM。

## 部署准备工作

### 1. 安装依赖

```bash
pip install -r requirements.txt 
pip install -e .
```

### 2. 配置 ADB 或 HDC

#### 对于 Android 设备

确认 **USB数据线具有数据传输功能**, 而不是仅有充电功能

确保已安装 ADB 并使用 **USB数据线** 连接设备：

```bash
# 检查已连接的设备
adb devices

# 输出结果应显示你的设备，如：
# List of devices attached
# emulator-5554   device
```

#### 对于鸿蒙设备

确认 **USB数据线具有数据传输功能**, 而不是仅有充电功能

确保已安装 HDC 并使用 **USB数据线** 连接设备：

```bash
# 检查已连接的设备
hdc list targets

# 输出结果应显示你的设备，如：
# 7001005458323933328a01bce01c2500
```

### 3. 启动模型服务

你可以选择自行部署模型服务，或使用第三方模型服务商。

#### 选项 A: 使用第三方模型服务

如果你不想自行部署模型，可以使用以下已部署我们模型的第三方服务：

**1. 智谱 BigModel**

- 文档: https://docs.bigmodel.cn/cn/api/introduction
- `--base-url`: `https://open.bigmodel.cn/api/paas/v4`
- `--model`: `autoglm-phone`
- `--apikey`: 在智谱平台申请你的 API Key

**2. ModelScope(魔搭社区)**

- 文档: https://modelscope.cn/models/ZhipuAI/AutoGLM-Phone-9B
- `--base-url`: `https://api-inference.modelscope.cn/v1`
- `--model`: `ZhipuAI/AutoGLM-Phone-9B`
- `--apikey`: 在 ModelScope 平台申请你的 API Key

使用第三方服务的示例：

```bash
# 使用智谱 BigModel
python main.py --base-url https://open.bigmodel.cn/api/paas/v4 --model "autoglm-phone" --apikey "your-bigmodel-api-key" "打开美团搜索附近的火锅店"

# 使用 ModelScope
python main.py --base-url https://api-inference.modelscope.cn/v1 --model "ZhipuAI/AutoGLM-Phone-9B" --apikey "your-modelscope-api-key" "打开美团搜索附近的火锅店"
```

> 💡 上述第三方服务均使用 OpenAI Chat Completions 兼容协议，默认 `--provider openai` 即可接入。还可以接入任何 OpenAI 兼容服务(如 DashScope、自定义 vLLM/SGLang 服务)。其它协议(Anthropic Messages、Ollama)的接入方式见下方[多模型供应商](#多模型供应商)章节。

#### 选项 B: 自行部署模型

如果你希望在本地或自己的服务器上部署模型：

1. 按照 `requirements.txt` 中 `For Model Deployment` 章节自行安装推理引擎框架。

对于SGLang， 除了使用pip安装，你也可以使用官方docker:
>
> ```shell
> docker pull lmsysorg/sglang:v0.5.6.post1
> ```
>
> 进入容器，执行
>
> ```
> pip install nvidia-cudnn-cu12==9.16.0.29
> ```

对于 vLLM，除了使用pip 安装，你也可以使用官方docker:
>
> ```shell
> docker pull vllm/vllm-openai:v0.12.0
> ```
>
> 进入容器，执行
>
> ```
> pip install -U transformers --pre
> ```

**注意**: 上述步骤出现的关于 transformers 的依赖冲突可以忽略。

1. 在对应容器或者实体机中(非容器安装)下载模型，通过 SGlang / vLLM 启动，得到 OpenAI 格式服务。这里提供一个 vLLM部署方案，请严格遵循我们提供的启动参数:

- vLLM:

```shell
python3 -m vllm.entrypoints.openai.api_server \
 --served-model-name autoglm-phone-9b \
 --allowed-local-media-path /   \
 --mm-encoder-tp-mode data \
 --mm_processor_cache_type shm \
 --mm_processor_kwargs "{\"max_pixels\":5000000}" \
 --max-model-len 25480  \
 --chat-template-content-format string \
 --limit-mm-per-prompt "{\"image\":10}" \
 --model zai-org/AutoGLM-Phone-9B \
 --port 8000
```

- SGLang:

```shell
python3 -m sglang.launch_server --model-path  zai-org/AutoGLM-Phone-9B \
        --served-model-name autoglm-phone-9b  \
        --context-length 25480  \
        --mm-enable-dp-encoder   \
        --mm-process-config '{"image":{"max_pixels":5000000}}'  \
        --port 8000
```

- 该模型结构与 `GLM-4.1V-9B-Thinking` 相同, 关于模型部署的详细内容，你也以查看 [GLM-V](https://github.com/zai-org/GLM-V)
  获取模型部署和使用指南。

- 运行成功后，将可以通过 `http://localhost:8000/v1` 访问模型服务。 如果您在远程服务器部署模型, 使用该服务器的IP访问模型.

### 4. 检查模型部署

模型服务启动后，可以使用检查脚本验证部署是否成功：

```bash
python scripts/check_deployment_cn.py --base-url http://你的IP:你的端口/v1 --model 模型名称
```

脚本将发送测试请求并展示模型的推理结果，你可以根据输出判断模型部署是否正常工作。

基于给定的任务, 预期输出如下。**如果思维链长度很短, 或者出现了乱码, 很可能是模型部署失败**, 请仔细检查文档要求的配置和依赖。

```
<think>用户想要比较这个洗发水在京东和淘宝上的价格，然后选择最便宜的平台下单。当前在小红书app上，显示的是一个关于LUMMI MOOD洗发水的帖子。

我需要：
1. 先启动京东app，搜索这个洗发水
2. 查看京东的价格
3. 再启动淘宝app，搜索这个洗发水
4. 查看淘宝的价格
5. 比较价格后，选择最便宜的京东或淘宝下单

首先，我需要从当前的小红书界面退出，然后启动京东app。</think>
<answer>do(action="Launch", app="京东")
```

**参数说明：**
- `--base-url`: 模型服务地址(根据实际部署地址修改)
- `--model`: 模型名称
- `--messages-file`: 可选，指定自定义测试消息文件(默认使用 `scripts/sample_messages.json`)

## 使用 AutoGLM

### 命令行

根据你部署的模型, 设置 `--base-url` 和 `--model` 参数, 设置 `--device-type` 指定是安卓设备或鸿蒙设备 (默认值 adb 表示安卓设备, hdc 表示鸿蒙设备). 例如:

```bash
# Android 设备 - 交互模式
python main.py --base-url http://localhost:8000/v1 --model "autoglm-phone-9b"

# Android 设备 - 指定任务
python main.py --base-url http://localhost:8000/v1 "打开美团搜索附近的火锅店"

# 鸿蒙设备 - 交互模式
python main.py --device-type hdc --base-url http://localhost:8000/v1 --model "autoglm-phone-9b"

# 鸿蒙设备 - 指定任务
python main.py --device-type hdc --base-url http://localhost:8000/v1 "打开美团搜索附近的火锅店"

# 使用 API Key 进行认证
python main.py --apikey sk-xxxxx

# 使用英文 system prompt
python main.py --lang en --base-url http://localhost:8000/v1 "Open Chrome browser"

# 列出支持的应用（Android）
python main.py --list-apps

# 列出支持的应用（鸿蒙）
python main.py --device-type hdc --list-apps
```

#### iOS 设备

iOS 设备既可以通过 `--device-type ios` 走统一的 `main.py` 入口，也可以使用专用的 `ios.py` 入口：

```bash
# iOS 设备 - 指定任务
python ios.py --base-url http://localhost:8000/v1 --model "autoglm-phone-9b" "Open Safari and search for iPhone tips"

# iOS 设备 - 指定 WDA 地址（WiFi 调试时）
python ios.py --wda-url http://192.168.1.100:8100

# 列出已连接的 iOS 设备
python ios.py --list-devices

# 查看 WebDriverAgent 状态
python ios.py --wda-status
```

iOS 设备的环境准备参考 [iOS 环境配置指南](docs/ios_setup/ios_setup.md)。

### Python API

```python
from phone_agent import PhoneAgent
from phone_agent.model import ModelConfig

# Configure model
model_config = ModelConfig(
    base_url="http://localhost:8000/v1",
    model_name="autoglm-phone-9b",
)

# 创建 Agent
agent = PhoneAgent(model_config=model_config)

try:
    # 执行任务
    result = agent.run("打开淘宝搜索无线耳机")
    print(result)
finally:
    # 显式释放模型客户端和设备连接
    agent.close()
```

> ⚠️ `PhoneAgent` 内部会持有模型客户端和设备句柄，建议使用 `try/finally` 调用 `agent.close()`，避免在长任务或异常路径下泄漏连接。如果你通过 `model_client=` 注入了自定义客户端，`agent.close()` 不会关闭它，需由调用方自行管理。

## 多模型供应商

除了默认的 `openai`(OpenAI Chat Completions 兼容)协议外，本项目还支持以下两类供应商协议，可通过 `--provider` 显式切换，不通过 URL 或模型名猜测：

| provider | 协议 | 适用场景 |
|---|---|---|
| `openai` (默认) | OpenAI Chat Completions | AutoGLM 系列模型、智谱 BigModel、ModelScope、DashScope gui-plus、本地 vLLM/SGLang、其它 OpenAI 兼容服务 |
| `anthropic` | Anthropic Messages | 官方 Anthropic 接口及严格实现 Messages 协议的代理服务 |
| `ollama` | Ollama `/api/chat` | 本地 Ollama 模型(需具备视觉能力) |

### CLI 用法

```bash
# 使用 Anthropic
python main.py \
  --provider anthropic \
  --base-url https://api.anthropic.com \
  --model "claude-sonnet-4-6" \
  --api-key "$ANTHROPIC_API_KEY" \
  "打开小红书搜索美食攻略"

# 使用本地 Ollama 模型
python main.py \
  --provider ollama \
  --base-url http://localhost:11434 \
  --model "llama3.2-vision" \
  "打开美团搜索附近的火锅店"
```

所有入口(`main.py` 和 `ios.py`)均支持以下参数和环境变量，优先级为 **命令行 > 环境变量 > provider 默认值**：

| 参数 | 环境变量 | 说明 |
|---|---|---|
| `--provider` | `PHONE_AGENT_PROVIDER` | 模型供应商：`openai` / `anthropic` / `ollama` |
| `--tool-mode` | `PHONE_AGENT_TOOL_MODE` | 工具调用模式：`auto` / `native` / `text` |
| `--base-url` | `PHONE_AGENT_BASE_URL` | 模型服务地址(各 provider 默认值不同) |
| `--model` | `PHONE_AGENT_MODEL` | 模型名称 |
| `--api-key` | `PHONE_AGENT_API_KEY` | API Key(向后兼容别名 `--apikey`，两者同时出现时报冲突) |

### 工具调用模式 (`tool_mode`)

| 模式 | 行为 |
|---|---|
| `auto` (默认) | 优先发送原生 tool 定义；若服务在尚未返回任何内容前明确拒绝 tools(返回 400/422 且错误字段精确指向 `tools`/`tool_choice`)，自动重试一次无工具请求。服务接受 tools 但模型返回文本时，不重试，直接进入混合文本解析。仅 `openai`/`anthropic` adapter 会把这类拒绝降级为触发回退的信号；`ollama` 原生协议无结构化错误字段，被拒时直接报错、不自动回退，需要回退时请显式使用 `text` 模式。 |
| `native` | 始终发送原生 tool 定义；服务拒绝时直接失败。 |
| `text` | 从不发送原生 tool 定义，只使用现有 prompt + 文本 DSL(`do(...)`/`finish(...)`)、XML、JSON 输出。 |

通用云端模型推荐用 `auto` 或 `native`；格式不稳定的本地模型可用 `text` 强制走文本解析。

### Python API 示例

```python
import os
from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig, ModelClient

# Anthropic 示例
anthropic_config = ModelConfig(
    provider="anthropic",
    model_name="claude-sonnet-4-6",
    api_key=os.environ["ANTHROPIC_API_KEY"],
    tool_mode="auto",
)

# Ollama 示例（localhost 是运行 Python 进程的主机，不是手机）
ollama_config = ModelConfig(
    provider="ollama",
    model_name="llama3.2-vision",
    base_url="http://localhost:11434",
    tool_mode="auto",
)

# 使用注入 ModelClient 的方式，便于自定义或测试
agent = PhoneAgent(
    model_config=anthropic_config,
    agent_config=AgentConfig(lang="cn"),
    model_client=ModelClient(anthropic_config, verbose=True),
)
try:
    agent.run("打开微信发送消息给文件传输助手")
finally:
    agent.close()
```

### 关键约束

- **所有 provider 的模型必须支持图像输入**，否则截图无法送达模型；遇到服务明确不接受图像的错误，会转换为可读错误而非静默降级为纯文本。
- `--base-url` 必须为绝对 http/https URL，不能包含用户名密码；尾斜杠会被自动去除。
- `openai` 允许空 API Key(用 `"EMPTY"` 或缺省代表无鉴权，是否需要 Key 由服务决定)；`anthropic` 强制要求非空非 `"EMPTY"` 的 API Key；`ollama` 不接受 API Key，代理鉴权请通过 `extra_headers` 传入。
- `frequency_penalty` 仅 `openai` 支持；`anthropic` 和 `ollama` 中 `None` 或 `0.0` 视为未启用，其它值会立即报配置错误。
- `extra_body` 不能覆盖 `model`/`messages`/`tools`/`tool_choice`/`stream` 等保留字段；Ollama 的 `extra_body.options` 不能覆盖由 `max_tokens`/`temperature`/`top_p` 生成的 `num_predict`/`temperature`/`top_p`。
- API Key 只从命令行、环境变量或调用方传入；日志和异常中会脱敏，请勿把它写入命令历史或长期文件。

### 依赖

本项目固定以下依赖下界，三个 provider 适配器共享使用：

| 依赖 | 下界 | 用途 |
|---|---|---|
| `openai` | `>=2.9.0` | OpenAI-compatible adapter |
| `anthropic` | `>=0.117.1` | Anthropic Messages adapter（流式原始事件接口） |
| `httpx` | `>=0.28.1` | Ollama 原生协议直接调用 |

## 远程调试

Phone Agent 支持通过 WiFi/网络进行远程 ADB/HDC 调试，无需 USB 连接即可控制设备。

### 配置远程调试

#### 在手机端开启无线调试

##### Android 设备

确保手机和电脑在同一个WiFi中，如图所示

![开启无线调试](resources/setting.png)

##### 鸿蒙设备

确保手机和电脑在同一个WiFi中：
1. 进入 `设置 > 系统和更新 > 开发者选项`
2. 开启 `USB 调试` 和 `无线调试`
3. 记录显示的 IP 地址和端口号

#### 在电脑端使用标准 ADB/HDC 命令

```bash
# Android 设备 - 通过 WiFi 连接, 改成手机显示的 IP 地址和端口
adb connect 192.168.1.100:5555

# 验证连接
adb devices
# 应显示：192.168.1.100:5555    device

# 鸿蒙设备 - 通过 WiFi 连接
hdc tconn 192.168.1.100:5555

# 验证连接
hdc list targets
# 应显示：192.168.1.100:5555
```

### 设备管理命令

#### Android 设备（ADB）

```bash
# 列出所有已连接设备
adb devices

# 连接远程设备
adb connect 192.168.1.100:5555

# 断开指定设备
adb disconnect 192.168.1.100:5555

# 指定设备执行任务
python main.py --device-id 192.168.1.100:5555 --base-url http://localhost:8000/v1 --model "autoglm-phone-9b" "打开抖音刷视频"
```

#### 鸿蒙设备（HDC）

```bash
# 列出所有已连接设备
hdc list targets

# 连接远程设备
hdc tconn 192.168.1.100:5555

# 断开指定设备
hdc tdisconn 192.168.1.100:5555

# 指定设备执行任务
python main.py --device-type hdc --device-id 192.168.1.100:5555 --base-url http://localhost:8000/v1 --model "autoglm-phone-9b" "打开抖音刷视频"
```

### Python API 远程连接

#### Android 设备（ADB）

```python
from phone_agent.adb import ADBConnection, list_devices

# 创建连接管理器
conn = ADBConnection()

# 连接远程设备
success, message = conn.connect("192.168.1.100:5555")
print(f"连接状态: {message}")

# 列出已连接设备
devices = list_devices()
for device in devices:
    print(f"{device.device_id} - {device.connection_type.value}")

# 在 USB 设备上启用 TCP/IP
success, message = conn.enable_tcpip(5555)
ip = conn.get_device_ip()
print(f"设备 IP: {ip}")

# 断开连接
conn.disconnect("192.168.1.100:5555")
```

#### 鸿蒙设备（HDC）

```python
from phone_agent.hdc import HDCConnection, list_devices

# 创建连接管理器
conn = HDCConnection()

# 连接远程设备
success, message = conn.connect("192.168.1.100:5555")
print(f"连接状态: {message}")

# 列出已连接设备
devices = list_devices()
for device in devices:
    print(f"{device.device_id} - {device.connection_type.value}")

# 断开连接
conn.disconnect("192.168.1.100:5555")
```

### 远程连接问题排查

**连接被拒绝：**

- 确保设备和电脑在同一网络
- 检查防火墙是否阻止 5555 端口
- 确认已启用 TCP/IP 模式：`adb tcpip 5555`

**连接断开：**

- WiFi 可能断开了，使用 `--connect` 重新连接
- 部分设备重启后会禁用 TCP/IP，需要通过 USB 重新启用

**多设备：**

- 使用 `--device-id` 指定要使用的设备
- 或使用 `--list-devices` 查看所有已连接设备

## 配置

### 自定义SYSTEM PROMPT

系统提供中英文两套 prompt，通过 `--lang` 参数切换：

- `--lang cn` - 中文 prompt(默认)，配置文件：`phone_agent/config/prompts_zh.py`
- `--lang en` - 英文 prompt，配置文件：`phone_agent/config/prompts_en.py`

可以直接修改对应的配置文件来增强模型在特定领域的能力，或通过注入 app 名称禁用某些 app。

### 环境变量

| 变量                          | 描述                     | 默认值                        |
|-----------------------------|------------------------|----------------------------|
| `PHONE_AGENT_PROVIDER`      | 模型供应商（`openai` / `anthropic` / `ollama`） | `openai` |
| `PHONE_AGENT_TOOL_MODE`     | 工具调用模式（`auto` / `native` / `text`） | `auto` |
| `PHONE_AGENT_BASE_URL`      | 模型 API 地址（按 provider 不同有不同默认值） | 见 [多模型供应商](#多模型供应商) |
| `PHONE_AGENT_MODEL`         | 模型名称                   | `autoglm-phone-9b`(仅 `openai`) |
| `PHONE_AGENT_API_KEY`       | 模型认证 API Key           | `EMPTY`                    |
| `PHONE_AGENT_MAX_STEPS`     | 每个任务最大步数               | `100`                      |
| `PHONE_AGENT_DEVICE_ID`     | ADB/HDC 设备 ID          | (自动检测)                     |
| `PHONE_AGENT_DEVICE_TYPE`   | 设备类型 (`adb` / `hdc` / `ios`)   | `adb`                      |
| `PHONE_AGENT_LANG`          | 语言 (`cn` 或 `en`)       | `cn`                       |
| `PHONE_AGENT_WDA_URL`       | WebDriverAgent URL（仅 iOS） | `http://localhost:8100` |

> 优先级：**命令行参数 > 环境变量 > provider 默认值**。

### 模型配置

```python
from phone_agent.model import ModelConfig

config = ModelConfig(
    base_url="http://localhost:8000/v1",
    api_key="EMPTY",  # API 密钥(如需要)
    model_name="autoglm-phone-9b",  # 模型名称
    max_tokens=2048,  # 最大输出 token 数
    temperature=0.1,  # 采样温度；None 时按 provider 适配为 OpenAI 路径有效默认（openai/anthropic/ollama 均为 0.0）
    top_p=0.85,  # nucleus 采样概率；None 时 openai/ollama 用 0.85，anthropic 不发送该字段
    frequency_penalty=0.2,  # 频率惩罚；仅 openai 发送，None 时用 0.2，anthropic/ollama 视为未启用
    extra_body={},  # 追加到请求体的额外字段
    lang="cn",  # UI 提示语言
    provider="openai",  # openai / anthropic / ollama
    tool_mode="auto",  # auto / native / text
    timeout=120.0,  # 单次请求超时（秒）
    extra_headers=None,  # 自定义头部（如代理鉴权），日志会脱敏
)
```

各 provider 的 `base_url` 默认值：

| provider | 默认 `base_url` | 备注 |
|---|---|---|
| `openai` | `http://localhost:8000/v1` | SDK 追加资源路径 |
| `anthropic` | `https://api.anthropic.com` | SDK 负责 Messages 路径 |
| `ollama` | `http://localhost:11434` | adapter 追加 `/api/chat`、`/api/tags` |

### Agent 配置

```python
from phone_agent.agent import AgentConfig  # Android/HarmonyOS
from phone_agent.agent_ios import IOSAgentConfig  # iOS

config = AgentConfig(
    max_steps=100,  # 每个任务最大步数
    device_id=None,  # ADB/HDC 设备 ID(None 为自动检测)
    lang="cn",  # 语言选择：cn(中文)或 en(英文)
    system_prompt=None,  # 自定义 system prompt（None 时按 lang 读取默认）
    verbose=True,  # 打印调试信息(包括思考过程和执行动作)
)

# iOS 专用字段
ios_config = IOSAgentConfig(
    max_steps=100,
    wda_url="http://localhost:8100",  # WebDriverAgent URL
    device_id=None,  # iOS UDID
    lang="cn",
    verbose=True,
)
```

### 模型客户端依赖注入

需要测试或自定义传输层时，可以构造 `ModelClient` 并注入 Agent：

```python
from phone_agent import PhoneAgent
from phone_agent.model import ModelClient, ModelConfig

model_config = ModelConfig(provider="openai")
model_client = ModelClient(model_config, verbose=True)
model_client.check_connection()  # 显式预检连接

agent = PhoneAgent(model_config=model_config, model_client=model_client)
try:
    agent.run("打开微信")
finally:
    agent.close()       # 不会关闭注入的 model_client
    model_client.close()  # 由调用方负责关闭
```

未注入 `model_client` 时，`PhoneAgent` 会内部创建并拥有 `ModelClient`，`agent.close()` 会自动关闭它。

### Verbose 模式输出

当 `verbose=True` 时，Agent 会在每一步输出详细信息：

```
==================================================
💭 思考过程:
--------------------------------------------------
当前在系统桌面，需要先启动小红书应用
--------------------------------------------------
🎯 执行动作:
{
  "_metadata": "do",
  "action": "Launch",
  "app": "小红书"
}
==================================================

... (执行动作后继续下一步)

==================================================
💭 思考过程:
--------------------------------------------------
小红书已打开，现在需要点击搜索框
--------------------------------------------------
🎯 执行动作:
{
  "_metadata": "do",
  "action": "Tap",
  "element": [500, 100]
}
==================================================

🎉 ================================================
✅ 任务完成: 已成功搜索美食攻略
==================================================
```

这样可以清楚地看到 AI 的推理过程和每一步的具体操作。

## 支持的应用

### Android 应用

Phone Agent 支持 50+ 款主流中文应用：

| 分类   | 应用              |
|------|-----------------|
| 社交通讯 | 微信、QQ、微博        |
| 电商购物 | 淘宝、京东、拼多多       |
| 美食外卖 | 美团、饿了么、肯德基      |
| 出行旅游 | 携程、12306、滴滴出行   |
| 视频娱乐 | bilibili、抖音、爱奇艺 |
| 音乐音频 | 网易云音乐、QQ音乐、喜马拉雅 |
| 生活服务 | 大众点评、高德地图、百度地图  |
| 内容社区 | 小红书、知乎、豆瓣       |

运行 `python main.py --list-apps` 查看完整列表。

### 鸿蒙应用

Phone Agent 支持 60+ 款鸿蒙原生应用和系统应用：

| 分类      | 应用                                       |
|---------|------------------------------------------|
| 社交通讯    | 微信、QQ、微博、飞书、企业微信                        |
| 电商购物    | 淘宝、京东、拼多多、唯品会、得物、闲鱼                     |
| 美食外卖    | 美团、美团外卖、大众点评、海底捞                        |
| 出行旅游    | 12306、滴滴出行、同程旅行、高德地图、百度地图               |
| 视频娱乐    | bilibili、抖音、快手、腾讯视频、爱奇艺、芒果TV            |
| 音乐音频    | QQ音乐、汽水音乐、喜马拉雅                           |
| 生活服务    | 小红书、知乎、今日头条、58同城、中国移动                   |
| AI与工具   | 豆包、WPS、UC浏览器、扫描全能王、美图秀秀                 |
| 系统应用    | 浏览器、日历、相机、时钟、云空间、文件管理器、相册、联系人、短信、设置等   |
| 华为服务    | 应用市场、音乐、视频、阅读、主题、天气                     |

运行 `python main.py --device-type hdc --list-apps` 查看完整列表。

## 可用操作

Agent 可以执行以下操作：

| 操作           | 描述              |
|--------------|-----------------|
| `Launch`     | 启动应用            |  
| `Tap`        | 点击指定坐标          |
| `Type`       | 输入文本            |
| `Swipe`      | 滑动屏幕            |
| `Back`       | 返回上一页           |
| `Home`       | 返回桌面            |
| `Long Press` | 长按              |
| `Double Tap` | 双击              |
| `Wait`       | 等待页面加载          |
| `Take_over`  | 请求人工接管(登录/验证码等) |

## 自定义回调

处理敏感操作确认和人工接管：

```python
def my_confirmation(message: str) -> bool:
    """敏感操作确认回调"""
    return input(f"确认执行 {message}？(y/n): ").lower() == "y"


def my_takeover(message: str) -> None:
    """人工接管回调"""
    print(f"请手动完成: {message}")
    input("完成后按回车继续...")


agent = PhoneAgent(
    confirmation_callback=my_confirmation,
    takeover_callback=my_takeover,
)
```

## 示例

查看 `examples/` 目录获取更多使用示例：

- `basic_usage.py` - 包含 5 个示例：基础任务执行、自定义回调、单步调试、批量任务、远程设备；文件头部还附有 Anthropic / Ollama 的 `ModelConfig` 配置片段。
- `demo_thinking.py` - 演示 verbose 模式下同时输出 thinking 与 action 的执行流程。

## 二次开发

### 配置开发环境

二次开发需要使用开发依赖：

```bash
pip install -e ".[dev]"
```

### 运行测试

```bash
# 运行全部测试
pytest tests/

# 仅运行模型层测试
pytest tests/model/

# 仅运行 Agent 或 CLI 测试
pytest tests/agent/ tests/cli/
```

测试覆盖三个 provider 适配器、统一响应解析、配置校验、Agent 生命周期、CLI 路由等，均使用 mock，不依赖真实模型服务。

### 设计文档

- [`docs/specs/2026-07-22-multi-model-provider-design.md`](docs/specs/2026-07-22-multi-model-provider-design.md) - 多模型供应商适配设计（OpenAI-compatible / Anthropic / Ollama，统一响应解析、工具模式与依赖注入）
- [`docs/ios_setup/ios_setup.md`](docs/ios_setup/ios_setup.md) - iOS 环境配置指南


### 完整项目结构

```
Open-AutoGLM/
├── main.py                  # CLI 入口（Android / HarmonyOS / iOS 通用）
├── ios.py                   # CLI 入口（iOS 专用，等价于 --device-type ios）
├── phone_agent/
│   ├── __init__.py          # 包导出（PhoneAgent / IOSPhoneAgent）
│   ├── agent.py             # PhoneAgent 主类（Android/HarmonyOS）
│   ├── agent_ios.py         # IOSPhoneAgent 主类
│   ├── cli.py               # 共享的模型 CLI 选项解析
│   ├── device_factory.py    # 设备类型工厂（adb / hdc / ios）
│   ├── adb/                 # ADB 工具
│   │   ├── connection.py    # 远程/本地连接管理
│   │   ├── screenshot.py    # 屏幕截图
│   │   ├── input.py         # 文本输入 (ADB Keyboard)
│   │   └── device.py        # 设备控制（点击、滑动等）
│   ├── hdc/                 # 鸿蒙 HDC 工具
│   ├── xctest/              # iOS XCTest / WebDriverAgent 客户端
│   ├── actions/             # 操作处理
│   │   ├── handler.py       # Android/HarmonyOS 操作执行器
│   │   └── handler_ios.py   # iOS 操作执行器
│   ├── config/              # 配置
│   │   ├── apps.py          # Android 支持的应用映射
│   │   ├── apps_harmonyos.py # 鸿蒙支持的应用映射
│   │   ├── apps_ios.py      # iOS 支持的应用映射
│   │   ├── prompts_zh.py     # 中文系统提示词
│   │   └── prompts_en.py     # 英文系统提示词
│   └── model/               # 多 provider 模型层
│       ├── client.py        # ModelConfig / ModelResponse / ModelClient 兼容门面
│       ├── base.py          # ModelAdapter 协议、共享异常类型
│       ├── openai_compatible.py  # OpenAI Chat Completions adapter
│       ├── anthropic.py     # Anthropic Messages adapter
│       ├── ollama.py        # Ollama /api/chat adapter
│       ├── response_parser.py # 原生 tool call / DSL / XML / JSON 解析
│       └── tool_schema.py   # phone_action / finish 工具 schema
├── examples/                # Python API 示例
├── scripts/                 # 部署检查脚本
├── tests/                   # 自动化测试
│   ├── agent/               # Agent 流程与生命周期
│   ├── cli/                 # CLI 入口与平台路由
│   └── model/               # 模型层单元测试
└── docs/
    ├── ios_setup/           # iOS 环境配置
    └── specs/               # 设计文档（含多 provider 适配设计）
```

## 常见问题

我们列举了一些常见的问题，以及对应的解决方案：

### 设备未找到

尝试通过重启 ADB 服务来解决：

```bash
adb kill-server
adb start-server
adb devices
```

如果仍然无法识别，请检查：

1. USB 调试是否已开启
2. 数据线是否支持数据传输(部分数据线仅支持充电)
3. 手机上弹出的授权框是否已点击「允许」
4. 尝试更换 USB 接口或数据线

### 能打开应用，但无法点击

部分机型需要同时开启两个调试选项才能正常使用：

- **USB 调试**
- **USB 调试(安全设置)**

请在 `设置 → 开发者选项` 中检查这两个选项是否都已启用。

### 文本输入不工作

1. 确保设备已安装 ADB Keyboard
2. 在设置 > 系统 > 语言和输入法 > 虚拟键盘 中启用
3. Agent 会在需要输入时自动切换到 ADB Keyboard

### 截图失败(黑屏)

这通常意味着应用正在显示敏感页面(支付、密码、银行类应用)。Agent 会自动检测并请求人工接管。

### windows 编码异常问题

报错信息形如 `UnicodeEncodeError gbk code`

解决办法: 在运行代码的命令前面加上环境变量: `PYTHONIOENCODING=utf-8`

### 交互模式非TTY环境无法使用

报错形如: `EOF when reading a line`

解决办法: 使用非交互模式直接指定任务, 或者切换到 TTY 模式的终端应用.

### 引用

如果你觉得我们的工作有帮助，请引用以下论文：

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

## 自动化部署指南(面向 AI)

> **本章节专为 AI 助手(如 Claude Code)设计，用于自动化部署 Open-AutoGLM。**
>
> 如果你是人类读者，可以跳过本章节，按照上面的文档操作即可。

---

### 项目概述

Open-AutoGLM 是一个手机 Agent 框架：
- **输入**：用户的自然语言指令(如"打开微信发消息给张三")
- **输出**：自动操作用户的安卓手机完成任务
- **原理**：截图 → 视觉模型理解界面 → 输出点击坐标 → ADB 执行操作 → 循环

架构分为两部分：
1. **Agent 代码**(本仓库)：运行在用户电脑上，负责调用模型、解析动作、控制手机
2. **视觉模型服务**：可以是远程 API，也可以本地部署

---

### 部署前置检查

在开始部署前，请逐项向用户确认以下内容：

#### 硬件环境
- [ ] 用户有一台安卓手机(Android 7.0+)
- [ ] 用户有一根支持数据传输的 USB 数据线(不是仅充电线)
- [ ] 手机和电脑可以通过数据线连接

#### 手机端配置
- [ ] 手机已开启「开发者模式」(设置 → 关于手机 → 连续点击版本号 7 次)
- [ ] 手机已开启「USB 调试」(设置 → 开发者选项 → USB 调试)
- [ ] 部分机型需要同时开启「USB 调试(安全设置)」
- [ ] 手机已安装 ADB Keyboard 应用(下载地址：https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk)
- [ ] ADB Keyboard 已在系统设置中启用(设置 → 语言和输入法 → 启用 ADB Keyboard)

#### 模型服务确认(二选一)

**请明确询问用户：你是否已有可用的 AutoGLM 模型服务？**

- **选项 A：使用已部署的模型服务(推荐)**
  - 用户提供模型服务的 URL(如 `http://xxx.xxx.xxx.xxx:8000/v1`)
  - 无需本地 GPU，无需下载模型
  - 直接使用该 URL 作为 `--base-url` 参数

- **选项 B：本地部署模型(高配置要求)**
  - 需要 NVIDIA GPU(建议 24GB+ 显存)
  - 需要安装 vLLM 或 SGLang
  - 需要下载约 20GB 的模型文件
  - **如果用户是新手或不确定，强烈建议选择选项 A**

---

### 部署流程

#### 阶段一：环境准备

```bash
# 1. 安装 ADB 工具
# MacOS:
brew install android-platform-tools
# 或手动下载：https://developer.android.com/tools/releases/platform-tools

# Windows: 下载后解压，添加到 PATH 环境变量

# 2. 验证 ADB 安装
adb version
# 应输出版本信息

# 3. 连接手机并验证
# 用数据线连接手机，手机上点击「允许 USB 调试」
adb devices
# 应输出设备列表，如：
# List of devices attached
# XXXXXXXX    device
```

**如果 `adb devices` 显示空列表或 unauthorized：**
1. 检查手机上是否弹出授权框，点击「允许」
2. 检查 USB 调试是否开启
3. 尝试更换数据线或 USB 接口
4. 执行 `adb kill-server && adb start-server` 后重试

#### 阶段二：安装 Agent

```bash
# 1. 克隆仓库(如果还没有克隆)
git clone https://github.com/zai-org/Open-AutoGLM.git
cd Open-AutoGLM

# 2. 创建虚拟环境(推荐)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt
pip install -e .
```

**注意：不需要 clone 模型仓库，模型通过 API 调用。**

#### 阶段三：配置模型服务

**如果用户选择选项 A(使用已部署的模型)：**

你可以使用以下第三方模型服务：

1. **智谱 BigModel**
   - 文档：https://docs.bigmodel.cn/cn/api/introduction
   - `--base-url`：`https://open.bigmodel.cn/api/paas/v4`
   - `--model`：`autoglm-phone`
   - `--apikey`：在智谱平台申请你的 API Key

2. **ModelScope(魔搭社区)**
   - 文档：https://modelscope.cn/models/ZhipuAI/AutoGLM-Phone-9B
   - `--base-url`：`https://api-inference.modelscope.cn/v1`
   - `--model`：`ZhipuAI/AutoGLM-Phone-9B`
   - `--apikey`：在 ModelScope 平台申请你的 API Key

使用示例：

```bash
# 使用智谱 BigModel
python main.py --base-url https://open.bigmodel.cn/api/paas/v4 --model "autoglm-phone" --apikey "your-bigmodel-api-key" "打开美团搜索附近的火锅店"

# 使用 ModelScope
python main.py --base-url https://api-inference.modelscope.cn/v1 --model "ZhipuAI/AutoGLM-Phone-9B" --apikey "your-modelscope-api-key" "打开美团搜索附近的火锅店"
```

或者直接使用用户提供的其他模型服务 URL，跳过本地模型部署步骤。

**如果用户选择选项 B(本地部署模型)：**

```bash
# 1. 安装 vLLM
pip install vllm

# 2. 启动模型服务(会自动下载模型，约 20GB)
python3 -m vllm.entrypoints.openai.api_server \
  --served-model-name autoglm-phone-9b \
  --allowed-local-media-path / \
  --mm-encoder-tp-mode data \
  --mm_processor_cache_type shm \
  --mm_processor_kwargs "{\"max_pixels\":5000000}" \
  --max-model-len 25480 \
  --chat-template-content-format string \
  --limit-mm-per-prompt "{\"image\":10}" \
  --model zai-org/AutoGLM-Phone-9B \
  --port 8000

# 模型服务 URL 为：http://localhost:8000/v1
```

#### 阶段四：验证部署

```bash
# 在 Open-AutoGLM 目录下执行
# 将 {MODEL_URL} 替换为实际的模型服务地址

python main.py --base-url {MODEL_URL} --model "autoglm-phone-9b" "打开微信，对文件传输助手发送消息：部署成功"
```

**预期结果：**
- 手机自动打开微信
- 自动搜索「文件传输助手」
- 自动发送消息「部署成功」

---

### 异常处理

| 错误现象 | 可能原因 | 解决方案 |
|---------|---------|---------|
| `adb devices` 无输出 | USB 调试未开启或数据线问题 | 检查开发者选项，更换数据线 |
| `adb devices` 显示 unauthorized | 手机未授权 | 手机上点击「允许 USB 调试」|
| 能打开应用但无法点击 | 缺少安全调试权限 | 开启「USB 调试(安全设置)」|
| 中文输入变成乱码或无输入 | ADB Keyboard 未启用 | 在系统设置中启用 ADB Keyboard |
| 截图返回黑屏 | 敏感页面(支付/银行) | 正常现象，系统会自动处理 |
| 连接模型服务失败 | URL 错误或服务未启动 | 检查 URL，确认服务正在运行 |
| `ModuleNotFoundError` | 依赖未安装 | 执行 `pip install -r requirements.txt` |

---

### 部署要点

1. **优先确认手机连接**：在安装任何代码之前，先确保 `adb devices` 能看到设备
2. **不要跳过 ADB Keyboard**：没有它，中文输入会失败
3. **模型服务是外部依赖**：Agent 代码本身不包含模型，需要单独的模型服务
4. **遇到权限问题先检查手机设置**：大部分问题都是手机端配置不完整
5. **部署完成后用简单任务测试**：建议用「打开微信发消息给文件传输助手」作为验收标准

---

### 命令速查

```bash
# 检查 ADB 连接
adb devices

# 重启 ADB 服务
adb kill-server && adb start-server

# 安装依赖
pip install -r requirements.txt && pip install -e .

# 运行 Agent(交互模式)
python main.py --base-url {MODEL_URL} --model "autoglm-phone-9b"

# 运行 Agent(单次任务)
python main.py --base-url {MODEL_URL} --model "autoglm-phone-9b" "你的任务描述"

# 查看支持的应用列表
python main.py --list-apps
```

---

**部署完成的标志：手机能自动执行用户的自然语言指令。**
