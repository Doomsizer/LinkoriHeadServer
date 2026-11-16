"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { hasLocalLegalConsent } from "@/lib/consent";

export default function LoginPage() {
  const [clicked, setClicked] = useState(false);
  const [legalAccepted, setLegalAccepted] = useState(false);

  useEffect(() => {
    setLegalAccepted(hasLocalLegalConsent());
  }, []);

  return (
    <section className="mx-auto flex max-w-6xl items-center justify-center px-4 py-20">
      <div className="w-full max-w-md rounded-[22px] border border-[#7ae9eb]/30 bg-[#130b2c] p-7 shadow-[0_24px_60px_rgba(4,1,16,0.95),0_0_40px_-14px_rgba(122,233,235,0.3)]">
        <span className="inline-flex items-center rounded-full border border-[#f472b6]/35 bg-[#f472b6]/10 px-2.5 py-0.5 text-[11px] font-semibold text-[#fbcfe8]">
          Личный кабинет
        </span>
        <h1 className="mt-3 text-2xl font-bold text-[#efeaff]">Вход через Telegram</h1>
        <p className="mt-2 text-sm leading-relaxed text-[#9e96cc]">
          Единый аккаунт с Telegram-ботом: статус доступа, управление устройствами и история
          оплат.
        </p>

        <div className="mt-6 space-y-3">
          <button
            type="button"
            onClick={() => setClicked(true)}
            className="w-full rounded-[14px] bg-[#7ae9eb] px-4 py-3 text-sm font-bold text-[#120b28] shadow-[0_0_24px_-6px_rgba(122,233,235,0.55)] transition hover:bg-[#9ef1f3]"
          >
            Войти через Telegram
          </button>

          <a
            href="https://t.me/linkoribot"
            target="_blank"
            rel="noreferrer"
            className="block w-full rounded-[14px] border border-[#8b5cf6]/35 bg-[#1b1238] px-4 py-3 text-center text-sm font-semibold text-[#d8d0ff] transition hover:border-[#7ae9eb]/45 hover:text-[#7ae9eb]"
          >
            Открыть бота @linkoribot
          </a>
        </div>

        {clicked && (
          <div className="mt-4 rounded-[14px] border border-[#f472b6]/35 bg-[#23123c] p-3.5 text-xs leading-relaxed text-[#fbcfe8]">
            Веб-авторизация через Telegram находится на этапе подключения.
            {legalAccepted &&
              " Ваше согласие с условиями сохранено в браузере и применится автоматически при входе."}
            {" "}Сейчас управлять подключением можно через{" "}
            <a
              href="https://t.me/linkoribot"
              target="_blank"
              rel="noreferrer"
              className="text-[#7ae9eb] underline"
            >
              @linkoribot
            </a>
            .
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