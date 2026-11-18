"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

interface MeResponse {
  user: {
    id: number;
    telegram_id: number;
    telegram_username: string;
    referral_code: string;
    balance_kopeks: number;
    is_legal_accepted: boolean;
  };
  referrals_count: number;
  devices_count: number;
  active_subscription: {
    id: string;
    sub_token: string;
    status: string;
    plan_name: string;
    max_devices: number;
    traffic_used_bytes: number;
    traffic_limit_bytes: number | null;
    expires_at: string;
  } | null;
}

function getCookie(name: string): string {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : "";
}

function formatRub(kopeks: number): string {
  const rub = kopeks / 100;
  return Number.isInteger(rub) ? `${rub} ₽` : `${rub.toFixed(2)} ₽`;
}

export default function CabinetPage() {
  const router = useRouter();
  const [data, setData] = useState<MeResponse | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetch("/api/accounts/me/", { credentials: "include" })
      .then(async (res) => {
        if (!res.ok) {
          router.replace("/login");
          return;
        }
        setData(await res.json());
      })
      .catch(() => router.replace("/login"));
  }, [router]);

  async function handleLogout() {
    await fetch("/api/accounts/logout/", {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRFToken": getCookie("csrftoken") },
    });
    window.dispatchEvent(new Event("linkori-auth-changed"));
    router.replace("/");
  }

  function copySubUrl(url: string) {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  if (!data) {
    return (
      <section className="mx-auto max-w-4xl px-4 py-20 text-center text-sm text-[#9e96cc]">
        Загрузка профиля...
      </section>
    );
  }

  const sub = data.active_subscription;
  const subUrl = sub ? `https://sub.linkori.org/${sub.sub_token}` : null;

  return (
    <section className="mx-auto max-w-4xl px-4 py-12">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-[#efeaff]">Личный кабинет</h1>
          <p className="mt-1 text-sm text-[#9e96cc]">
            Аккаунт:{" "}
            <span className="font-semibold text-[#7ae9eb]">
              @{data.user.telegram_username}
            </span>{" "}
            (ID: {data.user.telegram_id})
          </p>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="rounded-xl border border-[#8b5cf6]/35 bg-[#160e31] px-4 py-2 text-xs font-semibold text-[#d8d0ff] transition hover:border-[#ec5f49]/50 hover:text-[#ff9a8a]"
        >
          Выйти
        </button>
      </div>

      <div className="mt-8 grid gap-5 sm:grid-cols-3">
        <div className="rounded-[22px] border border-[#8b5cf6]/25 bg-[#160e31] p-5">
          <div className="text-xs text-[#9e96cc]">Баланс</div>
          <div className="mt-2 text-2xl font-bold text-[#7ae9eb]">
            {formatRub(data.user.balance_kopeks)}
          </div>
        </div>
        <div className="rounded-[22px] border border-[#8b5cf6]/25 bg-[#160e31] p-5">
          <div className="text-xs text-[#9e96cc]">Приглашено друзей</div>
          <div className="mt-2 text-2xl font-bold text-[#efeaff]">{data.referrals_count}</div>
        </div>
        <div className="rounded-[22px] border border-[#8b5cf6]/25 bg-[#160e31] p-5">
          <div className="text-xs text-[#9e96cc]">Реферальный код</div>
          <div className="mt-2 font-mono text-lg font-bold text-[#fbcfe8]">
            {data.user.referral_code}
          </div>
        </div>
      </div>

      <div className="mt-6 rounded-[22px] border border-[#7ae9eb]/35 bg-[#160e31] p-6 shadow-[0_20px_50px_-15px_rgba(6,3,20,0.9)]">
        <h2 className="text-xl font-bold text-[#efeaff]">Статус доступа</h2>

        {sub && subUrl ? (
          <div className="mt-4 space-y-4">
            <div className="flex flex-wrap gap-6 text-sm text-[#d8d0ff]">
              <div>
                Тариф: <span className="font-semibold text-[#7ae9eb]">{sub.plan_name}</span>
              </div>
              <div>
                Действует до:{" "}
                <span className="font-semibold text-[#efeaff]">
                  {new Date(sub.expires_at).toLocaleDateString("ru-RU")}
                </span>
              </div>
              <div>
                Устройства:{" "}
                <span className="font-semibold text-[#efeaff]">
                  {data.devices_count} / {sub.max_devices}
                </span>
              </div>
            </div>

            <div className="rounded-[14px] border border-[#8b5cf6]/30 bg-[#0d0720] p-3.5">
              <div className="text-xs text-[#9e96cc]">Ссылка подключения:</div>
              <div className="mt-1.5 flex flex-wrap items-center justify-between gap-3">
                <code className="break-all text-xs text-[#7ae9eb]">{subUrl}</code>
                <button
                  type="button"
                  onClick={() => copySubUrl(subUrl)}
                  className="rounded-lg bg-[#7ae9eb] px-3 py-1.5 text-xs font-bold text-[#120b28] transition hover:bg-[#9ef1f3]"
                >
                  {copied ? "Скопировано" : "Копировать"}
                </button>
              </div>
            </div>

            <div className="flex flex-wrap gap-2.5">
              <a
                href={`${subUrl}/open/happ`}
                className="rounded-xl border border-[#7ae9eb]/35 bg-[#7ae9eb]/10 px-4 py-2 text-xs font-semibold text-[#7ae9eb] hover:bg-[#7ae9eb]/20"
              >
                Открыть в Happ
              </a>
              <a
                href={`${subUrl}/open/v2raytun`}
                className="rounded-xl border border-[#7ae9eb]/35 bg-[#7ae9eb]/10 px-4 py-2 text-xs font-semibold text-[#7ae9eb] hover:bg-[#7ae9eb]/20"
              >
                Открыть в v2RayTun
              </a>
              <a
                href={`${subUrl}/open/hiddify`}
                className="rounded-xl border border-[#7ae9eb]/35 bg-[#7ae9eb]/10 px-4 py-2 text-xs font-semibold text-[#7ae9eb] hover:bg-[#7ae9eb]/20"
              >
                Открыть в Hiddify
              </a>
            </div>
          </div>
        ) : (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-4">
            <p className="text-sm text-[#9e96cc]">Активной подписки пока нет.</p>
            <Link
              href="/#pricing"
              className="rounded-[14px] bg-[#7ae9eb] px-5 py-2.5 text-sm font-bold text-[#120b28] transition hover:bg-[#9ef1f3]"
            >
              Выбрать тариф
            </Link>
          </div>
        )}
      </div>
    </section>
  );
}