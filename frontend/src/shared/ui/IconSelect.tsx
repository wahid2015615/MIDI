"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { TypeIcon } from "./TypeIcon";

type IconKind = "style" | "mood" | "mode" | "track" | "instrument" | "midiType";

export function IconSelect({
  value,
  options,
  onChange,
  kind,
  ariaLabel,
  disabled,
  getLabel,
}: {
  value: string;
  options: string[];
  onChange: (value: string) => void;
  kind: IconKind;
  ariaLabel?: string;
  disabled?: boolean;
  getLabel?: (value: string) => string;
}) {
  const [open, setOpen] = useState(false);
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0, width: 0, maxH: 280 });
  const btnRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLUListElement | null>(null);
  const listId = useId();
  const labelOf = getLabel ?? ((v: string) => v);

  function computeMenuPos() {
    const btn = btnRef.current;
    if (!btn) return null;
    const rect = btn.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom - 12;
    const spaceAbove = rect.top - 12;
    const maxH = Math.min(320, Math.max(160, spaceBelow > 180 ? spaceBelow : spaceAbove));
    const openUp = spaceBelow < 180 && spaceAbove > spaceBelow;
    return {
      top: openUp ? Math.max(8, rect.top - maxH - 6) : rect.bottom + 6,
      left: Math.max(8, Math.min(rect.left, window.innerWidth - Math.max(rect.width, 220) - 8)),
      width: Math.max(rect.width, 220),
      maxH,
    };
  }

  function placeMenu() {
    const next = computeMenuPos();
    if (next) setMenuPos(next);
  }

  useEffect(() => {
    if (!open) return;
    placeMenu();
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (btnRef.current?.contains(t) || menuRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const onWin = () => placeMenu();
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", onWin);
    window.addEventListener("scroll", onWin, true);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onWin);
      window.removeEventListener("scroll", onWin, true);
    };
  }, [open]);

  return (
    <div className="icon-select">
      <button
        ref={btnRef}
        type="button"
        className="icon-select-btn field-input"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        disabled={disabled}
        onClick={() => {
          if (open) {
            setOpen(false);
            return;
          }
          const pos = computeMenuPos();
          if (!pos) return;
          setMenuPos(pos);
          setOpen(true);
        }}
      >
        <span className="icon-select-value">
          <TypeIcon kind={kind} name={value} />
          <span>{labelOf(value)}</span>
        </span>
        <svg
          className={`icon-select-chevron${open ? " is-open" : ""}`}
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden
        >
          <path
            d="M6 9l6 6 6-6"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      {open &&
        menuPos.width > 0 &&
        typeof document !== "undefined" &&
        createPortal(
          <ul
            ref={menuRef}
            id={listId}
            role="listbox"
            aria-label={ariaLabel}
            className="icon-select-menu"
            style={{
              top: menuPos.top,
              left: menuPos.left,
              width: menuPos.width,
              maxHeight: menuPos.maxH,
            }}
          >
            {options.map((opt) => {
              const selected = opt === value;
              return (
                <li key={opt} role="presentation">
                  <button
                    type="button"
                    role="option"
                    aria-selected={selected}
                    className={`icon-select-option${selected ? " is-selected" : ""}`}
                    onClick={() => {
                      onChange(opt);
                      setOpen(false);
                    }}
                  >
                    <span className="icon-select-check" aria-hidden>
                      {selected ? (
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
                          <path
                            d="M5 12.5 9.5 17 19 7"
                            stroke="currentColor"
                            strokeWidth="2.2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      ) : null}
                    </span>
                    <TypeIcon kind={kind} name={opt} />
                    <span className="icon-select-label">{labelOf(opt)}</span>
                  </button>
                </li>
              );
            })}
          </ul>,
          document.body,
        )}
    </div>
  );
}
