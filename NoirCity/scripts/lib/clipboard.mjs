import { spawnSync } from "node:child_process";

/**
 * Puts text on the system clipboard, if the platform lets us.
 *
 * Returns whether it worked. Never throws and never blocks the caller: the
 * prompt is written to a file regardless, and the clipboard is a convenience
 * on top of that rather than the way the tool works.
 */
export function copyToClipboard(text) {
  const cmd =
    process.platform === "win32"
      ? { file: "clip", args: [] }
      : process.platform === "darwin"
        ? { file: "pbcopy", args: [] }
        : { file: "xclip", args: ["-selection", "clipboard"] };

  try {
    const r = spawnSync(cmd.file, cmd.args, { input: text, shell: true });
    return r.status === 0;
  } catch {
    return false;
  }
}
