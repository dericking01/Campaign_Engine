import { cn } from "@/lib/cn";

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-14 text-center", className)}>
      {icon && (
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-surface-sunken text-ink-faint [&>svg]:h-6 [&>svg]:w-6">
          {icon}
        </div>
      )}
      <p className="text-[14.5px] font-medium text-ink">{title}</p>
      {description && <p className="mt-1.5 max-w-sm text-[13.5px] text-ink-muted">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
