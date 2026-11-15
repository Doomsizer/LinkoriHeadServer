import Link from "next/link";

export function Navbar() {
  return (
    <header className="sticky top-0 z-40 border-b border-border/80 bg-bg/85 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        <Link href="/" className="flex items-center gap-2.5 text-lg font-bold tracking-tight text-white">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-sm font-extrabold text-white">
            L
          </span>
          <span>Linkori</span>
        </Link>

        <nav className="hidden items-center gap-7 text-sm text-slate-300 md:flex">
          <Link href="/#features" className="transition hover:text-white">
            Преимущества
          </Link>
          <Link href="/#pricing" className="transition hover:text-white">
            Тарифы
          </Link>
          <Link href="/#faq" className="transition hover:text-white">
            Вопросы
          </Link>
          <Link href="/terms" className="transition hover:text-white">
            Соглашение
          </Link>
          <Link href="/privacy" className="transition hover:text-white">
            Конфиденциальность
          </Link>
        </nav>

        <div className="flex items-center gap-3">
          <a
            href="https://t.me/linkori_support"
            target="_blank"
            rel="noreferrer"
            className="rounded-lg border border-border px-3.5 py-2 text-xs font-medium text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            Поддержка
          </a>
          <Link
            href="/#pricing"
            className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-blue-500"
          >
            Выбрать тариф
          </Link>
        </div>
      </div>
    </header>
  );
}
