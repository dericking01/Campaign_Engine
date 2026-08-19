"use client";

import { forwardRef, useId, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { cn } from "@/lib/cn";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  icon?: React.ReactNode;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, hint, icon, id, ...props }, ref) => {
    const autoId = useId();
    const inputId = id ?? autoId;

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="mb-1.5 block text-[13px] font-medium text-ink-muted"
          >
            {label}
          </label>
        )}
        <div className="relative">
          {icon && (
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint [&>svg]:h-[18px] [&>svg]:w-[18px]">
              {icon}
            </span>
          )}
          <input
            ref={ref}
            id={inputId}
            aria-invalid={!!error}
            aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
            className={cn(
              "h-11 w-full rounded-lg border bg-white px-3.5 text-[14.5px] text-ink placeholder:text-ink-faint",
              "transition-all duration-150 ease-out",
              "focus:outline-none focus:ring-4",
              icon ? "pl-10" : undefined,
              error
                ? "border-red-300 focus:border-red-400 focus:ring-red-400/15"
                : "border-line-strong focus:border-brand-400 focus:ring-brand-300/20",
              props.disabled && "cursor-not-allowed bg-surface-sunken text-ink-faint",
              className
            )}
            {...props}
          />
        </div>
        {error && (
          <p id={`${inputId}-error`} className="mt-1.5 text-[13px] text-red-600">
            {error}
          </p>
        )}
        {!error && hint && (
          <p id={`${inputId}-hint`} className="mt-1.5 text-[13px] text-ink-faint">
            {hint}
          </p>
        )}
      </div>
    );
  }
);
Input.displayName = "Input";

const PasswordInput = forwardRef<HTMLInputElement, InputProps>((props, ref) => {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <Input ref={ref} type={visible ? "text" : "password"} className="pr-11" {...props} />
      <button
        type="button"
        tabIndex={-1}
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Hide password" : "Show password"}
        className={cn(
          "absolute right-3 text-ink-faint hover:text-ink-muted transition-colors",
          props.label ? "top-[38px]" : "top-1/2 -translate-y-1/2"
        )}
      >
        {visible ? <EyeOff className="h-[18px] w-[18px]" /> : <Eye className="h-[18px] w-[18px]" />}
      </button>
    </div>
  );
});
PasswordInput.displayName = "PasswordInput";

export { Input, PasswordInput };
