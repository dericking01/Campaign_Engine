"use client";

import { forwardRef } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "outline" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: React.ReactNode;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "bg-brand-800 text-white shadow-soft hover:bg-brand-900 active:bg-brand-950 focus-visible:ring-brand-400/50",
  secondary:
    "bg-lime-400 text-brand-900 shadow-soft hover:bg-lime-300 active:bg-lime-500 focus-visible:ring-lime-400/50",
  outline:
    "bg-white text-ink border border-line-strong hover:border-brand-300 hover:bg-brand-50 active:bg-brand-100 focus-visible:ring-brand-300/50",
  ghost:
    "bg-transparent text-ink-muted hover:bg-surface-sunken hover:text-ink focus-visible:ring-brand-300/50",
  danger:
    "bg-white text-red-600 border border-red-200 hover:bg-red-50 hover:border-red-300 focus-visible:ring-red-300/50",
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5 rounded-lg",
  md: "h-10 px-4 text-sm gap-2 rounded-lg",
  lg: "h-12 px-6 text-[15px] gap-2 rounded-xl",
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { className, variant = "primary", size = "md", loading, icon, disabled, children, ...props },
    ref
  ) => {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={cn(
          "inline-flex items-center justify-center font-medium transition-all duration-150 ease-out",
          "focus-visible:outline-none focus-visible:ring-4",
          "disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none",
          "active:scale-[0.98]",
          VARIANT_CLASSES[variant],
          SIZE_CLASSES[size],
          className
        )}
        {...props}
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          icon && <span className="shrink-0 [&>svg]:h-4 [&>svg]:w-4">{icon}</span>
        )}
        {children}
      </button>
    );
  }
);
Button.displayName = "Button";

export { Button };
