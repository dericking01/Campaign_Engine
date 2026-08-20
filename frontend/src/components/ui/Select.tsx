import { forwardRef, useId } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  hint?: string;
}

const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, label, hint, id, children, ...props }, ref) => {
    const autoId = useId();
    const selectId = id ?? autoId;

    return (
      <div className="w-full">
        {label && (
          <label htmlFor={selectId} className="mb-1.5 block text-[13px] font-medium text-ink-muted">
            {label}
          </label>
        )}
        <div className="relative">
          <select
            ref={ref}
            id={selectId}
            aria-describedby={hint ? `${selectId}-hint` : undefined}
            className={cn(
              "h-11 w-full appearance-none rounded-lg border border-line-strong bg-white px-3.5 pr-9 text-[14.5px] text-ink",
              "transition-all duration-150 ease-out",
              "focus:outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-300/20",
              props.disabled && "cursor-not-allowed bg-surface-sunken text-ink-faint",
              className
            )}
            {...props}
          >
            {children}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
        </div>
        {hint && (
          <p id={`${selectId}-hint`} className="mt-1.5 text-[13px] text-ink-faint">
            {hint}
          </p>
        )}
      </div>
    );
  }
);
Select.displayName = "Select";

export { Select };
