/** Shared boundary for template text, external links, and optional browser storage. */
export const escapeHtml = (value: unknown): string => String(value ?? "").replace(
  /[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]!);

export function safeUrl(value: string): string {
  try { const url = new URL(value); return ["https:", "http:"].includes(url.protocol) ? url.href : "#"; }
  catch { return "#"; }
}

export const storage = {
  getItem(key: string): string | null {
    try { return localStorage.getItem(key); } catch { return null; }
  },
  setItem(key: string, value: string): boolean {
    try { localStorage.setItem(key, value); return true; } catch { return false; }
  },
  removeItem(key: string): void {
    try { localStorage.removeItem(key); } catch { /* Storage is optional. */ }
  },
  keys(prefix: string): string[] {
    try { return Object.keys(localStorage).filter(key => key.startsWith(prefix)).sort(); }
    catch { return []; }
  },
};

export function message(target: Element, text: string, kind = "error"): void {
  const element = document.createElement("div");
  element.className = `message ${kind}`;
  element.textContent = text;
  target.replaceChildren(element);
}
