"use client";

import type { Session } from "@/lib/api";

interface ProgressBarProps {
  session: Session;
}

export function ProgressBar({ session }: ProgressBarProps) {
  const pct = session.total > 0 ? Math.round((session.done / session.total) * 100) : 0;
  const label =
    session.type === "discover"
      ? `Découverte en cours… ${session.done} / ${session.total} sites`
      : `Scraping en cours… ${session.done} / ${session.total} tâches`;

  return (
    <div className="rounded-md border bg-muted/30 p-3 space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span className="text-foreground font-medium">{label}</span>
        <span className="text-muted-foreground tabular-nums">{pct}%</span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full bg-primary transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
