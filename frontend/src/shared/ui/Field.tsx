import type { ReactNode } from "react";

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-baseline justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">
          {label}
        </span>
        {hint ? (
          <span className="text-[11px] font-medium text-[var(--muted)]">{hint}</span>
        ) : null}
      </span>
      {children}
    </label>
  );
}
