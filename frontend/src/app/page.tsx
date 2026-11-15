import Link from "next/link";
import { PricingSection } from "@/components/PricingSection";
import { fetchPublicPlans } from "@/lib/api";

export const dynamic = "force-dynamic";

const FEATURES = [
  {
    title: "Шифрование в открытых сетях",
    text: "Надежная защита передаваемых данных при подключении через публичный Wi-Fi в кафе, отелях, аэропортах и коворкингах.",
  },
  {
    title: "Низкая задержка и стабильность",
    text: "Выделенные каналы и оптимальные сетевые маршруты для онлайн-игр, видеосвязи, облачной разработки и стриминга.",
  },
  {
    title: "Современные транспортные протоколы",
    text: "Поддержка VLESS, TLS/CDN-маршрутизации и Hysteria 2 для высокой скорости на мобильных и настольных устройствах.",
  },
  {
    title: "Единая конфигурация на 5 устройств",
    text: "Подключайте смартфон, ноутбук, планшет и домашний ПК по одной персональной ссылке подписки.",
  },
];

const FAQS = [
  {
    q: "Что именно предоставляет сервис Linkori?",
    a: "Linkori предоставляет технические услуги доступа к выделенной приватной прокси-инфраструктуре для защищенной передачи данных, повышения стабильности маршрутизации и безопасности в публичных сетях.",
  },
  {
    q: "На каких устройствах можно использовать подключение?",
    a: "Сервис работает на iOS, Android, Windows, macOS и Linux через популярные клиентские приложения (Happ, v2RayTun, Hiddify).",
  },
  {
    q: "Кто несет ответственность за действия при использовании прокси?",
    a: "Сервис предоставляет только техническую инфраструктуру связи. Ответственность за характер использования подключения и соблюдение законодательства лежит полностью на пользователе.",
  },
  {
    q: "Как связаться со службой поддержки?",
    a: "Вы можете написать напрямую оператору поддержки в Telegram @linkori_support или на почту support@linkori.org.",
  },
];

export default async function HomePage() {
  const plans = await fetchPublicPlans();

  return (
    <>
      <section className="relative overflow-hidden border-b border-border/70">
        <div className="mx-auto max-w-6xl px-4 py-20 sm:py-24">
          <div className="max-w-3xl">
            <span className="inline-flex items-center rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 text-xs font-medium text-blue-300">
              Приватная сетевая инфраструктура нового поколения
            </span>
            <h1 className="mt-5 text-4xl font-extrabold tracking-tight text-white sm:text-5xl">
              Приватный прокси-сервис для защищенного и быстрого интернета
            </h1>
            <p className="mt-5 text-base leading-relaxed text-slate-300 sm:text-lg">
              Стабильное зашифрованное соединение для повседневной работы, онлайн-игр и защиты
              трафика в публичных Wi-Fi сетях. Подключение за 1 минуту на iOS, Android, Windows и
              macOS.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Link
                href="/#pricing"
                className="rounded-xl bg-blue-600 px-6 py-3.5 text-sm font-semibold text-white transition hover:bg-blue-500"
              >
                Выбрать тариф и подключиться
              </Link>
              <a
                href="https://t.me/linkori_support"
                target="_blank"
                rel="noreferrer"
                className="rounded-xl border border-border bg-surface px-6 py-3.5 text-sm font-medium text-slate-200 transition hover:border-slate-500"
              >
                Написать в поддержку
              </a>
            </div>
          </div>
        </div>
      </section>

      <section id="features" className="mx-auto max-w-6xl px-4 py-16">
        <h2 className="text-2xl font-bold text-white sm:text-3xl">Почему выбирают Linkori</h2>
        <div className="mt-8 grid gap-6 sm:grid-cols-2">
          {FEATURES.map((item) => (
            <div
              key={item.title}
              className="rounded-2xl border border-border bg-surface/75 p-6"
            >
              <h3 className="text-lg font-semibold text-white">{item.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">{item.text}</p>
            </div>
          ))}
        </div>
      </section>

      <PricingSection plans={plans} />

      <section id="faq" className="mx-auto max-w-4xl px-4 py-16">
        <h2 className="text-center text-2xl font-bold text-white sm:text-3xl">
          Частые вопросы
        </h2>
        <div className="mt-8 space-y-4">
          {FAQS.map((item) => (
            <div key={item.q} className="rounded-2xl border border-border bg-surface/70 p-5">
              <h3 className="text-base font-semibold text-white">{item.q}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">{item.a}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
