import { toBlob } from "html-to-image";

/** Copy a rendered card to the clipboard as a PNG, or download it where copying is not allowed.
 * Safari accepts a clipboard write only inside the click, so the image is handed over as a promise. */
export async function copyNodeAsPng(node: HTMLElement, filename: string): Promise<"copied" | "saved"> {
  const bg = getComputedStyle(document.documentElement).getPropertyValue("--surface").trim() || "#ffffff";
  // 4K wide (3,840 px) whatever the screen: a 720 px card at the old 2x was 1,440 px (owner, 2026-10-21). A tall card
  // with its full analysis is kept under the 16,384 px canvas limit browsers allow.
  const { width, height } = node.getBoundingClientRect();
  const pixelRatio = Math.max(2, Math.min(3840 / Math.max(width, 1), 16000 / Math.max(height, 1), 6));
  const render = toBlob(node, {
    pixelRatio, backgroundColor: bg,
    filter: (n) => !(n instanceof HTMLElement && n.dataset.noexport === "true"),
  }).then((blob) => {
    if (!blob) throw new Error("render failed");
    return blob;
  });
  if (navigator.clipboard && "ClipboardItem" in window) {
    try {
      await navigator.clipboard.write([new ClipboardItem({ "image/png": render })]);
      return "copied";
    } catch {
      /* fall through to a download */
    }
  }
  const url = URL.createObjectURL(await render);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
  return "saved";
}
