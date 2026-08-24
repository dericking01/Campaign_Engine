"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";

const LENGTH = 4;

/** 4-character OTP entry (3 digits + 1 capital letter, in any position) -
 * one box per character with auto-advance focus. Calls onComplete the
 * moment all 4 boxes are filled (auto-verify - no need to click
 * anything), but the value is also exposed via onChange so a page can
 * still offer an explicit Confirm button as a fallback (e.g. after a
 * failed attempt, or for a user who prefers to double-check before
 * submitting). */
export function OtpInput({
  onComplete,
  onChange,
  disabled,
  autoFocus = true,
  reset,
}: {
  onComplete: (code: string) => void;
  onChange?: (code: string) => void;
  disabled?: boolean;
  autoFocus?: boolean;
  reset?: number;
}) {
  const [values, setValues] = useState<string[]>(Array(LENGTH).fill(""));
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);
  const firedRef = useRef(false);

  useEffect(() => {
    setValues(Array(LENGTH).fill(""));
    firedRef.current = false;
    inputRefs.current[0]?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reset]);

  function setAt(index: number, char: string) {
    const next = [...values];
    next[index] = char;
    setValues(next);
    onChange?.(next.join(""));

    const code = next.join("");
    if (code.length === LENGTH && !next.includes("") && !firedRef.current) {
      firedRef.current = true;
      onComplete(code);
    }
  }

  function handleChange(index: number, raw: string) {
    const char = raw.replace(/[^a-zA-Z0-9]/g, "").slice(-1).toUpperCase();
    setAt(index, char);
    if (char && index < LENGTH - 1) {
      inputRefs.current[index + 1]?.focus();
    }
  }

  function handleKeyDown(index: number, e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace" && !values[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  }

  function handlePaste(e: React.ClipboardEvent<HTMLInputElement>) {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/[^a-zA-Z0-9]/g, "").toUpperCase().slice(0, LENGTH);
    if (!pasted) return;
    const next = Array(LENGTH).fill("");
    for (let i = 0; i < pasted.length; i++) next[i] = pasted[i];
    setValues(next);
    onChange?.(next.join(""));
    const lastIndex = Math.min(pasted.length, LENGTH) - 1;
    inputRefs.current[lastIndex]?.focus();
    if (pasted.length === LENGTH && !firedRef.current) {
      firedRef.current = true;
      onComplete(pasted);
    }
  }

  return (
    <div className="flex justify-center gap-3">
      {values.map((val, i) => (
        <input
          key={i}
          ref={(el) => {
            inputRefs.current[i] = el;
          }}
          type="text"
          inputMode="text"
          maxLength={1}
          value={val}
          disabled={disabled}
          autoFocus={autoFocus && i === 0}
          onChange={(e) => handleChange(i, e.target.value)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          onPaste={handlePaste}
          className={cn(
            "h-14 w-12 rounded-lg border border-line-strong bg-white text-center text-[22px] font-semibold text-ink",
            "transition-all duration-150 ease-out",
            "focus:outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-300/20",
            disabled && "cursor-not-allowed bg-surface-sunken text-ink-faint"
          )}
        />
      ))}
    </div>
  );
}
