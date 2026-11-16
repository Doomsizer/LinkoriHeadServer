import type { Metadata } from "next";
import { ConsentGate } from "@/components/ConsentGate";
import { Footer } from "@/components/Footer";
import { Navbar } from "@/components/Navbar";
import "./globals.css";

export const metadata: Metadata = {
  title: "Linkori — Приватный прокси-сервис для защищенного подключения",
  description:
    "Высокоскоростные прокси-узлы для шифрования соединений, защиты в публичных Wi-Fi сетях и стабильной маршрутизации.",
  icons: {
    icon: "/icon.png",
    shortcut: "/icon.png",
    apple: "/icon.png",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body className="flex min-h-screen flex-col antialiased">
        <Navbar />
        <main className="flex-1">{children}</main>
        <Footer />
        <ConsentGate />
      </body>
    </html>
  );
}