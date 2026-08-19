import { AlertCircle, CheckCircle2, Info, XCircle } from "lucide-react";
import { cn } from "@/lib/cn";

type Tone = "info" | "success" | "warning" | "error";

const TONE_CONFIG: Record<Tone, { classes: string; icon: React.ElementType }> = {
  info: { classes: "bg-brand-50 border-brand-200 text-brand-900", icon: Info },
  success: { classes: "bg-lime-50 border-lime-200 text-lime-900", icon: CheckCircle2 },
  warning: { classes: "bg-amber-50 border-amber-200 text-amber-900", icon: AlertCircle },
  error: { classes: "bg-red-50 border-red-200 text-red-900", icon: XCircle },
};

export function Alert({
  tone = "info",
  children,
  className,
}: {
  tone?: Tone;
  children: React.ReactNode;
  className?: string;
}) {
  const { classes, icon: Icon } = TONE_CONFIG[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-3 rounded-lg border px-4 py-3 text-[13.5px] leading-relaxed animate-slide-up",
        classes,
        className
      )}
    >
      <Icon className="mt-0.5 h-[18px] w-[18px] shrink-0" aria-hidden="true" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}
