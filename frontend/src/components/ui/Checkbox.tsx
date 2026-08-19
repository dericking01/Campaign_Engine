import { forwardRef, useId } from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/cn";

interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  label?: React.ReactNode;
}

const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(({ label, id, className, ...props }, ref) => {
  const autoId = useId();
  const checkboxId = id ?? autoId;
  return (
    <label htmlFor={checkboxId} className="inline-flex select-none items-center gap-2 cursor-pointer">
      <span className="relative inline-flex h-[18px] w-[18px] shrink-0 items-center justify-center">
        <input
          ref={ref}
          id={checkboxId}
          type="checkbox"
          className={cn(
            "peer h-[18px] w-[18px] appearance-none rounded-[5px] border border-line-strong bg-white",
            "checked:border-brand-800 checked:bg-brand-800",
            "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-300/30",
            "transition-colors cursor-pointer",
            className
          )}
          {...props}
        />
        <Check className="pointer-events-none absolute h-3 w-3 text-white opacity-0 peer-checked:opacity-100 transition-opacity" />
      </span>
      {label && <span className="text-[13.5px] text-ink-muted">{label}</span>}
    </label>
  );
});
Checkbox.displayName = "Checkbox";

export { Checkbox };
