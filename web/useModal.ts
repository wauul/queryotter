import { useEffect, useRef } from "react";

export function useModal(active: boolean, close: () => void) {
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    if (!active) return;
    const prior = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector<HTMLElement>(
      '.q-overlay [aria-modal="true"]',
    );
    if (!dialog) return;
    const focusable = () =>
      Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],summary,[tabindex="0"]',
        ),
      ).filter((e) => e.getClientRects().length > 0);
    (focusable()[0] || dialog).focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeRef.current();
      }
      if (event.key !== "Tab") return;
      const list = focusable();
      const first = list[0],
        last = list[list.length - 1];
      if (!first) {
        event.preventDefault();
        return;
      }
      if (
        event.shiftKey &&
        (document.activeElement === first ||
          !dialog.contains(document.activeElement))
      ) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last ||
          !dialog.contains(document.activeElement))
      ) {
        event.preventDefault();
        first.focus();
      }
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", keydown);
    return () => {
      document.removeEventListener("keydown", keydown);
      document.body.style.overflow = previousOverflow;
      prior?.focus();
    };
  }, [active]);
}
