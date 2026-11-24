"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import type { PublicPlan } from "@/lib/api";
import { hasLocalLegalConsent } from "@/lib/consent";
import { clearPendingRefCode, getPendingRefCode } from "@/lib/referral";

interface MeUser {
  id: number;
  telegram_id: number | null;
  telegram_username: string;
  email: string | null;
  has_used_trial: boolean;
}

const FEE_PERCENT_BY_METHOD: Record<"sbp" | "crypto", number> = {
  sbp: 7,
  crypto: 5,
};

function getCookie(name: string): string {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : "";
}

function formatRub(kopeks: number): string {
  const rub = kopeks / 100;
  return Number.isInteger(rub) ? `${rub} ₽` : `${rub.toFixed(2)} ₽`;
}

function formatRubFloat(rub: number): string {
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
  if (days === 1) return "1 день";
  if (days >= 2 && days <= 4) return `${days} дня`;
  return `${days} дн.`;
}

export function PricingSection({ plans }: { plans: PublicPlan[] }) {
  const [sessionLoaded, setSessionLoaded] = useState(false);
  const [meUser, setMeUser] = useState<MeUser | null>(null);
  const [hasActiveSub, setHasActiveSub] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState<PublicPlan | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<"sbp" | "crypto">("sbp");

  const [email, setEmail] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  const [acceptedTerms, setAcceptedTerms] = useState(true);

  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function refreshSession() {
    try {
      const res = await fetch("/api/accounts/me/", { credentials: "include" });
      if (res.ok) {
        const data = await res.json();
        setMeUser(data.user || null);
        setHasActiveSub(Boolean(data.active_subscription));
      } else {
        setMeUser(null);
        setHasActiveSub(false);
      }
    } catch {
      setMeUser(null);
      setHasActiveSub(false);
    } finally {
      setSessionLoaded(true);
    }
  }

  useEffect(() => {
    refreshSession();
    window.addEventListener("linkori-auth-changed", refreshSession);
    return () => window.removeEventListener("linkori-auth-changed", refreshSession);
  }, []);

  const canShowTrial = sessionLoaded && (!meUser || (!meUser.has_used_trial && !hasActiveSub));
  const trialPlans = canShowTrial ? plans.filter((p) => p.is_trial) : [];
  const regularPlans = plans.filter((p) => !p.is_trial);

  const sortedRegular = [...regularPlans].sort((a, b) => a.duration_days - b.duration_days);
  const basePlan = sortedRegular[0];
  const baseMonthlyKopeks = basePlan
    ? basePlan.price_kopeks / getEffectiveMonths(basePlan.duration_days)
    : 0;

  let bestPlanId: number | null = null;
  if (regularPlans.length > 1) {
    let minMonthly = Infinity;
    for (const p of regularPlans) {
      const mPrice = p.price_kopeks / getEffectiveMonths(p.duration_days);
      if (mPrice < minMonthly) {
        minMonthly = mPrice;
        bestPlanId = p.id;
      }
    }
  }

  function openCheckout(plan: PublicPlan) {
    setSelectedPlan(plan);
    setPaymentMethod("sbp");
    setErrorMessage(null);
    setOtpSent(false);
    setOtpCode("");
    setEmail(meUser?.email || "");
  }

  function closeCheckout() {
    setSelectedPlan(null);
    setErrorMessage(null);
    setLoading(false);
  }

  async function handleRequestOtp(e: FormEvent) {
    e.preventDefault();
    if (!acceptedTerms) {
      setErrorMessage("Необходимо принять Пользовательское соглашение и Политику конфиденциальности.");
      return;
    }
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await fetch("/api/accounts/email-auth/request/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        setErrorMessage(data.detail || "Не удалось отправить код.");
        return;
      }
      setOtpSent(true);
    } catch {
      setErrorMessage("Ошибка соединения с сервером.");
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyOtpAndContinue(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await fetch("/api/accounts/email-auth/verify/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          email: email.trim(),
          code: otpCode.trim(),
          accepted_legal: hasLocalLegalConsent() || acceptedTerms,
          referred_by_code: getPendingRefCode(),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setErrorMessage(data.detail || "Неверный код подтверждения.");
        return;
      }
      clearPendingRefCode();
      await refreshSession();
      window.dispatchEvent(new Event("linkori-auth-changed"));
      setOtpSent(false);
    } catch {
      setErrorMessage("Ошибка соединения с сервером.");
    } finally {
      setLoading(false);
    }
  }

  async function handlePaySubmit(e: FormEvent) {
    e.preventDefault();
    if (!selectedPlan) return;

    setLoading(true);
    setErrorMessage(null);

    try {
      const res = await fetch("/api/billing/web/checkout/", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify({
          plan_id: selectedPlan.id,
          payment_method: selectedPlan.is_trial ? "sbp" : paymentMethod,
          email: meUser?.email ? "" : email.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setErrorMessage(data.detail || "Не удалось создать счет на оплату.");
        return;
      }
      if (data.payment_url) {
        window.location.href = data.payment_url;
      } else {
        setErrorMessage("Платежный шлюз не вернул ссылку на оплату.");
      }
    } catch {
      setErrorMessage("Ошибка соединения с сервером.");
    } finally {
      setLoading(false);
    }
  }

  const activeMethod: "sbp" | "crypto" = selectedPlan?.is_trial ? "sbp" : paymentMethod;
  const feePercent = FEE_PERCENT_BY_METHOD[activeMethod];
  const baseRub = selectedPlan ? selectedPlan.price_kopeks / 100 : 0;
  const feeRub = Math.round(baseRub * feePercent) / 100;
  const totalWithFeeRub = Math.round((baseRub + feeRub) * 100) / 100;

  return (
    <section id="pricing" className="mx-auto max-w-6xl px-4 py-14">
      <h2 className="mb-8 text-center text-3xl font-bold text-[#efeaff] sm:text-4xl">
        Тарифы доступа
      </h2>

      {trialPlans.length > 0 && (
        <div className="mb-8 space-y-4">
          {trialPlans.map((trial) => (
            <div
              key={trial.id}
              className="flex flex-col items-start justify-between gap-4 rounded-[22px] border border-[#f472b6]/40 bg-gradient-to-r from-[#23123c] to-[#160e31] p-6 shadow-[0_18px_45px_-15px_rgba(6,3,20,0.9)] sm:flex-row sm:items-center"
            >
              <div>
                <div className="flex flex-wrap items-center gap-2.5">
                  <span className="rounded-lg border border-[#f472b6]/45 bg-[#f472b6]/15 px-2.5 py-1 text-xs font-bold text-[#fbcfe8]">
                    Пробный период • {formatDurationLabel(trial.duration_days)}
                  </span>
                  <span className="text-xs text-[#9e96cc]">
                    Только СБП (+7% комиссия) • 1 раз для новых пользователей
                  </span>
                </div>
                <h3 className="mt-2.5 text-xl font-bold text-[#efeaff]">
                  {trial.name} —{" "}
                  <span className="text-[#7ae9eb]">{formatRub(trial.price_kopeks)}</span>
                </h3>
                {trial.description && (
                  <p className="mt-1 text-sm text-[#9e96cc]">{trial.description}</p>
                )}
              </div>

              <button
                type="button"
                onClick={() => openCheckout(trial)}
                className="shrink-0 rounded-[14px] bg-[#7ae9eb] px-6 py-3 text-sm font-bold text-[#120b28] shadow-[0_0_24px_-6px_rgba(122,233,235,0.55)] transition hover:bg-[#9ef1f3]"
              >
                Попробовать за {formatRub(trial.price_kopeks)}
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-3">
        {regularPlans.map((plan) => {
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

            {!meUser ? (
              <div className="mt-5 space-y-4">
                <div className="rounded-[14px] border border-[#8b5cf6]/25 bg-[#0d0720] p-3.5 text-xs leading-relaxed text-[#d8d0ff]">
                  Подтвердите Email (придет 6-значный код) или войдите через Telegram, чтобы доступ
                  привязался к вашему кабинету.
                </div>

                {!otpSent ? (
                  <form onSubmit={handleRequestOtp} className="space-y-4">
                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-[#d8d0ff]">
                        Email для входа и чека *
                      </label>
                      <input
                        type="email"
                        required
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="name@gmail.com"
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
                        <Link href="/terms" className="text-[#7ae9eb] underline" onClick={closeCheckout}>
                          Пользовательское соглашение
                        </Link>{" "}
                        и{" "}
                        <Link href="/privacy" className="text-[#7ae9eb] underline" onClick={closeCheckout}>
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

                    <button
                      type="submit"
                      disabled={loading}
                      className="w-full rounded-[14px] bg-[#7ae9eb] px-4 py-2.5 text-sm font-bold text-[#120b28] transition hover:bg-[#9ef1f3] disabled:opacity-60"
                    >
                      {loading ? "Отправка..." : "Отправить код на почту"}
                    </button>
                  </form>
                ) : (
                  <form onSubmit={handleVerifyOtpAndContinue} className="space-y-4">
                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-[#d8d0ff]">
                        Введите код из письма ({email})
                      </label>
                      <input
                        type="text"
                        inputMode="numeric"
                        required
                        value={otpCode}
                        onChange={(e) => setOtpCode(e.target.value)}
                        placeholder="123456"
                        className="w-full rounded-[14px] border border-[#8b5cf6]/30 bg-[#0d0720] px-3.5 py-2.5 text-center font-mono text-lg tracking-widest text-[#efeaff] focus:border-[#7ae9eb] focus:outline-none"
                      />
                    </div>

                    {errorMessage && (
                      <div className="rounded-[14px] border border-[#ec5f49]/40 bg-[#2d1020] p-3 text-xs text-[#ff9a8a]">
                        {errorMessage}
                      </div>
                    )}

                    <button
                      type="submit"
                      disabled={loading}
                      className="w-full rounded-[14px] bg-[#7ae9eb] px-4 py-2.5 text-sm font-bold text-[#120b28] transition hover:bg-[#9ef1f3] disabled:opacity-60"
                    >
                      {loading ? "Проверка..." : "Подтвердить код"}
                    </button>
                  </form>
                )}

                <div className="border-t border-[#8b5cf6]/20 pt-3 text-center">
                  <Link
                    href="/login"
                    onClick={closeCheckout}
                    className="text-xs font-semibold text-[#7ae9eb] hover:underline"
                  >
                    Или войти через Telegram →
                  </Link>
                </div>
              </div>
            ) : (
              <form onSubmit={handlePaySubmit} className="mt-5 space-y-4">
                <div>
                  <label className="mb-2 block text-xs font-medium text-[#d8d0ff]">
                    Способ оплаты (комиссия шлюза на стороне покупателя)
                  </label>
                  <div className={`grid gap-2.5 ${selectedPlan.is_trial ? "grid-cols-1" : "grid-cols-2"}`}>
                    <button
                      type="button"
                      onClick={() => setPaymentMethod("sbp")}
                      className={`rounded-[14px] border px-3 py-2.5 text-center transition ${
                        activeMethod === "sbp"
                          ? "border-[#7ae9eb] bg-[#7ae9eb]/15 text-[#7ae9eb]"
                          : "border-[#8b5cf6]/30 bg-[#0d0720] text-[#9e96cc]"
                      }`}
                    >
                      <div className="text-xs font-bold">СБП (QR-код)</div>
                      <div className="mt-0.5 text-[11px] opacity-80">Комиссия +7%</div>
                    </button>
                    {!selectedPlan.is_trial && (
                      <button
                        type="button"
                        onClick={() => setPaymentMethod("crypto")}
                        className={`rounded-[14px] border px-3 py-2.5 text-center transition ${
                          activeMethod === "crypto"
                            ? "border-[#7ae9eb] bg-[#7ae9eb]/15 text-[#7ae9eb]"
                            : "border-[#8b5cf6]/30 bg-[#0d0720] text-[#9e96cc]"
                        }`}
                      >
                        <div className="text-xs font-bold">Криптовалюта</div>
                        <div className="mt-0.5 text-[11px] opacity-80">Комиссия +5%</div>
                      </button>
                    )}
                  </div>
                </div>

                <div className="space-y-1.5 rounded-[14px] border border-[#8b5cf6]/25 bg-[#0d0720] p-3.5 text-xs">
                  <div className="flex justify-between text-[#9e96cc]">
                    <span>Тариф:</span>
                    <span>{formatRubFloat(baseRub)}</span>
                  </div>
                  <div className="flex justify-between text-[#9e96cc]">
                    <span>Комиссия платежной системы (+{feePercent}%):</span>
                    <span>~{formatRubFloat(feeRub)}</span>
                  </div>
                  <div className="flex justify-between border-t border-[#8b5cf6]/20 pt-1.5 text-sm font-bold text-[#7ae9eb]">
                    <span>К оплате на странице Platega:</span>
                    <span>~{formatRubFloat(totalWithFeeRub)}</span>
                  </div>
                </div>

                {meUser.email ? (
                  <div className="rounded-[14px] border border-[#8b5cf6]/25 bg-[#0d0720] px-3.5 py-2.5 text-xs text-[#9e96cc]">
                    Чек и доступ привязаны к{" "}
                    <span className="font-semibold text-[#efeaff]">{meUser.email}</span>
                  </div>
                ) : (
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-[#d8d0ff]">
                      Email для чека (опционально)
                    </label>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="name@gmail.com"
                      className="w-full rounded-[14px] border border-[#8b5cf6]/30 bg-[#0d0720] px-3.5 py-2.5 text-sm text-[#efeaff] placeholder-[#7e75ad] focus:border-[#7ae9eb] focus:outline-none"
                    />
                  </div>
                )}

                {errorMessage && (
                  <div className="rounded-[14px] border border-[#ec5f49]/40 bg-[#2d1020] p-3 text-xs text-[#ff9a8a]">
                    {errorMessage}
                  </div>
                )}

                <div className="flex gap-3 pt-1">
                  <button
                    type="submit"
                    disabled={loading}
                    className="flex-1 rounded-[14px] bg-[#7ae9eb] px-4 py-2.5 text-sm font-bold text-[#120b28] shadow-[0_0_20px_-6px_rgba(122,233,235,0.55)] transition hover:bg-[#9ef1f3] disabled:opacity-60"
                  >
                    {loading
                      ? "Создаем счет..."
                      : `Перейти к оплате (~${formatRubFloat(totalWithFeeRub)})`}
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
            )}
          </div>
        </div>
      )}
    </section>
  );
}