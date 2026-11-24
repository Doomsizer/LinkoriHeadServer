export interface PublicPlan {
  id: number;
  code: string;
  name: string;
  description: string;
  duration_days: number;
  price_kopeks: number;
  max_devices: number;
  traffic_limit_gb: number | null;
  is_trial: boolean;
}

export interface LegalDocumentItem {
  title: string;
  url: string;
  text: string;
}

export interface LegalDocsResponse {
  updated_at: string;
  support_telegram: string;
  support_email: string;
  max_transaction_rub: number;
  privacy_policy: LegalDocumentItem;
  terms_of_service: LegalDocumentItem;
}

const FALLBACK_PLANS: PublicPlan[] = [
  {
    id: 1,
    code: "proxy_1m",
    name: "Старт — 1 месяц",
    description: "До 10 устройств, высокоскоростные маршруты.",
    duration_days: 30,
    price_kopeks: 29900,
    max_devices: 10,
    traffic_limit_gb: null,
    is_trial: false,
  },
  {
    id: 2,
    code: "proxy_3m",
    name: "Оптимальный — 3 месяца",
    description: "До 10 устройств, приоритетная пропускная способность.",
    duration_days: 90,
    price_kopeks: 79900,
    max_devices: 10,
    traffic_limit_gb: null,
    is_trial: false,
  },
  {
    id: 3,
    code: "proxy_12m",
    name: "Годовой — 12 месяцев",
    description: "До 10 устройств, игровые и CDN-маршруты, поддержка 24/7.",
    duration_days: 365,
    price_kopeks: 249000,
    max_devices: 10,
    traffic_limit_gb: null,
    is_trial: false,
  },
];

function getInternalApiBase(): string {
  return (process.env.INTERNAL_API_URL || "http://django:8000").replace(/\/$/, "");
}

export async function fetchPublicPlans(): Promise<PublicPlan[]> {
  try {
    const res = await fetch(`${getInternalApiBase()}/api/billing/plans/`, {
      cache: "no-store",
    });
    if (!res.ok) return FALLBACK_PLANS;
    const data = (await res.json()) as PublicPlan[];
    return Array.isArray(data) && data.length > 0 ? data : FALLBACK_PLANS;
  } catch {
    return FALLBACK_PLANS;
  }
}

export async function fetchLegalDocs(): Promise<LegalDocsResponse | null> {
  try {
    const res = await fetch(`${getInternalApiBase()}/api/billing/legal/`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as LegalDocsResponse;
  } catch {
    return null;
  }
}