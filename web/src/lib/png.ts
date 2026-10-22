import { toBlob } from "html-to-image";

// 8K wide (7,680 px) whatever the screen (owner, 2026-10-22: "8K or more", a 4K image looked blurred on WhatsApp).
// What blurred it was its height: WhatsApp scales a photo to about 1,600 px on its long side (4,096 px with HD), so a
// card with its full analysis, 4-8 times taller than wide, kept a few pixels per letter. The image is now the card's
// face only, and the size steps down to what the browser's canvas allows: Safari on a phone refuses a canvas over
// 16.7M pixels, desktop browsers one side over 16,384 px or ~100M pixels in all.
const TARGET_WIDTH = 7680;
const MAX_SIDE = 16384;
const mobileSafari = () => /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const maxArea = () => (mobileSafari() ? 16_000_000 : 100_000_000);

/** The pixel ratio for a node: 8K wide where the canvas allows it; the canvas limits always win. */
export function exportRatio(width: number, height: number, area = 100_000_000): number {
  const w = Math.max(width, 1), h = Math.max(height, 1);
  return Math.min(TARGET_WIDTH / w, MAX_SIDE / w, MAX_SIDE / h, Math.sqrt(area / (w * h)));
}

async function render(node: HTMLElement): Promise<Blob> {
  const bg = getComputedStyle(document.documentElement).getPropertyValue("--surface").trim() || "#ffffff";
  const { width, height } = node.getBoundingClientRect();
  let ratio = exportRatio(width, height, maxArea());
  // a browser that runs out of canvas memory hands back nothing or a blank: try again smaller, down to 2x
  for (;;) {
    try {
      const blob = await toBlob(node, {
        pixelRatio: ratio, backgroundColor: bg,
        filter: (n) => !(n instanceof HTMLElement && n.dataset.noexport === "true"),
      });
      if (blob && blob.size > 1000) return blob;
    } catch {
      /* smaller next */
    }
    if (ratio <= 1) throw new Error("render failed");
    ratio = Math.max(1, ratio / 1.5);
  }
}

/** Share a rendered card as a PNG: the phone's share sheet where there is one (WhatsApp, as a photo or a document),
 *  else the clipboard, else a download. Safari accepts a clipboard write only inside the click, so the image is handed
 *  over as a promise. */
export async function copyNodeAsPng(node: HTMLElement, filename: string): Promise<"copied" | "saved" | "shared"> {
  const image = render(node);
  const touch = matchMedia("(pointer: coarse)").matches;
  if (touch && typeof navigator.canShare === "function") {
    const file = new File([await image], filename, { type: "image/png" });
    if (navigator.canShare({ files: [file] })) {
      try {
        await navigator.share({ files: [file] });
        return "shared";
      } catch (err) {
        if ((err as Error)?.name === "AbortError") return "shared";
      }
    }
  }
  if (!touch && navigator.clipboard && "ClipboardItem" in window) {
    try {
      await navigator.clipboard.write([new ClipboardItem({ "image/png": image })]);
      return "copied";
    } catch {
      /* fall through to a download */
    }
  }
  const url = URL.createObjectURL(await image);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
  return "saved";
}

/** The card as a PDF through the browser's own print to PDF: its text stays text, sharp at any zoom, and goes to
 *  WhatsApp as a document. Only the marked node prints (index.css, `body.printing-card`). */
export function printNode(node: HTMLElement, done: () => void): void {
  node.dataset.printing = "true";
  document.body.classList.add("printing-card");
  let cleaned = false;
  const clean = () => {
    if (cleaned) return;
    cleaned = true;
    delete node.dataset.printing;
    document.body.classList.remove("printing-card");
    window.removeEventListener("afterprint", clean);
    done();
  };
  window.addEventListener("afterprint", clean);
  window.print();
  // browsers that never send afterprint (some phones) are cleaned up when focus returns
  setTimeout(() => window.addEventListener("focus", clean, { once: true }), 500);
}
