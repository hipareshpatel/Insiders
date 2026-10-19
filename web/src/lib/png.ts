import { toBlob } from "html-to-image";

/** Copy a rendered card to the clipboard as a PNG, or download it where copying is not allowed.
 * Safari accepts a clipboard write only inside the click, so the image is handed over as a promise. */
export async function copyNodeAsPng(node: HTMLElement, filename: string): Promise<"copied" | "saved"> {
  const bg = getComputedStyle(document.documentElement).getPropertyValue("--surface").trim() || "#ffffff";
  const render = toBlob(node, {
    pixelRatio: 2, backgroundColor: bg,
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
