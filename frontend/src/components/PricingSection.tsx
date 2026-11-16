"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import type { PublicPlan } from "@/lib/api";

function formatRub(kopeks: number): string {
  const rub = kopeks / 100;
  return Number.isInteger(rub) ? `${rub} ₽` : `${rub.toFixed(2)} ₽`;
}

function getEffectiveMonths(days: number): number {
  if (days >= 360 && days <= 366) return 12;
  return Math.max(days / 30, 1);
}

function formatDurationLabel(days: number): string {
  if (days >= 360 && days <= 366) return "12 месяцев";
  if (days % 30 === 0 && days >= 30) {
    const m = days / 30;
    if (m === 1) return "1 месяц";
    if (m >= 2 && m <= 4) return `${m} месяца`;
    return `${m} месяцев`;
  }
  return `${days} дн.`;
}

export function PricingSection({ plans }: { plans: PublicPlan[] }) {
  const [selectedPlan, setSelectedPlan] = useState<PublicPlan | null>(null);
  const [email, setEmail] = useState("");
  const [acceptedTerms, setAcceptedTerms] = useState(true);
  const [loading, setLoading] = useState(false);
  const [resultMessage, setResultMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const sortedByDuration = [...plans].sort((a, b) => a.duration_days - b.duration_days);
  const basePlan = sortedByDuration[0];
  const baseMonthlyKopeks = basePlan
    ? basePlan.price_kopeks / getEffectiveMonths(basePlan.duration_days)
    : 0;

  let bestPlanId: number | null = null;
  if (plans.length > 1) {
    let minMonthly = Infinity;
    for (const p of plans) {
      const mPrice = p.price_kopeks / getEffectiveMonths(p.duration_days);
      if (mPrice < minMonthly) {
        minMonthly = mPrice;
        bestPlanId = p.id;
      }
    }
  }

  function openCheckout(plan: PublicPlan) {
    setSelectedPlan(plan);
    setResultMessage(null);
    setErrorMessage(null);
  }

  function closeCheckout() {
    setSelectedPlan(null);
    setResultMessage(null);
    setErrorMessage(null);
    setLoading(false);
  }

  async function handleCheckoutSubmit(e: FormEvent) {
    e.preventDefault();
    if (!selectedPlan) return;

    setLoading(true);
    setErrorMessage(null);
    setResultMessage(null);

    try {
      const res = await fetch("/api/billing/checkout-preview/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          plan_id: selectedPlan.id,
          email: email.trim(),
          accepted_terms: acceptedTerms,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setErrorMessage(data.detail || "Не удалось оформить заказ. Проверьте введенные данные.");
      } else {
        setResultMessage(
          data.message ||
            "Оплата временно недоступна: платежная система находится на этапе подключения."
        );
      }
    } catch {
      setErrorMessage("Оплата временно недоступна. Попробуйте чуть позже.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section id="pricing" className="mx-auto max-w-6xl px-4 py-14">
      <h2 className="mb-8 text-center text-3xl font-bold text-[#efeaff] sm:text-4xl">
        Тарифы доступа
      </h2>

      <div className="grid gap-6 md:grid-cols-3">
        {plans.map((plan) => {
          const isBestValue = plan.id === bestPlanId;
          const months = getEffectiveMonths(plan.duration_days);
          const monthlyKopeks = plan.price_kopeks / months;
          const monthlyRub = Math.round(monthlyKopeks / 100);
          const discountPercent =
            baseMonthlyKopeks > 0 && plan.duration_days > (basePlan?.duration_days || 0)
              ? Math.round((1 - monthlyKopeks / baseMonthlyKopeks) * 100)
              : 0;

          return (
            <div
              key={plan.id}
              className={`flex flex-col justify-between rounded-[22px] border p-6 transition duration-300 ${
                isBestValue
                  ? "border-[#7ae9eb]/45 bg-gradient-to-br from-[#271657] to-[#161038] shadow-[0_20px_50px_-15px_rgba(6,3,20,0.9),0_0_36px_-14px_rgba(122,233,235,0.4)]"
                  : "border-[#8b5cf6]/25 bg-[#160e31]/95 shadow-[0_20px_45px_-15px_rgba(6,3,20,0.85)] hover:border-[#7ae9eb]/40"
              }`}
            >
              <div>
                <div className="flex items-center justify-between gap-2">
                  <span className="inline-flex items-center rounded-lg border border-[#7ae9eb]/30 bg-[#7ae9eb]/10 px-2.5 py-1 text-xs font-bold text-[#7ae9eb]">
                    {formatDurationLabel(plan.duration_days)}
                  </span>

                  {isBestValue ? (
                    <span className="rounded-full border border-[#f472b6]/45 bg-[#f472b6]/15 px-2.5 py-0.5 text-xs font-semibold text-[#fbcfe8]">
                      {discountPercent > 0 ? `Выгодно -${discountPercent}%` : "Самый выгодный"}
                    </span>
                  ) : (
                    discountPercent > 0 && (
                      <span className="rounded-full border border-[#8b5cf6]/35 bg-[#1f1444] px-2.5 py-0.5 text-xs font-semibold text-[#d8d0ff]">
                        -{discountPercent}%
                      </span>
                    )
                  )}
                </div>

                <h3 className="mt-4 text-xl font-semibold text-[#efeaff]">{plan.name}</h3>

                <div className="mt-3 flex flex-wrap items-baseline gap-2.5">
                  <span className="text-4xl font-bold text-[#7ae9eb]">
                    {formatRub(plan.price_kopeks)}
                  </span>
                  {months > 1 && (
                    <span className="rounded-md bg-[#120b28]/80 px-2 py-0.5 text-xs font-medium text-[#d8d0ff]">
                      {monthlyRub} ₽ / мес
                    </span>
                  )}
                </div>

                {plan.description && (
                  <p className="mt-3 text-sm leading-relaxed text-[#9e96cc]">
                    {plan.description}
                  </p>
                )}

                <ul className="mt-5 space-y-2 text-sm text-[#d8d0ff]">
                  <li>• До {plan.max_devices} устройств</li>
                  <li>
                    • Трафик:{" "}
                    {plan.traffic_limit_gb ? `${plan.traffic_limit_gb} ГБ` : "Без ограничений"}
                  </li>
                  <li>• Протоколы: VLESS, Hysteria 2</li>
                </ul>
              </div>

              <button
                type="button"
                onClick={() => openCheckout(plan)}
                className="mt-8 w-full rounded-[14px] bg-[#7ae9eb] px-4 py-3 text-sm font-bold text-[#120b28] shadow-[0_0_24px_-6px_rgba(122,233,235,0.55)] transition hover:bg-[#9ef1f3]"
              >
                Оплатить / Купить
              </button>
            </div>
          );
        })}
      </div>

      {selectedPlan && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#070312]/85 p-4 backdrop-blur-md">
          <div className="w-full max-w-md rounded-[22px] border border-[#7ae9eb]/35 bg-[#130b2c] p-6 shadow-[0_24px_60px_rgba(4,1,16,0.95),0_0_40px_-14px_rgba(122,233,235,0.35)]">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-lg font-bold text-[#efeaff]">Оформление доступа</h3>
                <p className="mt-1 text-sm text-[#9e96cc]">
                  {selectedPlan.name} ({formatDurationLabel(selectedPlan.duration_days)}) —{" "}
                  <span className="font-semibold text-[#7ae9eb]">
                    {formatRub(selectedPlan.price_kopeks)}
                  </span>
                </p>
              </div>
              <button
                type="button"
                onClick={closeCheckout}
                className="rounded-lg border border-[#8b5cf6]/25 bg-[#1b1238] px-2.5 py-1 text-sm text-[#9e96cc] transition hover:border-[#7ae9eb]/40 hover:text-[#efeaff]"
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleCheckoutSubmit} className="mt-5 space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-[#d8d0ff]">
                  Email для чека и уведомлений *
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  className="w-full rounded-[14px] border border-[#8b5cf6]/30 bg-[#0d0720] px-3.5 py-2.5 text-sm text-[#efeaff] placeholder-[#7e75ad] focus:border-[#7ae9eb] focus:outline-none"
                />
              </div>

              <label className="flex items-start gap-2.5 text-xs leading-relaxed text-[#9e96cc]">
                <input
                  type="checkbox"
                  checked={acceptedTerms}
                  onChange={(e) => setAcceptedTerms(e.target.checked)}
                  className="mt-0.5 rounded border-[#8b5cf6]/40 bg-[#0d0720] accent-[#7ae9eb]"
                />
                <span>
                  Я принимаю{" "}
                  <Link
                    href="/terms"
                    className="text-[#7ae9eb] underline"
                    onClick={closeCheckout}
                  >
                    Пользовательское соглашение
                  </Link>{" "}
                  и{" "}
                  <Link
                    href="/privacy"
                    className="text-[#7ae9eb] underline"
                    onClick={closeCheckout}
                  >
                    Политику конфиденциальности
                  </Link>
                  .
                </span>
              </label>

              {errorMessage && (
                <div className="rounded-[14px] border border-[#ec5f49]/40 bg-[#2d1020] p-3 text-xs text-[#ff9a8a]">
                  {errorMessage}
                </div>
              )}

              {resultMessage && (
                <div className="rounded-[14px] border border-[#f472b6]/35 bg-[#23123c] p-3.5 text-xs leading-relaxed text-[#fbcfe8]">
                  {resultMessage}
                </div>
              )}

              <div className="flex gap-3 pt-1">
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 rounded-[14px] bg-[#7ae9eb] px-4 py-2.5 text-sm font-bold text-[#120b28] shadow-[0_0_20px_-6px_rgba(122,233,235,0.55)] transition hover:bg-[#9ef1f3] disabled:opacity-60"
                >
                  {loading
                    ? "Проверка..."
                    : `Перейти к оплате (${formatRub(selectedPlan.price_kopeks)})`}
                </button>
                <button
                  type="button"
                  onClick={closeCheckout}
                  className="rounded-[14px] border border-[#8b5cf6]/30 bg-[#1b1238] px-4 py-2.5 text-sm text-[#d8d0ff] transition hover:border-[#7ae9eb]/40"
                >
                  Закрыть
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}