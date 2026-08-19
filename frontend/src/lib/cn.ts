/** Minimal className joiner - skips falsy values. Deliberately not pulling
 * in clsx/tailwind-merge for this: the component set here never needs
 * tailwind-merge's conflict-resolution (later class wins), just
 * conditional concatenation. */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
