import Link from "next/link";
import { fetchLegalDocs } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function TermsPage() {
  const docs = await fetchLegalDocs();
  const title = docs?.terms_of_service.title || "Пользовательское соглашение";
  const text =
    docs?.terms_of_service.text ||
    "Пользовательское соглашение сервиса Linkori (linkori.org). Использование приватного прокси-сервиса лежит полностью на Пользователе. Поддержка: support@linkori.org, @Linkorisupport. Бот: @linkoribot.";

  return (
    <section className="mx-auto max-w-4xl px-4 py-14">
      <Link href="/" className="text-sm text-blue-400 hover:underline">
        ← На главную
      </Link>
      <h1 className="mt-4 text-3xl font-bold text-white">{title}</h1>
      <div className="mt-6 whitespace-pre-wrap rounded-2xl border border-border bg-surface/80 p-6 text-sm leading-relaxed text-slate-300 sm:p-8">
        {text}
      </div>
    </section>
  );
}