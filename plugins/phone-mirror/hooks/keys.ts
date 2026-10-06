export type KeyAction =
  | { type: "text"; text: string }
  | { type: "keycode"; keycode: number };

const ANDROID_KEYCODES: Record<string, number> = {
  return: 66,      // KEYCODE_ENTER
  enter: 66,
  backspace: 67,   // KEYCODE_DEL
  delete: 67,
  up: 19,          // KEYCODE_DPAD_UP
  down: 20,        // KEYCODE_DPAD_DOWN
  left: 21,        // KEYCODE_DPAD_LEFT
  right: 22,       // KEYCODE_DPAD_RIGHT
  tab: 61,         // KEYCODE_TAB
  escape: 4,       // KEYCODE_BACK
};

function actionFor(key: string): KeyAction | undefined {
  const keycode = ANDROID_KEYCODES[key.toLowerCase()];
  if (keycode !== undefined) {
    return { type: "keycode", keycode };
  }

  if (key === "space") {
    return { type: "text", text: " " };
  }

  // Single typed character (letter, digit, symbol)
  if ([...key].length === 1) {
    return { type: "text", text: key };
  }

  return undefined;
}

// Convert pressed terminal keys into batch device actions, merging consecutive text characters
export function keysToActions(keys: string[]): KeyAction[] {
  const actions: KeyAction[] = [];
  for (const key of keys) {
    const action = actionFor(key);
    if (!action) {
      continue;
    }

    const last = actions[actions.length - 1];
    if (action.type === "text" && last?.type === "text") {
      actions[actions.length - 1] = {
        type: "text",
        text: last.text + action.text,
      };
    } else {
      actions.push(action);
    }
  }
  return actions;
}
