/** Structured debug logger for graceful degradation (never throws). */

export function debug(scope: string, message: string, detail?: unknown): void {
  try {
    if (detail !== undefined) {
      console.debug(`[mango:${scope}] ${message}`, detail);
    } else {
      console.debug(`[mango:${scope}] ${message}`);
    }
  } catch {
    /* ignore */
  }
}
