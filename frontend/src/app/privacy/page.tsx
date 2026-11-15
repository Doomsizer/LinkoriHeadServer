import Link from "next/link";
import { fetchLegalDocs } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function PrivacyPage() {
  const docs = await fetchLegalDocs();
  const title = docs?.privacy_policy.title || "Политика конфиденциальности";
  const text =
    docs?.privacy_policy.text ||
    "Политика конфиденциальности сервиса Linkori (linkori.org). По вопросам обработки данных обращайтесь на support@linkori.org или @linkori_support.";

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
