"use client";

import { useState } from "react";

export interface BarSegment {
  key: string;
  label: string;
  value: number;
  color: string;
}

export interface BarRow {
  category: string;
  segments: BarSegment[];
}

/** Horizontal stacked bar chart - thin marks (24px), 2px surface gaps
 * between segments, 4px rounded data-end on the bar's outward tip only
 * (baseline stays square), per-segment hover tooltip with a lift effect,
 * legend for the (up to 2+) series. See the dataviz skill's
 * marks-and-anatomy.md / interaction.md - this mirrors both. */
export function StackedBarChart({ rows, legend }: { rows: BarRow[]; legend: BarSegment[] }) {
  const [hover, setHover] = useState<{ category: string; segment: BarSegment } | null>(null);
  const max = Math.max(1, ...rows.map((r) => r.segments.reduce((s, seg) => s + seg.value, 0)));

  return (
    <div>
      {legend.length > 1 && (
        <div className="mb-4 flex flex-wrap gap-x-4 gap-y-1.5">
          {legend.map((l) => (
            <span key={l.key} className="flex items-center gap-1.5 text-[12px] text-ink-muted">
              <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ backgroundColor: l.color }} />
              {l.label}
            </span>
          ))}
        </div>
      )}
      <div className="space-y-3">
        {rows.map((row) => {
          const total = row.segments.reduce((s, seg) => s + seg.value, 0);
          return (
            <div key={row.category} className="flex items-center gap-3">
              <span className="w-24 shrink-0 truncate text-[12.5px] text-ink-muted" title={row.category}>
                {row.category}
              </span>
              <div className="flex h-6 flex-1 items-center gap-[2px]">
                {total === 0 ? (
                  <div className="h-4 w-full rounded-[4px] bg-surface-sunken" />
                ) : (
                  row.segments
                    .filter((seg) => seg.value > 0)
                    .map((seg, i, arr) => {
                      const widthPct = (seg.value / max) * 100;
                      const isLast = i === arr.length - 1;
                      const isHovered = hover?.category === row.category && hover.segment.key === seg.key;
                      return (
                        <button
                          key={seg.key}
                          type="button"
                          onMouseEnter={() => setHover({ category: row.category, segment: seg })}
                          onMouseLeave={() => setHover(null)}
                          onFocus={() => setHover({ category: row.category, segment: seg })}
                          onBlur={() => setHover(null)}
                          className="relative h-4 min-w-[3px] shrink-0 transition-[filter,opacity] focus:outline-none"
                          style={{
                            width: `${widthPct}%`,
                            backgroundColor: seg.color,
                            borderTopRightRadius: isLast ? 4 : 0,
                            borderBottomRightRadius: isLast ? 4 : 0,
                            filter: isHovered ? "brightness(0.88)" : undefined,
                          }}
                          aria-label={`${row.category} · ${seg.label}: ${seg.value.toLocaleString()}`}
                        >
                          {isHovered && (
                            <span className="pointer-events-none absolute -top-9 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-md bg-ink px-2.5 py-1.5 text-[11.5px] text-white shadow-lifted">
                              <strong className="font-semibold">{seg.value.toLocaleString()}</strong>{" "}
                              <span className="text-white/70">{seg.label}</span>
                            </span>
                          )}
                        </button>
                      );
                    })
                )}
              </div>
              <span className="w-14 shrink-0 text-right text-[12.5px] font-medium text-ink">
                {total.toLocaleString()}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
