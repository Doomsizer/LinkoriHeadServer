export const LEGAL_CONSENT_STORAGE_KEY = "linkori_legal_accepted";

export function hasLocalLegalConsent(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(LEGAL_CONSENT_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function setLocalLegalConsent(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LEGAL_CONSENT_STORAGE_KEY, "true");
  } catch {
    // Игнорируем ограничения приватного режима браузера
  }
}