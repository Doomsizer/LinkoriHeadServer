"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import type { PublicPlan } from "../lib/api";

function formatRub(kopeks: number): string {
  const rub = kopeks / 100;
  return Number.isInteger(rub) ? `${rub} ₽` : `${rub.toFixed(2)} ₽`;
}

export function PricingSection({ plans }: { plans: PublicPlan[] }) {
  const [selectedPlan, setSelectedPlan] = useState<PublicPlan | null>(null);
  const [email, setEmail] = useState("");
  const [acceptedTerms, setAcceptedTerms] = useState(true);
  const [loading, setLoading] = useState(false);
  const [resultMessage, setResultMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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
    <section id="pricing" className="mx-auto max-w-6xl px-4 py-16">
      <div className="mb-10 text-center">
        <h2 className="text-3xl font-bold text-white sm:text-4xl">Тарифы доступа</h2>
        <p className="mx-auto mt-3 max-w-2xl text-sm text-slate-400 sm:text-base">
          Прозрачная стоимость без скрытых списаний. Доступ ко всем приватным прокси-узлам,
          высокая скорость канала и поддержка до 5 устройств.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {plans.map((plan, idx) => {
          const isPopular = idx === 1;
          return (
            <div
              key={plan.id}
              className={`flex flex-col justify-between rounded-2xl border p-6 transition ${
                isPopular
                  ? "border-blue-500/80 bg-surface shadow-lg shadow-blue-950/40"
                  : "border-border bg-surface/80 hover:border-slate-600"
              }`}
            >
              <div>
                <div className="flex items-center justify-between gap-2">

      {selectedPlan && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-border bg-surface p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-lg font-bold text-white">Оформление доступа</h3>
                <p className="mt-1 text-sm text-slate-400">
                  {selectedPlan.name} —{" "}
                  <span className="font-semibold text-white">
                    {formatRub(selectedPlan.price_kopeks)}
                  </span>
                </p>
              </div>
              <button
                type="button"
                onClick={closeCheckout}
                className="rounded-lg px-2 py-1 text-slate-400 hover:bg-slate-800 hover:text-white"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCheckoutSubmit} className="mt-5 space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-slate-300">
                  Email для чека и уведомлений *
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  className="w-full rounded-xl border border-border bg-bg px-3.5 py-2.5 text-sm text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none"
                />
              </div>

              <label className="flex items-start gap-2.5 text-xs leading-relaxed text-slate-400">
                <input
                  type="checkbox"
                  checked={acceptedTerms}
                  onChange={(e) => setAcceptedTerms(e.target.checked)}
                  className="mt-0.5 rounded border-border bg-bg text-blue-600"
                />
                <span>
                  Я принимаю{" "}
                  <Link href="/terms" className="text-blue-400 underline" onClick={closeCheckout}>
                    Пользовательское соглашение
                  </Link>{" "}
                  и{" "}
                  <Link href="/privacy" className="text-blue-400 underline" onClick={closeCheckout}>
                    Политику конфиденциальности
                  </Link>
                  .
                </span>
              </label>

              {errorMessage && (
                <div className="rounded-xl border border-red-500/40 bg-red-950/40 p-3 text-xs text-red-200">
                  {errorMessage}
                </div>
              )}

              {resultMessage && (
                <div className="rounded-xl border border-amber-500/40 bg-amber-950/40 p-3.5 text-xs leading-relaxed text-amber-200">
                  {resultMessage}
                </div>
              )}

              <div className="flex gap-3 pt-1">
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:opacity-60"
                >
                  {loading ? "Проверка..." : `Перейти к оплате (${formatRub(selectedPlan.price_kopeks)})`}
                </button>
                <button
                  type="button"
                  onClick={closeCheckout}
                  className="rounded-xl border border-border px-4 py-2.5 text-sm text-slate-300 hover:bg-slate-800"
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

                  <h3 className="text-xl font-semibold text-white">{plan.name}</h3>
                  {isPopular && (
                    <span className="rounded-full bg-blue-600/20 px-2.5 py-1 text-xs font-medium text-blue-300">
                      Популярный
                    </span>
                  )}
                </div>

                <div className="mt-4 flex items-baseline gap-2">
                  <span className="text-4xl font-bold text-white">
                    {formatRub(plan.price_kopeks)}
                  </span>
                  <span className="text-sm text-slate-400">/ {plan.duration_days} дн.</span>
                </div>

                <p className="mt-3 text-sm leading-relaxed text-slate-400">
                  {plan.description || "Приватное прокси-подключение на базе современных протоколов."}
                </p>

                <ul className="mt-6 space-y-2.5 text-sm text-slate-300">
                  <li>• Устройств: до {plan.max_devices}</li>
                  <li>
                    • Трафик:{" "}
                    {plan.traffic_limit_gb ? `${plan.traffic_limit_gb} ГБ` : "Без ограничений"}
                  </li>
                  <li>• Протоколы: VLESS, Hysteria 2 (низкий пинг)</li>
                  <li>• Поддержка через Telegram и Email</li>
                </ul>
              </div>

              <button
                type="button"
                onClick={() => openCheckout(plan)}
                className="mt-8 w-full rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-blue-500"
              >
                Оплатить / Купить
              </button>
            </div>
          );
        })}
      </div>
