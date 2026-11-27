"""Production launch gates may never be green with draft legal pages."""
import importlib.util
import pathlib
import tempfile
import unittest

HERE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("compass_preflight",HERE/"preflight.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.site=pathlib.Path(self.temp.name)
        (self.site/"index.html").write_text(
            '<meta name="robots" content="index,follow">Лизинг Компас '
            '<a href="/apply/">Отправить</a><a href="/callback/">Звонок</a>',
            encoding="utf-8"
        )
        for name in ("privacy.html","consent.html"):
            (self.site/name).write_text(
                "Утверждённая политика обработки данных v1",encoding="utf-8")
        self.config={
            "COMPASS_OPERATOR_NAME":"ИП Гасанов Тариэль Алиевич",
            "COMPASS_OPERATOR_INN":"231207234403",
            "COMPASS_PRODUCTION":"1",
            "COMPASS_POLICY_APPROVED":"yes",
            "COMPASS_RKN_SCOPE_CONFIRMED":"yes",
            "COMPASS_RESTORE_TEST_PASSED":"yes",
            "COMPASS_FERNET_KEYS":"example-placeholder-format-do-not-use-tests",
            "DATABASE_URL":"postgresql://compass:synthetic@db:5432/leasingcompass",
            "DJANGO_SECRET_KEY":"testonly-"+"b"*80,
            "COMPASS_THROTTLE_SECRET":"testonly-"+"c"*80,
            "COMPASS_CONSENT_VERSION":"consent-v1",
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_draft_legal_pages_are_not_launch_ready(self):
        (self.site/"privacy.html").write_text(
            "Проект для согласования с оператором. "
            "Адрес оператора для юридически значимых обращений будет уточнён",
            encoding="utf-8"
        )
        report=module.inspect_settings(self.config,self.site,"leasingcompass.ru")
        self.assertFalse(report["no_legal_drafts"])
        self.assertFalse(all(report.values()))

    def test_public_exposure_of_private_file_blocks_launch(self):
        (self.site/"broker-preview.html").write_text("should not be public")
        report=module.inspect_settings(self.config,self.site,"leasingcompass.ru")
        self.assertFalse(report["site_no_private"])

    def test_missing_rkn_backup_or_policy_flags_are_blockers(self):
        for key in ("COMPASS_RKN_SCOPE_CONFIRMED",
                    "COMPASS_RESTORE_TEST_PASSED","COMPASS_POLICY_APPROVED"):
            config={**self.config,key:"no"}
            self.assertFalse(all(module.inspect_settings(
                config,self.site,"leasingcompass.ru").values()),key)

    def test_nonexistent_server_config_fails_without_network_probe(self):
        report=module.inspect_settings({},self.site,"leasingcompass.ru")
        self.assertFalse(report["operator_identity"])
        self.assertFalse(report["database_configured"])
        self.assertNotIn("public_https_home",report)

    def test_legally_approved_synthetic_static_case_passes_offline_checks(self):
        report=module.inspect_settings(self.config,self.site,"leasingcompass.ru")
        self.assertTrue(all(report.values()),report)

if __name__=="__main__":
    unittest.main()
