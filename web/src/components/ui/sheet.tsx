import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export function Sheet({
  open, onOpenChange, title, description, children, className,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[1px]" />
        <Dialog.Content
          className={cn(
            "fixed inset-y-0 right-0 z-50 flex w-full max-w-[1040px] flex-col border-l border-line bg-bg shadow-2xl outline-none",
            className,
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line bg-surface px-5 py-4">
            <div className="min-w-0">
              <Dialog.Title className="font-display text-lg font-bold text-ink">{title}</Dialog.Title>
              {description ? <Dialog.Description asChild><div className="mt-1 text-sm text-ink-2">{description}</div></Dialog.Description> : null}
            </div>
            <Dialog.Close className="rounded-md p-1.5 text-ink-2 hover:bg-surface-2 hover:text-ink" aria-label="Close">
              <X className="h-5 w-5" />
            </Dialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
