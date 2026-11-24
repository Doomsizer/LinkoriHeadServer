"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { hasLocalLegalConsent } from "@/lib/consent";
import {
  captureReferralFromUrl,
  clearPendingRefCode,
  getPendingRefCode,
} from "@/lib/referral";

function getCookie(name: string): string {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : "";
}

export default function LoginPage() {
  const router = useRouter();
  const [tab, setTab] = useState<"email" | "telegram">("email");

  const [email, setEmail] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  const [emailLoading, setEmailLoading] = useState(false);

  const [tgLoading, setTgLoading] = useState(false);
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [botUrl, setBotUrl] = useState<string | null>(null);

  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    captureReferralFromUrl();
    fetch("/api/accounts/me/", { credentials: "include" })
      .then((res) => {
        if (res.ok) router.replace("/cabinet");
      })
      .catch(() => {});
  }, [router]);

  useEffect(() => {
    if (!authToken) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(
          `/api/accounts/telegram-auth/status/${encodeURIComponent(authToken)}/`,
          { credentials: "include" }
        );
        if (res.status === 404) {
          clearInterval(interval);
          setAuthToken(null);
          setBotUrl(null);
          setErrorMsg("Срок действия ссылки истек. Нажмите «Войти через Telegram» еще раз.");
          return;
        }
        if (!res.ok) return;

        const data = await res.json();
        if (data.status === "confirmed") {
          clearInterval(interval);
          clearPendingRefCode();
          window.dispatchEvent(new Event("linkori-auth-changed"));
          router.replace("/cabinet");
        }
      } catch {
        // Ждем следующую попытку
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [authToken, router]);

  async function handleRequestOtp(e: FormEvent) {
    e.preventDefault();
    setEmailLoading(true);
    setErrorMsg(null);

    try {
      const res = await fetch("/api/accounts/email-auth/request/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        setErrorMsg(data.detail || "Не удалось отправить код.");
        return;
      }
      setOtpSent(true);
    } catch {
      setErrorMsg("Ошибка соединения с сервером.");
    } finally {
      setEmailLoading(false);
    }
  }

  async function handleVerifyOtp(e: FormEvent) {
    e.preventDefault();
    setEmailLoading(true);
    setErrorMsg(null);

    try {
      const res = await fetch("/api/accounts/email-auth/verify/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        credentials: "include",
        body: JSON.stringify({
          email: email.trim(),
          code: otpCode.trim(),
          accepted_legal: hasLocalLegalConsent(),
          referred_by_code: getPendingRefCode(),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setErrorMsg(data.detail || "Неверный код подтверждения.");
        return;
      }
      clearPendingRefCode();
      window.dispatchEvent(new Event("linkori-auth-changed"));
      router.replace("/cabinet");
    } catch {
      setErrorMsg("Ошибка соединения с сервером.");
    } finally {
      setEmailLoading(false);
    }
  }

  async function handleStartTgAuth() {
    setTgLoading(true);
    setErrorMsg(null);

    try {
      const res = await fetch("/api/accounts/telegram-auth/init/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        credentials: "include",
        body: JSON.stringify({
          accepted_legal: hasLocalLegalConsent(),
          referred_by_code: getPendingRefCode(),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setErrorMsg(data.detail || "Не удалось создать ссылку для входа.");
        return;
      }

      setAuthToken(data.auth_token);
      setBotUrl(data.bot_url);
      window.open(data.bot_url, "_blank", "noopener,noreferrer");
    } catch {
      setErrorMsg("Ошибка соединения с сервером. Попробуйте еще раз.");
    } finally {
      setTgLoading(false);
    }
  }

  return (
    <section className="mx-auto flex max-w-6xl items-center justify-center px-4 py-16">
      <div className="w-full max-w-md rounded-[22px] border border-[#7ae9eb]/30 bg-[#130b2c] p-7 shadow-[0_24px_60px_rgba(4,1,16,0.95),0_0_40px_-14px_rgba(122,233,235,0.3)]">
        <span className="inline-flex items-center rounded-full border border-[#f472b6]/35 bg-[#f472b6]/10 px-2.5 py-0.5 text-[11px] font-semibold text-[#fbcfe8]">
          Личный кабинет
        </span>
        <h1 className="mt-3 text-2xl font-bold text-[#efeaff]">Вход в Linkori</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-[#9e96cc]">
          Войдите по Email (без пароля) или через Telegram-бота.
        </p>

        <div className="mt-5 grid grid-cols-2 gap-2 rounded-[14px] border border-[#8b5cf6]/25 bg-[#0d0720] p-1">
          <button
            type="button"
            onClick={() => {
              setTab("email");
              setErrorMsg(null);
            }}
            className={`rounded-[10px] py-2 text-xs font-bold transition ${
              tab === "email"
                ? "bg-[#7ae9eb] text-[#120b28]"
                : "text-[#9e96cc] hover:text-[#efeaff]"
            }`}
          >
            По Email
          </button>
          <button
            type="button"
            onClick={() => {
              setTab("telegram");
              setErrorMsg(null);
            }}
            className={`rounded-[10px] py-2 text-xs font-bold transition ${
              tab === "telegram"
                ? "bg-[#7ae9eb] text-[#120b28]"
                : "text-[#9e96cc] hover:text-[#efeaff]"
            }`}
          >
            Через Telegram
          </button>
        </div>

        {tab === "email" ? (
          !otpSent ? (
            <form onSubmit={handleRequestOtp} className="mt-5 space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-[#d8d0ff]">
                  Ваш Email (Gmail, Яндекс, Mail.ru, iCloud, Outlook)
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
              <button
                type="submit"
                disabled={emailLoading}
                className="w-full rounded-[14px] bg-[#7ae9eb] px-4 py-3 text-sm font-bold text-[#120b28] shadow-[0_0_24px_-6px_rgba(122,233,235,0.55)] transition hover:bg-[#9ef1f3] disabled:opacity-60"
              >
                {emailLoading ? "Отправка кода..." : "Получить код на почту"}
              </button>
            </form>
          ) : (
            <form onSubmit={handleVerifyOtp} className="mt-5 space-y-4">
              <div className="rounded-[14px] border border-[#7ae9eb]/25 bg-[#0d0720] p-3 text-xs text-[#d8d0ff]">
                Код отправлен на <span className="font-semibold text-[#7ae9eb]">{email}</span>
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-[#d8d0ff]">
                  6-значный код из письма
                </label>
                <input
                  type="text"
                  inputMode="numeric"
                  required
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value)}
                  placeholder="123456"
                  className="w-full rounded-[14px] border border-[#8b5cf6]/30 bg-[#0d0720] px-3.5 py-2.5 text-center font-mono text-lg tracking-widest text-[#efeaff] placeholder-[#7e75ad] focus:border-[#7ae9eb] focus:outline-none"
                />
              </div>
              <button
                type="submit"
                disabled={emailLoading}
                className="w-full rounded-[14px] bg-[#7ae9eb] px-4 py-3 text-sm font-bold text-[#120b28] shadow-[0_0_24px_-6px_rgba(122,233,235,0.55)] transition hover:bg-[#9ef1f3] disabled:opacity-60"
              >
                {emailLoading ? "Проверка..." : "Подтвердить и войти"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setOtpSent(false);
                  setOtpCode("");
                  setErrorMsg(null);
                }}
                className="w-full rounded-[14px] border border-[#8b5cf6]/30 bg-[#1b1238] px-4 py-2 text-xs text-[#9e96cc] hover:text-[#efeaff]"
              >
                Изменить email
              </button>
            </form>
          )
        ) : !botUrl ? (
          <div className="mt-5 space-y-3">
            <button
              type="button"
              disabled={tgLoading}
              onClick={handleStartTgAuth}
              className="w-full rounded-[14px] bg-[#7ae9eb] px-4 py-3 text-sm font-bold text-[#120b28] shadow-[0_0_24px_-6px_rgba(122,233,235,0.55)] transition hover:bg-[#9ef1f3] disabled:opacity-60"
            >
              {tgLoading ? "Создаем ссылку..." : "Войти через Telegram"}
            </button>
          </div>
        ) : (
          <div className="mt-5 space-y-4">
            <div className="rounded-[14px] border border-[#7ae9eb]/30 bg-[#0d0720] p-4 text-xs leading-relaxed text-[#d8d0ff]">
              Перейдите в бота <span className="font-semibold text-[#7ae9eb]">@linkoribot</span> и
              подтвердите вход. Эта страница обновится автоматически.
            </div>
            <a
              href={botUrl}
              target="_blank"
              rel="noreferrer"
              className="block w-full rounded-[14px] bg-[#7ae9eb] px-4 py-3 text-center text-sm font-bold text-[#120b28] shadow-[0_0_24px_-6px_rgba(122,233,235,0.55)] transition hover:bg-[#9ef1f3]"
            >
              Открыть @linkoribot для входа
            </a>
            <button
              type="button"
              onClick={handleStartTgAuth}
              className="w-full rounded-[14px] border border-[#8b5cf6]/35 bg-[#1b1238] px-4 py-2.5 text-xs font-medium text-[#9e96cc] transition hover:text-[#efeaff]"
            >
              Сгенерировать новую ссылку
            </button>
          </div>
        )}

        {errorMsg && (
          <div className="mt-4 rounded-[14px] border border-[#ec5f49]/40 bg-[#2d1020] p-3 text-xs text-[#ff9a8a]">
            {errorMsg}
          </div>
        )}

        <div className="mt-6 border-t border-[#8b5cf6]/20 pt-4 text-center">
          <Link href="/" className="text-xs text-[#9e96cc] transition hover:text-[#7ae9eb]">
            ← Вернуться на главную
          </Link>
        </div>
      </div>
    </section>
  );
}