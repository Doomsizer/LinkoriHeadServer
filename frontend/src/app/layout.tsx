import type { Metadata } from "next";
import { Footer } from "@/components/Footer";
import { Navbar } from "@/components/Navbar";
import "./globals.css";

export const metadata: Metadata = {
  title: "Linkori — Приватный прокси-сервис для защищенного подключения",
  description:
    "Высокоскоростные приватные прокси-узлы для шифрования соединений, защиты в публичных Wi-Fi сетях и стабильной маршрутизации.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body className="flex min-h-screen flex-col bg-bg text-slate-100 antialiased">
        <Navbar />
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
