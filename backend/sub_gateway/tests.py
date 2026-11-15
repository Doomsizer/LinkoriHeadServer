import base64
from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from billing.models import Plan, Subscription
from nodes.models import NodeInbound, VpnNode


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
        self.assertNotIn(":443?", decoded)

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