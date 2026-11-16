"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { hasLocalLegalConsent, setLocalLegalConsent } from "@/lib/consent";

const UNBLOCKED_PATHS = new Set(["/privacy", "/terms"]);

export function ConsentGate() {
  const pathname = usePathname();
  const [accepted, setAccepted] = useState<boolean | null>(null);

  useEffect(() => {
    setAccepted(hasLocalLegalConsent());
  }, []);

  const isUnblockedRoute = UNBLOCKED_PATHS.has(pathname || "");
  const shouldBlock = accepted === false && !isUnblockedRoute;

  useEffect(() => {
    if (shouldBlock) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [shouldBlock]);

  function handleAccept() {
    setLocalLegalConsent();
    setAccepted(true);
  }

  if (!shouldBlock) {
    return null;
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#060211]/90 p-4 backdrop-blur-md"
    >
      <div className="w-full max-w-lg rounded-[22px] border border-[#7ae9eb]/40 bg-[#130b2c] p-7 shadow-[0_26px_70px_rgba(4,1,16,0.98),0_0_45px_-14px_rgba(122,233,235,0.35)]">
        <span className="inline-flex items-center rounded-full border border-[#f472b6]/40 bg-[#f472b6]/10 px-3 py-0.5 text-xs font-semibold text-[#fbcfe8]">
          Согласие и cookies
        </span>

        <h2 className="mt-4 text-2xl font-bold text-[#efeaff]">
          Перед началом работы с Linkori
        </h2>

        <p className="mt-3 text-sm leading-relaxed text-[#9e96cc]">
          Для продолжения работы с сайтом необходимо принять использование файлов cookie, а также
          условия{" "}
          <Link href="/terms" className="text-[#7ae9eb] underline hover:text-[#9ef1f3]">
            Пользовательского соглашения
          </Link>{" "}
          и{" "}
          <Link href="/privacy" className="text-[#7ae9eb] underline hover:text-[#9ef1f3]">
            Политики конфиденциальности
          </Link>
          .
        </p>

        <div className="mt-5 rounded-[14px] border border-[#8b5cf6]/25 bg-[#0d0720] p-3.5 text-xs leading-relaxed text-[#a8a2d4]">
          Продолжая использование сервиса, вы подтверждаете ознакомление с документами и берете на
          себя ответственность за соблюдение правил использования инфраструктуры.
        </div>

        <button
          type="button"
          onClick={handleAccept}
          className="mt-6 w-full rounded-[14px] bg-[#7ae9eb] px-5 py-3.5 text-sm font-bold text-[#120b28] shadow-[0_0_26px_-6px_rgba(122,233,235,0.6)] transition hover:bg-[#9ef1f3]"
        >
          Принять файлы cookie и условия
        </button>
      </div>
    </div>
  );
}