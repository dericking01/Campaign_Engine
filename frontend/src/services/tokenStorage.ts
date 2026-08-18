// Centralizes where the access token lives so "Remember me" is a real
// behavior, not a decorative checkbox: checked -> localStorage (survives
// closing the browser), unchecked -> sessionStorage (cleared when the tab
// closes). Every reader checks both, since a token could be in either
// depending on how the user logged in.

const KEY = "access_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(KEY) ?? window.sessionStorage.getItem(KEY);
}

export function setToken(token: string, remember: boolean): void {
  if (typeof window === "undefined") return;
  clearToken();
  (remember ? window.localStorage : window.sessionStorage).setItem(KEY, token);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(KEY);
  window.sessionStorage.removeItem(KEY);
}
