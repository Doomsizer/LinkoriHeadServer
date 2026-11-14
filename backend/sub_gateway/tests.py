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
            name="NL-01",
            country_code="NL",
            flag_emoji="🇳🇱",
            ip_address="198.51.100.10",
            panel_url="https://198.51.100.10:2053",
            panel_username="admin",
            panel_password="secret",
            is_enabled=True,
            priority=10,
        )
        self.inbound_online = NodeInbound.objects.create(
            node=self.node,
            xui_inbound_id=1,
            protocol=NodeInbound.Protocol.SS,
            display_name="NL Shadowsocks",
            connect_host="nl1.linkori.org",
            connect_port=8388,
            extra_params={
                "method": "2022-blake3-aes-256-gcm",
                "server_psk": "c2VydmVyX3Bza18zMl9ieXRlc19rZXlfMTIzNDU2Nzg=",
            },
            is_enabled=True,
            health_status=NodeInbound.HealthStatus.ONLINE,
        )
        self.inbound_offline = NodeInbound.objects.create(
            node=self.node,
            xui_inbound_id=2,
            protocol=NodeInbound.Protocol.VLESS_REALITY,
            display_name="NL Offline",
            connect_host="nl1.linkori.org",
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

    def test_device_limit_and_ios_sip002_vs_sip022(self):
        # 1-е устройство (Android -> SIP022)
        res_android = self.client.get(
            f"/{self.sub.sub_token}",
            HTTP_HOST="sub.linkori.org",
            HTTP_X_HWID="android-device-001",
            HTTP_X_DEVICE_OS="Android",
            HTTP_ACCEPT="*/*",
        )
        self.assertEqual(res_android.status_code, 200)
        decoded_android = base64.b64decode(res_android.content).decode("utf-8")
        self.assertIn("ss://2022-blake3-aes-256-gcm:", decoded_android)
        self.assertNotIn("NL Offline", decoded_android)

        # 2-е устройство (iOS -> SIP002 base64)
        res_ios = self.client.get(
            f"/{self.sub.sub_token}",
            HTTP_HOST="sub.linkori.org",
            HTTP_X_HWID="ios-device-002",
            HTTP_X_DEVICE_OS="iOS",
            HTTP_USER_AGENT="Shadowrocket/2.2",
            HTTP_ACCEPT="*/*",
        )
        self.assertEqual(res_ios.status_code, 200)
        decoded_ios = base64.b64decode(res_ios.content).decode("utf-8")
        self.assertTrue(decoded_ios.startswith("ss://"))
        self.assertNotIn("2022-blake3-aes-256-gcm:", decoded_ios)

        # 3-е устройство -> превышение лимита (max_devices=2)
        res_third = self.client.get(
            f"/{self.sub.sub_token}",
            HTTP_HOST="sub.linkori.org",
            HTTP_X_HWID="windows-device-003",
            HTTP_ACCEPT="*/*",
        )
        self.assertEqual(res_third.status_code, 403)
        self.assertEqual(res_third["x-hwid-active"], "true")
        self.assertEqual(res_third["x-hwid-max-devices-reached"], "true")
        self.assertEqual(res_third["x-hwid-limit"], "true")
