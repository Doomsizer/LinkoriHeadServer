import Link from "next/link";

export function Footer() {
  return (
    <footer className="border-t border-border bg-surface/60">
      <div className="mx-auto max-w-6xl px-4 py-10">
        <div className="grid gap-8 md:grid-cols-3">
          <div>
            <div className="text-lg font-bold text-white">Linkori</div>
            <p className="mt-2 text-sm leading-relaxed text-slate-400">
              Приватный прокси-сервис для защищенного шифрованного подключения, стабильной
              маршрутизации и безопасной работы в публичных и домашних сетях.
            </p>
            <p className="mt-3 text-xs text-slate-500">
              Использование прокси-инфраструктуры осуществляется пользователем самостоятельно и под
              его полную ответственность.
            </p>
          </div>

          <div>
            <div className="text-sm font-semibold text-white">Документы и бот</div>
            <ul className="mt-3 space-y-2 text-sm text-slate-400">
              <li>
                <Link href="/privacy" className="transition hover:text-white">
                  Политика конфиденциальности
                </Link>
              </li>
              <li>
                <Link href="/terms" className="transition hover:text-white">
                  Пользовательское соглашение
                </Link>
              </li>
              <li>
                <Link href="/#pricing" className="transition hover:text-white">
                  Тарифы и оплата
                </Link>
              </li>
              <li>
                <a
                  href="https://t.me/linkoribot"
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-400 hover:underline"
                >
                  Telegram-бот @linkoribot
                </a>
              </li>
            </ul>
          </div>

          <div>
            <div className="text-sm font-semibold text-white">Поддержка и контакты</div>
            <ul className="mt-3 space-y-2 text-sm text-slate-400">
              <li>
                Поддержка Telegram:{" "}
                <a
                  href="https://t.me/Linkorisupport"
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-400 hover:underline"
                >
                  @Linkorisupport
                </a>
              </li>
              <li>
                Email:{" "}
                <a href="mailto:support@linkori.org" className="text-blue-400 hover:underline">
                  support@linkori.org
                </a>
              </li>
              <li className="text-xs text-slate-500">
                Лимит одной транзакции: до 10 000 руб.
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-8 flex flex-col items-start justify-between gap-3 border-t border-border/70 pt-6 text-xs text-slate-500 sm:flex-row sm:items-center">
          <span>© 2026 Linkori. Все права защищены.</span>
          <span className="rounded border border-border px-2 py-0.5 font-mono text-slate-400">
            ОPLAT
          </span>
        </div>
      </div>
    </footer>
  );
}