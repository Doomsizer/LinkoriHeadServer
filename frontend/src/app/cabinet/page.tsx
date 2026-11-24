"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

interface MeResponse {
  user: {
    id: number;
    telegram_id: number | null;
    telegram_username: string;
    email: string | null;
    referral_code: string;
    has_used_trial: boolean;
    is_legal_accepted: boolean;
  };
  referrals_count: number;
  referral_bonus_hours: number;
  devices_count: number;
  active_subscription: {
    id: string;
    sub_token: string;
    status: string;
    plan_name: string;
    max_devices: number;
    traffic_used_bytes: number;
    traffic_limit_bytes: number | null;
    expires_at: string;
  } | null;
}

function getCookie(name: string): string {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : "";
}

function formatBonusTime(hours: number): string {
  if (!hours) return "0 дн.";
  const days = Math.floor(hours / 24);
  const rem = hours % 24;
  if (days > 0 && rem > 0) return `${days} дн. ${rem} ч.`;
  if (days > 0) return `${days} дн.`;
  return `${rem} ч.`;
}

export default function CabinetPage() {
  const router = useRouter();
  const [data, setData] = useState<MeResponse | null>(null);
  const [copied, setCopied] = useState(false);

  // Статус оплаты после возврата с Platega
  const [paymentBanner, setPaymentBanner] = useState<{
    type: "pending" | "paid" | "failed";
    text: string;
  } | null>(null);

  // Привязка Email
  const [linkEmail, setLinkEmail] = useState("");
  const [linkOtpSent, setLinkOtpSent] = useState(false);
  const [linkOtpCode, setLinkOtpCode] = useState("");
  const [linkMsg, setLinkMsg] = useState<string | null>(null);
  const [linkErr, setLinkErr] = useState<string | null>(null);

  // Привязка Telegram
  const [tgBotUrl, setTgBotUrl] = useState<string | null>(null);
  const [tgAuthToken, setTgAuthToken] = useState<string | null>(null);

  async function loadProfile() {
    try {
      const res = await fetch("/api/accounts/me/", { credentials: "include" });
      if (!res.ok) {
        router.replace("/login");
        return;
      }
      setData(await res.json());
    } catch {
      router.replace("/login");
    }
  }

  useEffect(() => {
    loadProfile();

    const params = new URLSearchParams(window.location.search);
    const payId = params.get("payment");
    const urlStatus = params.get("status");
    if (!payId) return;

    if (urlStatus === "failed") {
      setPaymentBanner({ type: "failed", text: "Оплата не была завершена." });
      return;
    }

    setPaymentBanner({ type: "pending", text: "Проверяем статус вашей оплаты..." });
    let attempts = 0;
    const timer = setInterval(async () => {
      attempts += 1;
      try {
        const res = await fetch(
          `/api/billing/web/payments/${encodeURIComponent(payId)}/status/`,
          { credentials: "include" }
        );
        if (!res.ok) {
          clearInterval(timer);
          return;
        }
        const payData = await res.json();
        if (payData.status === "paid") {
          clearInterval(timer);
          setPaymentBanner({
            type: "paid",
            text: "Оплата подтверждена! Доступ активирован.",
          });
          loadProfile();
        } else if (payData.status === "failed") {
          clearInterval(timer);
          setPaymentBanner({ type: "failed", text: "Платеж отменен или не прошел." });
        } else if (attempts >= 15) {
          clearInterval(timer);
          setPaymentBanner({
            type: "pending",
            text: "Оплата еще обрабатывается банком. Обновите страницу через минуту.",
          });
        }
      } catch {
        // Ждем следующую попытку
      }
    }, 2000);

    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!tgAuthToken) return;
    const timer = setInterval(async () => {
      try {
        const res = await fetch(
          `/api/accounts/telegram-auth/status/${encodeURIComponent(tgAuthToken)}/`,
          { credentials: "include" }
        );
        if (res.status === 404) {
          clearInterval(timer);
          setTgAuthToken(null);
          setTgBotUrl(null);
          return;
        }
        if (!res.ok) return;
        const d = await res.json();
        if (d.status === "confirmed") {
          clearInterval(timer);
          setTgAuthToken(null);
          setTgBotUrl(null);
          setLinkMsg("Telegram успешно привязан к вашему аккаунту!");
          loadProfile();
        }
      } catch {
        // Ждем следующую попытку
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [tgAuthToken]);

  async function handleLogout() {
    await fetch("/api/accounts/logout/", {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRFToken": getCookie("csrftoken") },
    });
    window.dispatchEvent(new Event("linkori-auth-changed"));
    router.replace("/");
  }

  async function handleSendLinkEmail(e: FormEvent) {
    e.preventDefault();
    setLinkErr(null);
    setLinkMsg(null);
    const res = await fetch("/api/accounts/email-auth/request/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: linkEmail.trim() }),
    });
    const d = await res.json();
    if (!res.ok) {
      setLinkErr(d.detail || "Не удалось отправить код.");
      return;
    }
    setLinkOtpSent(true);
  }

  async function handleVerifyLinkEmail(e: FormEvent) {
    e.preventDefault();
    setLinkErr(null);
    const res = await fetch("/api/accounts/email-auth/verify/", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({
        email: linkEmail.trim(),
        code: linkOtpCode.trim(),
        accepted_legal: true,
      }),
    });
    const d = await res.json();
    if (!res.ok) {
      setLinkErr(d.detail || "Ошибка привязки email.");
      return;
    }
    setLinkOtpSent(false);
    setLinkOtpCode("");
    setLinkMsg("Email успешно привязан к вашему аккаунту!");
    loadProfile();
  }

  async function handleStartLinkTelegram() {
    setLinkErr(null);
    setLinkMsg(null);
    const res = await fetch("/api/accounts/telegram-auth/init/", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({ accepted_legal: true }),
    });
    const d = await res.json();
    if (!res.ok) {
      setLinkErr(d.detail || "Не удалось создать ссылку привязки.");
      return;
    }
    setTgAuthToken(d.auth_token);
    setTgBotUrl(d.bot_url);
    window.open(d.bot_url, "_blank", "noopener,noreferrer");
  }

  function copyText(text: string) {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  if (!data) {
    return (
      <section className="mx-auto max-w-4xl px-4 py-20 text-center text-sm text-[#9e96cc]">
        Загрузка профиля...
      </section>
    );
  }

  const sub = data.active_subscription;
  const subUrl = sub ? `https://sub.linkori.org/${sub.sub_token}` : null;

  return (
    <section className="mx-auto max-w-4xl px-4 py-12">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-[#efeaff]">Личный кабинет</h1>
          <p className="mt-1 text-sm text-[#9e96cc]">
            {data.user.telegram_id ? (
              <>
                Telegram:{" "}
                <span className="font-semibold text-[#7ae9eb]">
                  @{data.user.telegram_username}
                </span>
              </>
            ) : (
              <>
                Email: <span className="font-semibold text-[#7ae9eb]">{data.user.email}</span>
              </>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="rounded-xl border border-[#8b5cf6]/35 bg-[#160e31] px-4 py-2 text-xs font-semibold text-[#d8d0ff] transition hover:border-[#ec5f49]/50 hover:text-[#ff9a8a]"
        >
          Выйти
        </button>
      </div>

      {paymentBanner && (
        <div
          className={`mt-6 rounded-[18px] border p-4 text-sm font-medium ${
            paymentBanner.type === "paid"
              ? "border-[#2fbf8a]/40 bg-[#2fbf8a]/15 text-[#6ff0bd]"
              : paymentBanner.type === "failed"
                ? "border-[#ec5f49]/40 bg-[#ec5f49]/15 text-[#ff9a8a]"
                : "border-[#7ae9eb]/40 bg-[#7ae9eb]/10 text-[#7ae9eb]"
          }`}
        >
          {paymentBanner.text}
        </div>
      )}

      <div className="mt-8 grid gap-5 sm:grid-cols-3">
        <div className="rounded-[22px] border border-[#8b5cf6]/25 bg-[#160e31] p-5">
          <div className="text-xs text-[#9e96cc]">Бонус за рефералов (+15% дней)</div>
          <div className="mt-2 text-2xl font-bold text-[#7ae9eb]">
            {formatBonusTime(data.referral_bonus_hours)}
          </div>
        </div>
        <div className="rounded-[22px] border border-[#8b5cf6]/25 bg-[#160e31] p-5">
          <div className="text-xs text-[#9e96cc]">Приглашено друзей</div>
          <div className="mt-2 text-2xl font-bold text-[#efeaff]">{data.referrals_count}</div>
        </div>
        <div className="rounded-[22px] border border-[#8b5cf6]/25 bg-[#160e31] p-5">
          <div className="text-xs text-[#9e96cc]">Реферальный код</div>
          <div className="mt-2 font-mono text-lg font-bold text-[#fbcfe8]">
            {data.user.referral_code}
          </div>
        </div>
      </div>

      <div className="mt-6 rounded-[22px] border border-[#7ae9eb]/35 bg-[#160e31] p-6 shadow-[0_20px_50px_-15px_rgba(6,3,20,0.9)]">
        <h2 className="text-xl font-bold text-[#efeaff]">Статус доступа</h2>

        {sub && subUrl ? (
          <div className="mt-4 space-y-4">
            <div className="flex flex-wrap gap-6 text-sm text-[#d8d0ff]">
              <div>
                Тариф: <span className="font-semibold text-[#7ae9eb]">{sub.plan_name}</span>
              </div>
              <div>
                Действует до:{" "}
                <span className="font-semibold text-[#efeaff]">
                  {new Date(sub.expires_at).toLocaleDateString("ru-RU")}
                </span>
              </div>
              <div>
                Устройства:{" "}
                <span className="font-semibold text-[#efeaff]">
                  {data.devices_count} / {sub.max_devices}
                </span>
              </div>
            </div>

            <div className="rounded-[14px] border border-[#8b5cf6]/30 bg-[#0d0720] p-3.5">
              <div className="text-xs text-[#9e96cc]">Ссылка подключения:</div>
              <div className="mt-1.5 flex flex-wrap items-center justify-between gap-3">
                <code className="break-all text-xs text-[#7ae9eb]">{subUrl}</code>
                <button
                  type="button"
                  onClick={() => copyText(subUrl)}
                  className="rounded-lg bg-[#7ae9eb] px-3 py-1.5 text-xs font-bold text-[#120b28] transition hover:bg-[#9ef1f3]"
                >
                  {copied ? "Скопировано" : "Копировать"}
                </button>
              </div>
            </div>

            <div className="flex flex-wrap gap-2.5">
              <a
                href={`${subUrl}/open/happ`}
                className="rounded-xl border border-[#7ae9eb]/35 bg-[#7ae9eb]/10 px-4 py-2 text-xs font-semibold text-[#7ae9eb] hover:bg-[#7ae9eb]/20"
              >
                Открыть в Happ
              </a>
              <a
                href={`${subUrl}/open/v2raytun`}
                className="rounded-xl border border-[#7ae9eb]/35 bg-[#7ae9eb]/10 px-4 py-2 text-xs font-semibold text-[#7ae9eb] hover:bg-[#7ae9eb]/20"
              >
                Открыть в v2RayTun
              </a>
              <a
                href={`${subUrl}/open/hiddify`}
                className="rounded-xl border border-[#7ae9eb]/35 bg-[#7ae9eb]/10 px-4 py-2 text-xs font-semibold text-[#7ae9eb] hover:bg-[#7ae9eb]/20"
              >
                Открыть в Hiddify
              </a>
              <Link
                href="/#pricing"
                className="rounded-xl border border-[#f472b6]/40 bg-[#f472b6]/10 px-4 py-2 text-xs font-semibold text-[#fbcfe8] hover:bg-[#f472b6]/20"
              >
                Продлить доступ
              </Link>
            </div>
          </div>
        ) : (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-4">
            <p className="text-sm text-[#9e96cc]">Активной подписки пока нет.</p>
            <Link
              href="/#pricing"
              className="rounded-[14px] bg-[#7ae9eb] px-5 py-2.5 text-sm font-bold text-[#120b28] transition hover:bg-[#9ef1f3]"
            >
              Выбрать тариф
            </Link>
          </div>
        )}
      </div>

      {/* Блок привязки второго способа входа (Email <-> Telegram) */}
      <div className="mt-6 rounded-[22px] border border-[#8b5cf6]/25 bg-[#160e31] p-6">
        <h2 className="text-lg font-bold text-[#efeaff]">Привязка аккаунтов</h2>
        <p className="mt-1 text-xs text-[#9e96cc]">
          Свяжите Email и Telegram, чтобы входить любым удобным способом в единый профиль.
        </p>

        {linkMsg && (
          <div className="mt-3 rounded-[14px] border border-[#2fbf8a]/40 bg-[#2fbf8a]/15 p-3 text-xs text-[#6ff0bd]">
            {linkMsg}
          </div>
        )}
        {linkErr && (
          <div className="mt-3 rounded-[14px] border border-[#ec5f49]/40 bg-[#2d1020] p-3 text-xs text-[#ff9a8a]">
            {linkErr}
          </div>
        )}

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div className="rounded-[16px] border border-[#8b5cf6]/25 bg-[#0d0720] p-4">
            <div className="text-xs font-semibold text-[#efeaff]">Email</div>
            {data.user.email ? (
              <div className="mt-2 text-xs text-[#7ae9eb]">Привязан: {data.user.email}</div>
            ) : !linkOtpSent ? (
              <form onSubmit={handleSendLinkEmail} className="mt-2.5 flex gap-2">
                <input
                  type="email"
                  required
                  value={linkEmail}
                  onChange={(e) => setLinkEmail(e.target.value)}
                  placeholder="name@gmail.com"
                  className="min-w-0 flex-1 rounded-xl border border-[#8b5cf6]/30 bg-[#160e31] px-3 py-1.5 text-xs text-[#efeaff] focus:border-[#7ae9eb] focus:outline-none"
                />
                <button
                  type="submit"
                  className="rounded-xl bg-[#7ae9eb] px-3 py-1.5 text-xs font-bold text-[#120b28]"
                >
                  Код
                </button>
              </form>
            ) : (
              <form onSubmit={handleVerifyLinkEmail} className="mt-2.5 flex gap-2">
                <input
                  type="text"
                  required
                  value={linkOtpCode}
                  onChange={(e) => setLinkOtpCode(e.target.value)}
                  placeholder="Код из письма"
                  className="min-w-0 flex-1 rounded-xl border border-[#8b5cf6]/30 bg-[#160e31] px-3 py-1.5 text-xs text-[#efeaff]"
                />
                <button
                  type="submit"
                  className="rounded-xl bg-[#7ae9eb] px-3 py-1.5 text-xs font-bold text-[#120b28]"
                >
                  Привязать
                </button>
              </form>
            )}
          </div>

          <div className="rounded-[16px] border border-[#8b5cf6]/25 bg-[#0d0720] p-4">
            <div className="text-xs font-semibold text-[#efeaff]">Telegram</div>
            {data.user.telegram_id ? (
              <div className="mt-2 text-xs text-[#7ae9eb]">
                Привязан: @{data.user.telegram_username}
              </div>
            ) : tgBotUrl ? (
              <a
                href={tgBotUrl}
                target="_blank"
                rel="noreferrer"
                className="mt-2.5 inline-block rounded-xl bg-[#7ae9eb] px-3.5 py-2 text-xs font-bold text-[#120b28]"
              >
                Подтвердить в @linkoribot
              </a>
            ) : (
              <button
                type="button"
                onClick={handleStartLinkTelegram}
                className="mt-2.5 rounded-xl border border-[#7ae9eb]/40 bg-[#7ae9eb]/10 px-3.5 py-2 text-xs font-semibold text-[#7ae9eb] hover:bg-[#7ae9eb]/20"
              >
                Привязать Telegram
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}