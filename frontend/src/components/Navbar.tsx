import Link from "next/link";

export function Navbar() {
  return (
    <header className="sticky top-0 z-40 border-b border-[var(--border)] bg-[#1b1238]/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3.5">
        <Link href="/" className="flex items-center gap-2.5 text-lg font-bold tracking-tight text-[var(--text)]">
          <img
            src="/icon.png"
            alt="Linkori"
            className="h-9 w-9 rounded-xl object-contain"
          />
          <span>Linkori</span>
        </Link>

        <nav className="hidden items-center gap-7 text-sm text-[var(--text-muted)] md:flex">
          <Link href="/#features" className="transition hover:text-[var(--text)]">
            Преимущества
          </Link>
          <Link href="/#pricing" className="transition hover:text-[var(--text)]">
            Тарифы
          </Link>
          <Link href="/#faq" className="transition hover:text-[var(--text)]">
            Вопросы
          </Link>
          <Link href="/terms" className="transition hover:text-[var(--text)]">
            Соглашение
          </Link>
          <Link href="/privacy" className="transition hover:text-[var(--text)]">
            Конфиденциальность
          </Link>
        </nav>

        <div className="flex items-center gap-2.5">
          <a
            href="https://t.me/Linkorisupport"
            target="_blank"
            rel="noreferrer"
            className="hidden rounded-[12px] border border-[var(--border)] bg-[var(--surface)] px-3.5 py-2 text-xs font-medium text-[var(--text)] transition hover:bg-[var(--surface-hover)] sm:inline-block"
          >
            Поддержка
          </a>
          <a
            href="https://t.me/linkoribot"
            target="_blank"
            rel="noreferrer"
            className="rounded-[12px] border border-[var(--accent)]/35 bg-[var(--accent-soft)] px-3.5 py-2 text-xs font-semibold text-[var(--accent)] transition hover:bg-[var(--accent)]/20"
          >
            Открыть бота
          </a>
          <Link
            href="/#pricing"
            className="rounded-[12px] bg-[var(--accent)] px-4 py-2 text-xs font-bold text-[#150d2e] transition hover:bg-[var(--accent-2)]"
          >
            Тарифы
          </Link>
        </div>
      </div>
    </header>
  );
}
