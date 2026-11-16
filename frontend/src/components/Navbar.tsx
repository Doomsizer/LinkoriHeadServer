import Link from "next/link";

export function Navbar() {
  return (
    <header className="sticky top-0 z-40 border-b border-[#8b5cf6]/20 bg-[#120b28]/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3.5">
        <Link
          href="/"
          className="flex items-center gap-2 text-lg font-extrabold tracking-tight text-[#efeaff]"
        >
          <span className="h-2 w-2 rounded-full bg-[#7ae9eb] shadow-[0_0_12px_#7ae9eb]" />
          <span>Linkori</span>
        </Link>

        <nav className="hidden items-center gap-7 text-sm text-[#9e96cc] md:flex">
          <Link href="/#features" className="transition hover:text-[#7ae9eb]">
            Преимущества
          </Link>
          <Link href="/#pricing" className="transition hover:text-[#7ae9eb]">
            Тарифы
          </Link>
          <Link href="/#faq" className="transition hover:text-[#7ae9eb]">
            Вопросы
          </Link>
          <Link href="/terms" className="transition hover:text-[#7ae9eb]">
            Соглашение
          </Link>
          <Link href="/privacy" className="transition hover:text-[#7ae9eb]">
            Конфиденциальность
          </Link>
        </nav>

        <div className="flex items-center gap-2.5">
          <a
            href="https://t.me/linkoribot"
            target="_blank"
            rel="noreferrer"
            className="hidden rounded-xl border border-[#7ae9eb]/35 bg-[#7ae9eb]/10 px-3.5 py-2 text-xs font-semibold text-[#7ae9eb] transition hover:bg-[#7ae9eb]/20 hover:shadow-[0_0_20px_-6px_rgba(122,233,235,0.5)] sm:inline-block"
          >
            Открыть бота
          </a>
          <Link
            href="/login"
            className="rounded-xl border border-[#8b5cf6]/35 bg-[#1b1238]/90 px-3.5 py-2 text-xs font-semibold text-[#efeaff] transition hover:border-[#f472b6]/50 hover:text-[#fbcfe8]"
          >
            Войти
          </Link>
          <Link
            href="/#pricing"
            className="rounded-xl bg-[#7ae9eb] px-4 py-2 text-xs font-bold text-[#120b28] shadow-[0_0_22px_-6px_rgba(122,233,235,0.6)] transition hover:bg-[#9ef1f3]"
          >
            Тарифы
          </Link>
        </div>
      </div>
    </header>
  );
}