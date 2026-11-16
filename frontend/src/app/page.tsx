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
      <section className="border-b border-[#8b5cf6]/20">
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-14 lg:grid-cols-[1fr_340px] lg:py-20">
          <div>
            <span className="inline-flex items-center rounded-full border border-[#f472b6]/35 bg-[#f472b6]/10 px-3 py-1 text-xs font-semibold text-[#fbcfe8]">
              Сетевая инфраструктура нового поколения
            </span>
            <h1 className="mt-5 text-4xl font-extrabold tracking-tight text-[#efeaff] sm:text-5xl">
              Приватный прокси-сервис для защищенного и быстрого интернета
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-relaxed text-[#9e96cc] sm:text-lg">
              Шифрование соединения, низкий пинг и стабильный канал на iOS, Android, Windows и
              macOS. До 10 устройств по одной ссылке.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3.5">
              <Link
                href="/#pricing"
                className="rounded-[14px] bg-[#7ae9eb] px-6 py-3.5 text-sm font-bold text-[#120b28] shadow-[0_0_26px_-6px_rgba(122,233,235,0.6)] transition hover:bg-[#9ef1f3]"
              >
                Выбрать тариф
              </Link>
              <a
                href="https://t.me/linkoribot"
                target="_blank"
                rel="noreferrer"
                className="rounded-[14px] border border-[#7ae9eb]/35 bg-[#7ae9eb]/10 px-6 py-3.5 text-sm font-semibold text-[#7ae9eb] transition hover:bg-[#7ae9eb]/20 hover:shadow-[0_0_22px_-6px_rgba(122,233,235,0.45)]"
              >
                Открыть бота @linkoribot
              </a>
              <a
                href="https://t.me/Linkorisupport"
                target="_blank"
                rel="noreferrer"
                className="rounded-[14px] border border-[#8b5cf6]/30 bg-[#160e31] px-6 py-3.5 text-sm font-medium text-[#d8d0ff] transition hover:border-[#f472b6]/50 hover:text-[#fbcfe8]"
              >
                Поддержка
              </a>
            </div>
          </div>

          <div className="relative mx-auto flex w-full max-w-[300px] items-center justify-center lg:max-w-[340px]">
            <div
              className="pointer-events-none absolute inset-0 rounded-full blur-3xl"
              style={{
                background:
                  "radial-gradient(circle at 48% 42%, rgba(244, 114, 182, 0.28) 0%, rgba(122, 233, 235, 0.24) 48%, rgba(18, 11, 40, 0) 76%)",
              }}
            />
            <div
              className="relative -rotate-2 overflow-hidden rounded-[28px] border border-[#7ae9eb]/20 p-2 transition-transform duration-500 hover:rotate-0"
              style={{
                background:
                  "radial-gradient(circle at 50% 45%, rgba(34, 21, 72, 0.72) 0%, rgba(14, 8, 34, 0.96) 82%)",
                boxShadow:
                  "0 26px 60px -14px rgba(5, 2, 18, 0.95), 0 0 38px -14px rgba(122, 233, 235, 0.35), inset 0 0 36px rgba(10, 5, 26, 0.92)",
              }}
            >
              <img
                src="/linkori-mascot.png"
                alt="Linkori"
                className="relative z-10 h-auto w-full object-contain"
                style={{
                  maskImage:
                    "radial-gradient(ellipse 90% 90% at 50% 46%, #000 62%, transparent 100%)",
                  WebkitMaskImage:
                    "radial-gradient(ellipse 90% 90% at 50% 46%, #000 62%, transparent 100%)",
                  filter: "drop-shadow(0 0 22px rgba(122, 233, 235, 0.22))",
                }}
              />
            </div>
          </div>
        </div>
      </section>

      <section id="features" className="mx-auto max-w-6xl px-4 py-14">
        <h2 className="text-2xl font-bold text-[#efeaff] sm:text-3xl">Преимущества</h2>
        <div className="mt-8 grid gap-5 sm:grid-cols-2">
          {FEATURES.map((item) => (
            <div
              key={item.title}
              className="rounded-[22px] border border-[#8b5cf6]/25 bg-[#160e31]/95 p-6 shadow-[0_18px_40px_-14px_rgba(6,3,20,0.85)] transition hover:border-[#7ae9eb]/35"
            >
              <h3 className="text-lg font-semibold text-[#efeaff]">{item.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[#9e96cc]">{item.text}</p>
            </div>
          ))}
        </div>
      </section>

      <PricingSection plans={plans} />

      <section id="faq" className="mx-auto max-w-4xl px-4 py-14">
        <h2 className="text-center text-2xl font-bold text-[#efeaff] sm:text-3xl">
          Частые вопросы
        </h2>
        <div className="mt-8 space-y-4">
          {FAQS.map((item) => (
            <div
              key={item.q}
              className="rounded-[22px] border border-[#8b5cf6]/25 bg-[#160e31]/95 p-5 shadow-[0_14px_32px_-12px_rgba(6,3,20,0.8)]"
            >
              <h3 className="text-base font-semibold text-[#efeaff]">{item.q}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[#9e96cc]">{item.a}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}