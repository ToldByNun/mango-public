import type { MangoBridge } from "@shared/ipc-schema";

export type { MangoBridge, GgufModel } from "@shared/ipc-schema";

declare global {
  interface Window {
    mango: MangoBridge;
  }
}

export {};
