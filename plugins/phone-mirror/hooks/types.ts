export type Shot = {
  file: string;
  generation: number;
  width: number;
  height: number;
};

export type Target = {
  id: string;
  screenWidth: number;
  screenHeight: number;
};

export type TapMessage = {
  x: number;
  y: number;
};

export type KeysMessage = {
  keys: string[];
};

declare module "claude-code" {
  interface PluginState {
    "phone-mirror": {
      shot: Shot;
      target: Target | null;
      streamId: number;
      isAskingUrl: boolean;
    };
  }
}
