import Link from "next/link";

export function Footer() {
  return (
    <footer className="border-t border-[#8b5cf6]/20 bg-[#100924]/90">
      <div className="mx-auto max-w-6xl px-4 py-10">
        <div className="grid gap-8 md:grid-cols-3">
          <div>
            <div className="flex items-center gap-2 text-lg font-extrabold text-[#efeaff]">
              <span className="h-2 w-2 rounded-full bg-[#7ae9eb] shadow-[0_0_10px_#7ae9eb]" />
              <span>Linkori</span>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-[#9e96cc]">
              Высокоскоростной прокси-сервис для шифрования трафика, стабильной маршрутизации и
              безопасной работы в сети.
            </p>
            <p className="mt-3 text-xs text-[#7e75ad]">
              Использование инфраструктуры осуществляется пользователем самостоятельно и под его
              полную ответственность.
            </p>
          </div>

          <div>
            <div className="text-sm font-semibold text-[#efeaff]">Документы и бот</div>
            <ul className="mt-3 space-y-2 text-sm text-[#9e96cc]">
              <li>
                <Link href="/privacy" className="transition hover:text-[#7ae9eb]">
                  Политика конфиденциальности
                </Link>
              </li>
              <li>
                <Link href="/terms" className="transition hover:text-[#7ae9eb]">
                  Пользовательское соглашение
                </Link>
              </li>
              <li>
                <Link href="/#pricing" className="transition hover:text-[#7ae9eb]">
                  Тарифы
                </Link>
              </li>
              <li>
                <a
                  href="https://t.me/linkoribot"
                  target="_blank"
                  rel="noreferrer"
                  className="text-[#7ae9eb] hover:underline"
                >
                  Telegram-бот @linkoribot
                </a>
              </li>
            </ul>
          </div>

          <div>
            <div className="text-sm font-semibold text-[#efeaff]">Поддержка и контакты</div>
            <ul className="mt-3 space-y-2 text-sm text-[#9e96cc]">
              <li>
                Telegram:{" "}
                <a
                  href="https://t.me/Linkorisupport"
                  target="_blank"
                  rel="noreferrer"
                  className="text-[#7ae9eb] hover:underline"
                >
                  @Linkorisupport
                </a>
              </li>
              <li>
                Email:{" "}
                <a href="mailto:support@linkori.org" className="text-[#7ae9eb] hover:underline">
                  support@linkori.org
                </a>
              </li>
              <li className="text-xs text-[#7e75ad]">
                Лимит одной транзакции: до 10 000 руб.
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-8 flex flex-col items-start justify-between gap-3 border-t border-[#8b5cf6]/15 pt-6 text-xs text-[#7e75ad] sm:flex-row sm:items-center">
          <span>© 2026 Linkori. Все права защищены.</span>
          <span className="rounded-lg border border-[#8b5cf6]/25 bg-[#160e31] px-2.5 py-0.5 font-mono text-[#9e96cc]">
            ОPLAT
          </span>
        </div>
      </div>
    </footer>
  );
}