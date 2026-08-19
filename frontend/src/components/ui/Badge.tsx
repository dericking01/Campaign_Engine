import { cn } from "@/lib/cn";

type Tone = "neutral" | "success" | "warning" | "danger" | "brand";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-surface-sunken text-ink-muted",
  success: "bg-lime-100 text-lime-800",
  warning: "bg-amber-100 text-amber-800",
  danger: "bg-red-50 text-red-700",
  brand: "bg-brand-100 text-brand-800",
};

/** Maps common backend status strings to a sensible tone automatically -
 * pages can still pass `tone` explicitly to override. */
function toneForStatus(status: string): Tone {
  const s = status.toUpperCase();
  if (["READY", "OK", "ACTIVE", "COMPLETED", "SENT"].includes(s)) return "success";
  if (["REJECTED", "FAILED", "DEAD", "ERROR"].includes(s)) return "danger";
  if (["PENDING", "VALIDATING", "COMMITTING", "QUEUED", "RETRYING"].includes(s)) return "warning";
  return "neutral";
}

export function Badge({
  children,
  tone,
  className,
}: {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}) {
  const resolvedTone = tone ?? (typeof children === "string" ? toneForStatus(children) : "neutral");
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-[12px] font-medium",
        TONE_CLASSES[resolvedTone],
        className
      )}
    >
      {children}
    </span>
  );
}
