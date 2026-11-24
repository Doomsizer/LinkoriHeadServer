const REF_STORAGE_KEY = "linkori_ref_code";

export function captureReferralFromUrl(): void {
  if (typeof window === "undefined") return;
  try {
    const params = new URLSearchParams(window.location.search);
    const ref = (params.get("ref") || "").trim();
    if (ref) {
      window.localStorage.setItem(REF_STORAGE_KEY, ref);
    }
  } catch {
    // Игнорируем ограничения приватного режима
  }
}

export function getPendingRefCode(): string {
  if (typeof window === "undefined") return "";
  try {
    return (window.localStorage.getItem(REF_STORAGE_KEY) || "").trim();
  } catch {
    return "";
  }
}

export function clearPendingRefCode(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(REF_STORAGE_KEY);
  } catch {
    // Игнорируем ограничения приватного режима
  }
}