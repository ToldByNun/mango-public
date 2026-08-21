/** Strip model think wrappers and tool junk from visible thought text. */

const THINK_TAG = "(?:redacted_thinking|think(?:ing)?)";
const THINK_BLOCK_RE = new RegExp(
  `<\\s*${THINK_TAG}\\b[^>]*>([\\s\\S]*?)<\\s*\\/\\s*${THINK_TAG}\\s*>`,
  "gi",
);
const THINK_OPEN_OR_CLOSE_RE = new RegExp(`<\\s*\\/?\\s*${THINK_TAG}\\b[^>]*>`, "gi");
const THINK_PARTIAL_END_RE = new RegExp(`<\\s*\\/?\\s*${THINK_TAG}\\b[^>]*$`, "i");
const CHANNEL_RE = /<\|?channel\|?>/gi;

export function stripThoughtMarkup(text: string): string {
  const cut = text.search(/<tool_call\b/i);
  const head = cut >= 0 ? text.slice(0, cut) : text;
  const dump = head.search(/[A-Za-z_][\w.]*\([^)]*\)\s*\|/);
  const untilDump = dump >= 0 ? head.slice(0, dump) : head;
  let cleaned = untilDump
    .replace(CHANNEL_RE, "")
    .replace(THINK_BLOCK_RE, "$1")
    .replace(THINK_OPEN_OR_CLOSE_RE, "")
    .replace(THINK_PARTIAL_END_RE, "")
    .replace(/<[^>]*$/i, "")
    .replace(/```[\w+-]*\n[\s\S]*?```/g, "")
    .replace(/<tool(?:_call\b[\s\S]*)?$/i, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  return cleaned;
}

export function isEmptyThought(text: string): boolean {
  return !stripThoughtMarkup(text).trim();
}
