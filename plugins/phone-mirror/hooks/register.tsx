import { atom, read, update } from "claude-code";
import type { EngineInterface, Register } from "claude-code";

import type { KeysMessage, Shot, TapMessage, Target } from "./types";
import { keysToActions } from "./keys";
import { fitInside, pngSize } from "./png";

const COMMAND = "phone-mirror";
const PANE = "phone-mirror";
const VIEW_KEY = "view";
const TAP_KEY = "tap";

// Frames rotate through 3 temporary files so the terminal never reads a half-written file
const FRAME_FILES = 3;
const TOOLBAR_ROWS = 1;
const URL_FIELD_ROWS = 1;
const RETRY_AFTER_ERROR_MS = 1000;

// Managed in plugin state across live reloads
const target = atom({ plugin: "phone-mirror", key: "target" } as const, null as Target | null);
const streamId = atom({ plugin: "phone-mirror", key: "streamId" } as const, 0);
const isAskingUrl = atom({ plugin: "phone-mirror", key: "isAskingUrl" } as const, false);
const shot = atom(
  { plugin: "phone-mirror", key: "shot" } as const,
  { file: "", generation: 0, width: 1, height: 1 } as Shot,
);

function frameFile(generation: number): string {
  return `/tmp/phone-mirror-${generation % FRAME_FILES}.png`;
}

