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
      <Link href="/" className="text-sm text-[#7ae9eb] hover:underline">
        ← На главную
      </Link>
      <h1 className="mt-4 text-3xl font-bold text-[#efeaff]">{title}</h1>
      <div className="mt-6 whitespace-pre-wrap rounded-[22px] border border-[#8b5cf6]/25 bg-[#160e31]/95 p-6 text-sm leading-relaxed text-[#d8d0ff] shadow-[0_20px_50px_-15px_rgba(6,3,20,0.9)] sm:p-8">
        {text}
      </div>
    </section>
  );
}