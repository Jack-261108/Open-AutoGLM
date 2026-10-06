import type { ClientKeyEvent, ClientPointerEvent, ClientSurface } from "claude-code";

type Pending = { keys: string[] };

const FLUSH_MS = 50;

// Overlaid on the screenshot: posts left-click as fraction (0..1) of picture dimensions,
// and buffers keystrokes typed while focused.
export default function TapInput(_props: unknown, surface: ClientSurface<Pending>) {
  if (surface.state === undefined) {
    const pending: Pending = { keys: [] };

    surface.onPointer((e: ClientPointerEvent) => {
      if (
        e.type !== "down" ||
        e.button !== "left" ||
        surface.columns === 0 ||
        surface.rows === 0
      ) {
        return;
      }

      const x = e.fine?.x ?? e.x + 0.5;
      const y = e.fine?.y ?? e.y + 0.5;
      surface.post({ x: x / surface.columns, y: y / surface.rows });
    });

    surface.onKey((e: ClientKeyEvent) => {
      pending.keys.push(e.key);
    });

    surface.every(FLUSH_MS, () => {
      if (pending.keys.length === 0) {
        return;
      }
      surface.post({ keys: pending.keys.splice(0) });
    });

    surface.setState(pending);
  }

  const { Box } = surface.elements;
  return <Box width="100%" height="100%" />;
}