function decodeBase64(b64: string): Uint8Array {
  if (typeof globalThis !== "undefined" && "Buffer" in globalThis) {
    return new Uint8Array((globalThis as any).Buffer.from(b64, "base64"));
  }
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

async function resolveDevice(
  $: EngineInterface,
  wanted?: string,
): Promise<Target | null> {
  const listProc = await $.process.run(["/bin/sh", "-c", "adb devices"]);
  if (listProc.exitCode !== 0) {
    return null;
  }

  const lines = (listProc.stdout || "").split("\n").slice(1);
  const onlineDevices: string[] = [];
  for (const line of lines) {
    const parts = line.trim().split(/\s+/);
    if (parts.length >= 2 && parts[1] === "device" && parts[0]) {
      onlineDevices.push(parts[0]);
    }
  }

  if (onlineDevices.length === 0) {
    return null;
  }

  let chosenId: string | null = null;
  if (wanted && wanted.trim().length > 0) {
    const cleanWanted = wanted.trim();
    chosenId = onlineDevices.find((d) => d === cleanWanted) ?? null;
  } else {
    chosenId = onlineDevices[0] ?? null;
  }

  if (!chosenId) {
    return null;
  }

  // Probe actual physical screen size
  let screenWidth = 1080;
  let screenHeight = 2400;
  try {
    const wmProc = await $.process.run([
      "/bin/sh",
      "-c",
      `adb -s ${chosenId} shell wm size`,
    ]);
    const match = /(?:Physical size|Override size):\s*(\d+)x(\d+)/i.exec(
      wmProc.stdout || "",
    );
    if (match) {
      screenWidth = Number(match[1]);
      screenHeight = Number(match[2]);
    }
  } catch {
    // Fallback to default
  }

  return { id: chosenId, screenWidth, screenHeight };
}

async function sendAdbKey(
  $: EngineInterface,
  deviceId: string,
  keycode: number,
  label: string,
): Promise<void> {
  try {
    const proc = await $.process.run([
      "/bin/sh",
      "-c",
      `adb -s ${deviceId} shell input keyevent ${keycode}`,
    ]);
    if (proc.exitCode !== 0) {
      $.ui.toast(proc.stderr || `执行 ${label} 失败`);
    }
  } catch (err) {
    $.ui.toast(`${label} 错误: ${String(err)}`);
  }
}

async function sendAdbTap(
  $: EngineInterface,
  deviceId: string,
  x: number,
  y: number,
): Promise<void> {
  try {
    await $.process.run([
      "/bin/sh",
      "-c",
      `adb -s ${deviceId} shell input tap ${x} ${y}`,
    ]);
  } catch (err) {
    $.ui.toast(`点击失败: ${String(err)}`);
  }
}

async function sendAdbText(
  $: EngineInterface,
  deviceId: string,
  text: string,
): Promise<void> {
  try {
    const escaped = text
      .replace(/ /g, "%s")
      .replace(/([&|;()<>$"'\\])/g, "\\$1");
    await $.process.run([
      "/bin/sh",
      "-c",
      `adb -s ${deviceId} shell input text "${escaped}"`,
    ]);
  } catch (err) {
    $.ui.toast(`输入失败: ${String(err)}`);
  }
}

export const register: Register = (on) => {
  let typing: Promise<void> = Promise.resolve();

  on("session.start", async ($, e, next) => {
    await $.command.register({
      name: COMMAND,
      description: "手机屏幕实时镜像：高清画面推流、鼠标点击、键盘打字与导航按键",
      argumentHint: "[device-id]",
    });
    return next(e);
  });

  on("command.run", { command: COMMAND }, async ($, e) => {
    const wanted = e.args?.trim() || undefined;
    const device = await resolveDevice($, wanted);

    if (!device) {
      const listProc = await $.process.run(["/bin/sh", "-c", "adb devices"]);
      return {
        text: `未发现可用的在线 Android 设备${wanted ? ` "${wanted}"` : ""}。\n当前 adb 输出:\n${listProc.stdout || listProc.stderr || "无"}`,
      };
    }

    await update($, target, () => device);
    await update($, isAskingUrl, () => false);
    const id = await update($, streamId, (n) => n + 1);

    const captureFrame = async (generation: number): Promise<boolean> => {
      const file = frameFile(generation);
      const screencapCmd = `adb -s ${device.id} exec-out screencap -p > ${file}`;
      const proc = await $.process.run(["/bin/sh", "-c", screencapCmd]);
      if (proc.exitCode !== 0) {
        return false;
      }

      const fileData = await $.fs.read(file, { as: "bytes" });
      if (!fileData || typeof fileData.base64 !== "string" || fileData.base64.length === 0) {
        return false;
      }

      const bytes = decodeBase64(fileData.base64);
      const size = pngSize(bytes);
      const current = await read($, shot);

      // Trigger full redraw on initial frame or rotation/resolution changes;
      // otherwise use $.ui.blit to smoothly update pixels in place without terminal flicker.
      if (
        current.generation === 0 ||
        current.width !== size.width ||
        current.height !== size.height
      ) {
        await update($, shot, () => ({ file, generation, ...size }));
      } else {
        await $.ui.blit({
          requestId: PANE,
          key: VIEW_KEY,
          source: { file, format: "png", generation },
        }).catch(() => {});
      }

      return true;
    };

    const stream = async () => {
      // Loop continually while current streamId matches; grab next frame as soon as previous frame completes
      for (let generation = 1; id === (await read($, streamId)); generation++) {
        const isShown = await captureFrame(generation).catch(() => false);
        if (!isShown) {
          await $.clock.sleep(RETRY_AFTER_ERROR_MS);
        }
      }
    };

    await update($, shot, () => ({ file: "", generation: 0, width: 1, height: 1 }));
    void stream();
    await $.ui.open({ id: PANE, title: `Phone Mirror · ${device.id}` });

    return {
      text: `已连接设备 ${device.id} (${device.screenWidth}x${device.screenHeight})。鼠标直接点击画面即可操作，聚焦后敲击键盘输入。`,
    };
  });

  on("ui.message", async ($, e) => {
    const device = await read($, target);
    if (e.element !== TAP_KEY || !device) {
      return {};
    }

    if ("keys" in (e.data as object)) {
      const actions = keysToActions((e.data as KeysMessage).keys);
      typing = typing.then(async () => {
        for (const action of actions) {
          if (action.type === "text") {
            await sendAdbText($, device.id, action.text);
          } else {
            await sendAdbKey($, device.id, action.keycode, `Key ${action.keycode}`);
          }
        }
      });
      return {};
    }

    const tap = e.data as TapMessage;
    const x = Math.round(tap.x * device.screenWidth);
    const y = Math.round(tap.y * device.screenHeight);
    await sendAdbTap($, device.id, x, y);
    return {};
  });

  on("ui.close", async ($, e, next) => {
    if (e.id === PANE) {
      await update($, streamId, (n) => n + 1);
    }
    return next(e);
  });

  on("ui.render", { component: "Pane", requestId: PANE }, async ($, e) => {
    const ui = $.ui.resolve(e);
    const { Box, Text } = ui;

    if (e.surface !== "terminal" || !("Image" in ui)) {
      return <Text>Phone Mirror 需要终端图形协议支持（如 Ghostty 或 kitty）</Text>;
    }

    const { Button, Input } = ui as any;

    const { file, generation, width, height } = await read($, shot);
    if (generation === 0) {
      return <Text dimColor>正在等待设备首帧画面...</Text>;
    }

    const device = await read($, target);
    if (!device) {
      return <Text dimColor>运行 /phone-mirror 选择设备</Text>;
    }

    const isAsking = await read($, isAskingUrl);
    const roomForImage =
      (e.props?.scroll?.bodyRows ?? 35) -
      TOOLBAR_ROWS -
      (isAsking ? URL_FIELD_ROWS : 0);
    const colsLimit = e.props?.bodyColumns ?? 45;
    const size = fitInside(colsLimit, roomForImage, width, height);

    const press = (keycode: number, label: string) => () =>
      sendAdbKey($, device.id, keycode, label);

    const openUrl = async (url: string) => {
      await update($, isAskingUrl, () => false);
      const cleanUrl = url.trim();
      if (!cleanUrl) return;

      if (!cleanUrl.startsWith("http://") && !cleanUrl.startsWith("https://")) {
        $.ui.toast("请输入以 http:// 或 https:// 开头的完整 URL");
        return;
      }

      const safeUrl = cleanUrl.replace(/'/g, "'\\''");
      const cmd = `adb -s ${device.id} shell am start -a android.intent.action.VIEW -d '${safeUrl}'`;
      const proc = await $.process.run(["/bin/sh", "-c", cmd]);
      if (proc.exitCode !== 0) {
        $.ui.toast(`打开网页失败: ${proc.stderr || "未知错误"}`);
      } else {
        $.ui.toast(`已在设备打开: ${cleanUrl}`);
      }
    };

    return (
      <Box flexDirection="column">
        <Box flexDirection="row" gap={1}>
          <Button key="home" label="Home" onPress={press(3, "Home")} />
          <Button key="back" label="Back" onPress={press(4, "Back")} />
          <Button
            key="app-switch"
            label="App Switch"
            onPress={press(187, "App Switch")}
          />
          <Button
            key="url"
            label="URL"
            onPress={() => update($, isAskingUrl, (asking) => !asking)}
          />
          <Button
            key="refresh"
            label="Refresh"
            onPress={() => $.ui.invalidate("ui.render")}
          />
        </Box>
        {isAsking && (
          <Input
            key="url-field"
            label="URL "
            placeholder="https://example.com"
            submitLabel="打开"
            autoFocus
            onSubmit={openUrl}
          />
        )}
        <Box>
          <ui.Image
            key={VIEW_KEY}
            source={{ file, format: "png", generation }}
            columns={size.columns}
            rows={size.rows}
            alt="Android Screen"
          />
          <Box position="absolute" top={0} left={0}>
            <ui.Client
              key={TAP_KEY}
              module="./tap.tsx"
              width={size.columns}
              height={size.rows}
            />
          </Box>
        </Box>
      </Box>
    );
  });
};
