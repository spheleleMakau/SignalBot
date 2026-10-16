import unittest

from config import Settings, validate_deployment_security


class DeploymentSecurityTests(unittest.TestCase):
    def test_loopback_development_bind_may_run_without_dashboard_auth(self):
        for host in ("127.0.0.1", "::1", "localhost"):
            with self.subTest(host=host):
                validate_deployment_security(
                    Settings(host=host, dashboard_auth_required=False)
                )

    def test_non_loopback_bind_requires_dashboard_authentication(self):
        for host in ("0.0.0.0", "::", "192.0.2.1"):
            with self.subTest(host=host):
                with self.assertRaisesRegex(RuntimeError, "DASHBOARD_AUTH_REQUIRED"):
                    validate_deployment_security(
                        Settings(host=host, dashboard_auth_required=False)
                    )

    def test_authentication_requires_both_credentials(self):
        with self.assertRaisesRegex(RuntimeError, "DASHBOARD_USERNAME"):
            validate_deployment_security(
                Settings(
                    host="0.0.0.0",
                    dashboard_auth_required=True,
                    dashboard_username="",
                    dashboard_password="",
                )
            )

    def test_authentication_allows_configured_external_bind(self):
        validate_deployment_security(
            Settings(
                host="0.0.0.0",
                dashboard_auth_required=True,
                dashboard_username="operator",
                dashboard_password="secret",
            )
        )


if __name__ == "__main__":
    unittest.main()
