"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { hasLocalLegalConsent } from "@/lib/consent";

export default function LoginPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [botUrl, setBotUrl] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
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
          window.dispatchEvent(new Event("linkori-auth-changed"));
          router.replace("/cabinet");
        }
      } catch {
        // Ждем следующую попытку
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [authToken, router]);

  async function handleStartAuth() {
    setLoading(true);
    setErrorMsg(null);

    try {
      const res = await fetch("/api/accounts/telegram-auth/init/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          accepted_legal: hasLocalLegalConsent(),
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
      setLoading(false);
    }
  }

  return (
    <section className="mx-auto flex max-w-6xl items-center justify-center px-4 py-20">
      <div className="w-full max-w-md rounded-[22px] border border-[#7ae9eb]/30 bg-[#130b2c] p-7 shadow-[0_24px_60px_rgba(4,1,16,0.95),0_0_40px_-14px_rgba(122,233,235,0.3)]">
        <span className="inline-flex items-center rounded-full border border-[#f472b6]/35 bg-[#f472b6]/10 px-2.5 py-0.5 text-[11px] font-semibold text-[#fbcfe8]">
          Личный кабинет
        </span>
        <h1 className="mt-3 text-2xl font-bold text-[#efeaff]">Вход через Telegram</h1>
        <p className="mt-2 text-sm leading-relaxed text-[#9e96cc]">
          Единый аккаунт с Telegram-ботом: активный доступ, ссылка подключения и баланс.
        </p>

        {!botUrl ? (
          <div className="mt-6 space-y-3">
            <button
              type="button"
              disabled={loading}
              onClick={handleStartAuth}
              className="w-full rounded-[14px] bg-[#7ae9eb] px-4 py-3 text-sm font-bold text-[#120b28] shadow-[0_0_24px_-6px_rgba(122,233,235,0.55)] transition hover:bg-[#9ef1f3] disabled:opacity-60"
            >
              {loading ? "Создаем ссылку..." : "Войти через Telegram"}
            </button>
          </div>
        ) : (
          <div className="mt-6 space-y-4">
            <div className="rounded-[14px] border border-[#7ae9eb]/30 bg-[#0d0720] p-4 text-xs leading-relaxed text-[#d8d0ff]">
              Перейдите в бота <span className="font-semibold text-[#7ae9eb]">@linkoribot</span> и
              нажмите «Start» / «Подтвердить вход». Эта страница обновится автоматически.
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
              onClick={handleStartAuth}
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