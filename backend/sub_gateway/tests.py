import base64
import json
import uuid
from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from billing.models import Plan, Subscription
from nodes.models import NodeInbound, VpnNode
from probes.models import WorkingPublicConfig

from .uri_builder import (
    BURST_PING_INTERVAL,
    BURST_PING_SAMPLING,
    BURST_PING_TIMEOUT,
    LEAST_LOAD_MAX_RTT,
    LEAST_LOAD_TOLERANCE,
    MAX_OUTBOUNDS_PER_CONFIG,
    MAX_XRAY_CONFIGS,
)


@override_settings(ALLOWED_HOSTS=["sub.linkori.org", "linkori.org", "testserver"])
class SubGatewayTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="tg_1001",
            telegram_id=1001,
            telegram_username="testuser",
        )
        self.plan = Plan.objects.create(
            code="month_1",
            name="1 месяц",
            duration_days=30,
            price_kopeks=29900,
            traffic_limit_gb=0,
            max_devices=2,
        )
        self.sub = Subscription.objects.create(
            user=self.user,
            plan=self.plan,
            max_devices=2,
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.node = VpnNode.objects.create(
            name="Finland",
            country_code="FI",
            flag_emoji="🇫🇮",
            ip_address="198.51.100.10",
            panel_url="https://198.51.100.10:2053",
            panel_api_token="test-token",
            is_enabled=True,
            priority=10,
        )
        self.inbound_online = NodeInbound.objects.create(
            node=self.node,
            xui_inbound_id=1,
            protocol=NodeInbound.Protocol.HYSTERIA2,
            display_name="[Pr 👑] Finland (игровой 🎮)",
            connect_host="198.51.100.10",
            connect_port=8443,
            extra_params={"pin_sha256": "ab:cd:ef", "alpn": "h3"},
            is_enabled=True,
            health_status=NodeInbound.HealthStatus.ONLINE,
        )
        self.inbound_offline = NodeInbound.objects.create(
            node=self.node,
            xui_inbound_id=2,
            protocol=NodeInbound.Protocol.VLESS_REALITY,
            display_name="[Pr 👑] Finland",
            connect_host="198.51.100.10",
            connect_port=443,
            is_enabled=True,
            health_status=NodeInbound.HealthStatus.OFFLINE,
        )

    def test_browser_receives_html_stub_without_configs(self):
        res = self.client.get(
            f"/{self.sub.sub_token}",
            HTTP_HOST="sub.linkori.org",
            HTTP_ACCEPT="text/html,application/xhtml+xml",
            HTTP_SEC_FETCH_DEST="document",
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res["Content-Type"])
        self.assertNotIn(str(self.sub.xray_uuid), res.content.decode())

    def test_missing_hwid_returns_not_supported_header(self):
        res = self.client.get(
            f"/{self.sub.sub_token}",
            HTTP_HOST="sub.linkori.org",
            HTTP_ACCEPT="*/*",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res["x-hwid-active"], "true")
        self.assertEqual(res["x-hwid-not-supported"], "true")

    def test_device_limit_and_hysteria2_pin_sha256(self):
        res1 = self.client.get(
            f"/{self.sub.sub_token}",
            HTTP_HOST="sub.linkori.org",
            HTTP_X_HWID="android-device-001",
            HTTP_ACCEPT="*/*",
        )
        self.assertEqual(res1.status_code, 200)
        decoded = base64.b64decode(res1.content).decode("utf-8")
        self.assertIn("hysteria2://", decoded)
        self.assertIn("pinSHA256=ab%3Acd%3Aef", decoded)
        # Hysteria2 отдается на своем порту, а не на 443: строки VLESS Reality на 443
        # в списке есть отдельными серверами, и это нормально.
        for line in decoded.splitlines():
            if line.startswith("hysteria2://"):
                self.assertNotIn(":443?", line)

        res2 = self.client.get(
            f"/{self.sub.sub_token}",
            HTTP_HOST="sub.linkori.org",
            HTTP_X_HWID="ios-device-002",
            HTTP_ACCEPT="*/*",
        )
        self.assertEqual(res2.status_code, 200)

        res3 = self.client.get(
            f"/{self.sub.sub_token}",
            HTTP_HOST="sub.linkori.org",
            HTTP_X_HWID="windows-device-003",
            HTTP_ACCEPT="*/*",
        )
        self.assertEqual(res3.status_code, 403)
        self.assertEqual(res3["x-hwid-active"], "true")
        self.assertEqual(res3["x-hwid-max-devices-reached"], "true")
        self.assertEqual(res3["x-hwid-limit"], "true")


@override_settings(ALLOWED_HOSTS=["sub.linkori.org", "linkori.org", "testserver"])
class HappXrayPayloadTests(TestCase):
    """Happ/INCY получают Xray JSON: проверяем настройки balancer и бюджет outbound'ов."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="tg_2002", telegram_id=2002)
        self.plan = Plan.objects.create(
            code="month_2",
            name="1 месяц",
            duration_days=30,
            price_kopeks=29900,
            traffic_limit_gb=0,
            max_devices=5,
        )
        self.sub = Subscription.objects.create(
            user=self.user,
            plan=self.plan,
            max_devices=5,
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.nl_node = VpnNode.objects.create(
            name="Netherlands",
            country_code="NL",
            flag_emoji="🇳🇱",
            ip_address="198.51.100.20",
            panel_url="https://198.51.100.20:2053",
            panel_api_token="token",
            priority=10,
            probe_xray_uuid=uuid.uuid4(),
        )
        self.de_node = VpnNode.objects.create(
            name="Germany",
            country_code="DE",
            flag_emoji="🇩🇪",
            ip_address="198.51.100.30",
            panel_url="https://198.51.100.30:2053",
            panel_api_token="token",
            priority=20,
            probe_xray_uuid=uuid.uuid4(),
        )

        self.nl_fast = NodeInbound.objects.create(
            node=self.nl_node,
            xui_inbound_id=1,
            protocol=NodeInbound.Protocol.HYSTERIA2,
            display_name="[Pr 👑] Netherlands",
            connect_host="198.51.100.20",
            connect_port=8443,
            extra_params={"sni": "nl.example.com", "alpn": "h3"},
            is_enabled=True,
            health_status=NodeInbound.HealthStatus.ONLINE,
            last_latency_ms=40,
        )
        self.nl_slow = NodeInbound.objects.create(
            node=self.nl_node,
            xui_inbound_id=2,
            protocol=NodeInbound.Protocol.VLESS_REALITY,
            display_name="[Pr 👑] Netherlands",
            connect_host="198.51.100.20",
            connect_port=443,
            extra_params={"pbk": "pbk", "sni": "nl.example.com", "sid": "ab", "type": "tcp"},
            is_enabled=True,
            health_status=NodeInbound.HealthStatus.ONLINE,
            last_latency_ms=90,
        )
        self.de_offline = NodeInbound.objects.create(
            node=self.de_node,
            xui_inbound_id=3,
            protocol=NodeInbound.Protocol.VLESS_REALITY,
            display_name="[Pr 👑] Germany",
            connect_host="198.51.100.30",
            connect_port=443,
            extra_params={"pbk": "pbk", "sni": "de.example.com", "sid": "cd", "type": "tcp"},
            is_enabled=True,
            health_status=NodeInbound.HealthStatus.OFFLINE,
            last_latency_ms=None,
        )
        # Страна низкого приоритета: ее профиль обязан остаться даже при жестком бюджете.
        jp_node = VpnNode.objects.create(
            name="Japan",
            country_code="JP",
            flag_emoji="🇯🇵",
            ip_address="198.51.100.50",
            panel_url="https://198.51.100.50:2053",
            panel_api_token="token",
            priority=50,
            probe_xray_uuid=uuid.uuid4(),
        )
        self.jp_inbound = NodeInbound.objects.create(
            node=jp_node,
            xui_inbound_id=4,
            protocol=NodeInbound.Protocol.VLESS_REALITY,
            display_name="[Pr 👑] Japan",
            connect_host="198.51.100.50",
            connect_port=443,
            extra_params={"pbk": "pbk", "sni": "jp.example.com", "sid": "ef", "type": "tcp"},
            is_enabled=True,
            health_status=NodeInbound.HealthStatus.UNKNOWN,
            last_latency_ms=None,
        )

        for idx in range(3):
            WorkingPublicConfig.objects.create(
                source="lte",
                origin_source="",
                country_code="NL",
                uri=(
                    "vless://11111111-1111-1111-1111-111111111111@203.0.113."
                    f"{idx + 5}:443?type=tcp&security=tls&sni=pub.example.com#NL public {idx}"
                ),
                latency_ms=60 + idx,
            )

    def _payload(self, url=None, ua="Happ/3.9.0", hwid="happ-device-001"):
        response = self.client.get(
            url or f"/{self.sub.sub_token}",
            HTTP_HOST="sub.linkori.org",
            HTTP_ACCEPT="*/*",
            HTTP_X_HWID=hwid,
            HTTP_USER_AGENT=ua,
        )
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content.decode("utf-8"))

    @staticmethod
    def _proxy_outbounds(config):
        return [o for o in config["outbounds"] if o.get("protocol") != "freedom"]

    def test_balancer_ping_is_tuned_and_not_cutting_live_servers(self):
        configs = self._payload()
        self.assertTrue(configs)

        auto = configs[0]
        self.assertEqual(auto["remarks"], "⭐ Автовыбор")
        ping = auto["burstObservatory"]["pingConfig"]
        self.assertEqual(ping["interval"], BURST_PING_INTERVAL)
        self.assertEqual(ping["sampling"], BURST_PING_SAMPLING)
        self.assertEqual(ping["timeout"], BURST_PING_TIMEOUT)

        settings = auto["routing"]["balancers"][0]["strategy"]["settings"]
        self.assertEqual(settings["expected"], 1)
        self.assertEqual(settings["maxRTT"], LEAST_LOAD_MAX_RTT)
        self.assertEqual(settings["tolerance"], LEAST_LOAD_TOLERANCE)

    def test_fallback_tag_points_to_live_fastest_server(self):
        auto = self._payload()[0]
        fallback_tag = auto["routing"]["balancers"][0]["fallbackTag"]
        by_tag = {o["tag"]: o for o in auto["outbounds"]}
        self.assertIn(fallback_tag, by_tag)

        # Первым идет живой сервер с минимальной задержкой (NL hysteria2, 40 мс).
        fallback = by_tag[fallback_tag]
        settings = fallback["settings"]
        if "vnext" in settings:
            server = settings["vnext"][0]
        else:
            server = {"address": settings["address"], "port": settings["port"]}
        self.assertEqual(server["address"], "198.51.100.20")
        self.assertEqual(server["port"], 8443)

    def test_every_config_fits_outbound_budget_and_has_unique_tags(self):
        for config in self._payload():
            proxies = self._proxy_outbounds(config)
            self.assertLessEqual(len(proxies), MAX_OUTBOUNDS_PER_CONFIG)
            tags = [o["tag"] for o in proxies]
            self.assertEqual(len(tags), len(set(tags)), config["remarks"])

    def test_all_enabled_inbounds_stay_in_subscription(self):
        configs = self._payload()
        addresses = set()
        for config in configs:
            for outbound in self._proxy_outbounds(config):
                for server in outbound.get("settings", {}).get("vnext", []):
                    addresses.add(server["address"])
                if "address" in outbound.get("settings", {}):
                    addresses.add(outbound["settings"]["address"])
        for inbound in (self.nl_fast, self.nl_slow, self.de_offline, self.jp_inbound):
            self.assertIn(inbound.connect_host, addresses)

    def test_profile_budget_keeps_our_countries_first(self):
        extra_countries = [
            "PL", "EE", "LT", "FR", "GB", "CH", "AT", "CZ", "NO", "DK",
            "ES", "IT", "IE", "BE", "LU", "RO", "MD", "BG", "HU", "SK",
        ]
        for idx, cc in enumerate(extra_countries):
            WorkingPublicConfig.objects.create(
                source="lte",
                origin_source="",
                country_code=cc,
                uri=(
                    f"vless://22222222-2222-2222-2222-{idx:012d}@203.0.113."
                    f"{(idx % 200) + 1}:443?type=tcp&security=tls&sni=pub.example.com#{cc} public"
                ),
                latency_ms=80 + idx,
            )

        configs = self._payload()
        remarks = [c["remarks"] for c in configs]

        self.assertLessEqual(len(configs), MAX_XRAY_CONFIGS)
        self.assertEqual(remarks[0], "⭐ Автовыбор")
        # Свои страны попадают в бюджет первыми, даже если страна низкого приоритета.
        for expected in ("🇳🇱 Нидерланды", "🇩🇪 Германия", "🇯🇵 Япония"):
            self.assertIn(expected, remarks)

    def test_single_outbound_country_config_has_no_balancer(self):
        configs = self._payload()
        germany = next(c for c in configs if c["remarks"] == "🇩🇪 Германия")
        self.assertNotIn("burstObservatory", germany)
        self.assertNotIn("balancers", germany["routing"])
        self.assertEqual(germany["routing"]["rules"][0]["outboundTag"], "prem-0")


@override_settings(
    ALLOWED_HOSTS=["sub.linkori.org", "linkori.org", "testserver"],
    SUB_ADMIN_TOKEN="admin-test-token",
)
class AdminTestSubscriptionTests(TestCase):
    """Админская подписка: все серверы плоским Xray JSON, без balancer и observatory."""

    def setUp(self):
        self.client = Client()
        self.node = VpnNode.objects.create(
            name="Netherlands",
            country_code="NL",
            flag_emoji="🇳🇱",
            ip_address="198.51.100.40",
            panel_url="https://198.51.100.40:2053",
            panel_api_token="token",
            priority=10,
            probe_xray_uuid=uuid.uuid4(),
        )
        self.hy2 = NodeInbound.objects.create(
            node=self.node,
            xui_inbound_id=1,
            protocol=NodeInbound.Protocol.HYSTERIA2,
            display_name="[Pr 👑] Netherlands (игровой)",
            connect_host="198.51.100.40",
            connect_port=8443,
            extra_params={"sni": "nl.example.com", "alpn": "h3"},
            is_enabled=True,
        )
        self.reality = NodeInbound.objects.create(
            node=self.node,
            xui_inbound_id=2,
            protocol=NodeInbound.Protocol.VLESS_REALITY,
            display_name="[Pr 👑] Netherlands",
            connect_host="198.51.100.40",
            connect_port=443,
            extra_params={"pbk": "pbk", "sni": "nl.example.com", "sid": "ab", "type": "tcp"},
            is_enabled=True,
        )

    def _get(self, url="/admin-test-token", ua="Happ/3.9.0", extra_headers=None):
        return self.client.get(
            url,
            HTTP_HOST="sub.linkori.org",
            HTTP_ACCEPT="*/*",
            HTTP_USER_AGENT=ua,
            **(extra_headers or {"HTTP_X_HWID": "admin-device-001"}),
        )

    def test_flat_payload_without_balancer_uses_probe_uuid(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response["Content-Type"])

        configs = json.loads(response.content.decode("utf-8"))
        self.assertEqual(len(configs), 2)
        for config in configs:
            self.assertNotIn("burstObservatory", config)
            self.assertNotIn("observatory", config)
            self.assertNotIn("balancers", config["routing"])
            self.assertEqual(config["routing"]["rules"][0]["outboundTag"], "proxy")
            self.assertIn("198.51.100.40", config["remarks"])

        by_port = {c["outbounds"][0]["settings"].get("port") or
                   c["outbounds"][0]["settings"]["vnext"][0]["port"]: c for c in configs}
        self.assertEqual(
            by_port[8443]["outbounds"][0]["streamSettings"]["hysteriaSettings"]["auth"],
            str(self.node.probe_xray_uuid),
        )
        self.assertEqual(
            by_port[443]["outbounds"][0]["settings"]["vnext"][0]["users"][0]["id"],
            str(self.node.probe_xray_uuid),
        )

    def test_admin_subscription_ignores_hwid_and_subscription_state(self):
        self.assertEqual(Subscription.objects.count(), 0)
        self.assertEqual(self._get(extra_headers={}).status_code, 200)

    def test_admin_subscription_uri_format(self):
        response = self._get(url="/admin-test-token?format=uri", ua="curl/8.5")
        self.assertEqual(response.status_code, 200)
        decoded = base64.b64decode(response.content).decode("utf-8")
        self.assertIn(f"hysteria2://{self.node.probe_xray_uuid}@198.51.100.40:8443", decoded)
        self.assertIn(f"vless://{self.node.probe_xray_uuid}@198.51.100.40:443", decoded)

    def test_browser_gets_stub_without_configs(self):
        response = self.client.get(
            "/admin-test-token",
            HTTP_HOST="sub.linkori.org",
            HTTP_ACCEPT="text/html,application/xhtml+xml",
            HTTP_SEC_FETCH_DEST="document",
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("text/html", response["Content-Type"])
        self.assertNotIn(str(self.node.probe_xray_uuid), body)

    def test_unknown_token_still_404(self):
        self.assertEqual(self._get(url="/not-the-admin-token").status_code, 404)
