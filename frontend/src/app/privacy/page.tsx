import Link from "next/link";
import { fetchLegalDocs } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function PrivacyPage() {
  const docs = await fetchLegalDocs();
  const title = docs?.privacy_policy.title || "Политика конфиденциальности";
  const text =
    docs?.privacy_policy.text ||
    "Политика конфиденциальности сервиса Linkori (linkori.org). По вопросам обработки данных обращайтесь на support@linkori.org или @Linkorisupport.";

  return (
    <section className="mx-auto max-w-4xl px-4 py-14">
      <Link href="/" className="text-sm text-[var(--accent)] hover:underline">
        ← На главную
      </Link>
      <h1 className="mt-4 text-3xl font-bold text-[var(--text)]">{title}</h1>
      <div
        className="mt-6 whitespace-pre-wrap rounded-[22px] border border-[var(--border)] bg-[var(--surface)] p-6 text-sm leading-relaxed text-[var(--text)]/90 sm:p-8"
        style={{ boxShadow: "var(--shadow-card)" }}
      >
        {text}
      </div>
    </section>
  );
}
