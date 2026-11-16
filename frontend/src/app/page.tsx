import Link from "next/link";
import { PricingSection } from "@/components/PricingSection";
import { fetchPublicPlans } from "@/lib/api";

export const dynamic = "force-dynamic";

const FEATURES = [
  {
    title: "Шифрование в открытых сетях",
    text: "Надежная защита передаваемых данных в публичных Wi-Fi сетях кафе, отелей и аэропортов.",
  },
  {
    title: "Низкий пинг и стабильность",
    text: "Выделенные каналы и прямые маршруты для онлайн-игр, созвонов и повседневных задач.",
  },
  {
    title: "Современные протоколы",
    text: "VLESS, TLS/CDN-маршрутизация и Hysteria 2 для высокой скорости на любом типе сети.",
  },
  {
    title: "До 10 устройств одновременно",
    text: "Подключайте смартфоны, ноутбуки и домашние ПК по одной персональной ссылке.",
  },
];

const FAQS = [
  {
    q: "Как подключиться после оплаты?",
    a: "Выберите тариф на сайте или в боте @linkoribot, укажите email и оплатите заказ. Сразу после оплаты откроется персональная ссылка подписки — вставьте ее в приложение, и соединение заработает за минуту.",
  },
  {
    q: "На каких устройствах работает подключение?",
    a: "На iOS, Android, Windows, macOS и Linux через приложения Happ, v2RayTun или Hiddify. Одна подписка поддерживает до 10 устройств.",
  },
  {
    q: "Как связаться со службой поддержки?",
    a: "Напишите оператору поддержки в Telegram @Linkorisupport или на почту support@linkori.org.",
  },
];

export default async function HomePage() {
  const plans = await fetchPublicPlans();

  return (
    <>
      <section className="border-b border-[var(--border)]">
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-16 lg:grid-cols-[1fr_320px] lg:py-20">
          <div>
            <span className="inline-flex items-center rounded-full border border-[var(--accent)]/35 bg-[var(--accent-soft)] px-3 py-1 text-xs font-semibold text-[var(--accent)]">
              Сетевая инфраструктура нового поколения
            </span>
            <h1 className="mt-5 text-4xl font-extrabold tracking-tight text-[var(--text)] sm:text-5xl">
              Приватный прокси-сервис для защищенного и быстрого интернета
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-relaxed text-[var(--text-muted)] sm:text-lg">
              Шифрование соединения, низкий пинг и стабильный канал на iOS, Android, Windows и
              macOS. До 10 устройств по одной ссылке.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3.5">
              <Link
                href="/#pricing"
                className="rounded-[14px] bg-[var(--accent)] px-6 py-3.5 text-sm font-bold text-[#150d2e] transition hover:bg-[var(--accent-2)]"
              >
                Выбрать тариф
              </Link>
              <a
                href="https://t.me/linkoribot"
                target="_blank"
                rel="noreferrer"
                className="rounded-[14px] border border-[var(--accent)]/35 bg-[var(--accent-soft)] px-6 py-3.5 text-sm font-semibold text-[var(--accent)] transition hover:bg-[var(--accent)]/20"
              >
                Открыть бота @linkoribot
              </a>
              <a
                href="https://t.me/Linkorisupport"
                target="_blank"
                rel="noreferrer"
                className="rounded-[14px] border border-[var(--border)] bg-[var(--surface)] px-6 py-3.5 text-sm font-medium text-[var(--text)] transition hover:bg-[var(--surface-hover)]"
              >
                Поддержка
              </a>
            </div>
          </div>

          <div className="relative mx-auto w-full max-w-[280px] lg:max-w-[320px]">
            <div
              className="absolute -inset-4 rounded-[30px] opacity-80 blur-2xl"
              style={{
                background:
                  "radial-gradient(circle, rgba(150,90,255,0.45) 0%, rgba(122,233,235,0.25) 60%, transparent 100%)",
              }}
            />
            <div
              className="relative overflow-hidden rounded-[22px] border border-white/15 bg-white/95 p-2"
              style={{ boxShadow: "var(--shadow-card)" }}
            >
              <img
                src="/linkori-mascot.jpg"
                alt="Linkori"
                className="h-auto w-full rounded-[16px] object-cover"
              />
            </div>
          </div>
        </div>
      </section>

      <section id="features" className="mx-auto max-w-6xl px-4 py-14">
        <h2 className="text-2xl font-bold text-[var(--text)] sm:text-3xl">Преимущества</h2>
        <div className="mt-8 grid gap-5 sm:grid-cols-2">
          {FEATURES.map((item) => (
            <div
              key={item.title}
              className="rounded-[22px] border border-[var(--border)] bg-[var(--surface)] p-6 transition hover:bg-[var(--surface-hover)]"
              style={{ boxShadow: "var(--shadow-card)" }}
            >
              <h3 className="text-lg font-semibold text-[var(--text)]">{item.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[var(--text-muted)]">{item.text}</p>
            </div>
          ))}
        </div>
      </section>

      <PricingSection plans={plans} />

      <section id="faq" className="mx-auto max-w-4xl px-4 py-14">
        <h2 className="text-center text-2xl font-bold text-[var(--text)] sm:text-3xl">
          Частые вопросы
        </h2>
        <div className="mt-8 space-y-4">
          {FAQS.map((item) => (
            <div
              key={item.q}
              className="rounded-[22px] border border-[var(--border)] bg-[var(--surface)] p-5"
            >
              <h3 className="text-base font-semibold text-[var(--text)]">{item.q}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[var(--text-muted)]">{item.a}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
