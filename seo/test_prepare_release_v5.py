"""Release build smoke checks; do not publish or contact external search engines."""
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from xml.etree import ElementTree

ROOT=pathlib.Path(__file__).resolve().parents[1]
BUILDER=ROOT/"seo"/"prepare_release.py"

class ReleaseV5(unittest.TestCase):
    def test_guard_prevents_approval_free_indexable_build(self):
        with tempfile.TemporaryDirectory() as root:
            target=pathlib.Path(root)/"build"
            r=subprocess.run([sys.executable,str(BUILDER),"--output",str(target)],
                             capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)
            self.assertFalse(target.exists())

    def test_build_is_v5_and_never_contains_private_backend_pages(self):
        with tempfile.TemporaryDirectory() as root:
            target=pathlib.Path(root)/"build"
            r=subprocess.run([
                sys.executable,str(BUILDER),"--output",str(target),
                "--confirm-ready","--indexnow-key","approved-test-key-2026"
            ],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            home=(target/"index.html").read_text(encoding="utf-8")
            self.assertIn("Лизинг Компас",home)
            self.assertIn('href="/apply/"',home)
            self.assertEqual(home.count('data-compass-intake="production"'),4)
            self.assertNotIn('onsubmit="submitForm(',home)
            # Old disabled form inputs must never look like live PII submission.
            self.assertNotIn('<input type="checkbox" id="pdConsent',home)
            self.assertIn('href="/callback/"',home)
            self.assertIn('href="/apply/"',home)
            self.assertNotIn('<input type="tel" name="phone"',home)
            self.assertIn('id="request" data-compass-intake="production"',home)
            self.assertIn('<meta name="robots" content="index,follow">',home)
            self.assertIn('rel="canonical" href="https://leasingcompass.ru/"',home)
            self.assertNotIn("talysrus90-cmd.github.io",home)
            self.assertNotIn('content="noindex,nofollow"',home)
            shadow=(target/"variant-5.html").read_text(encoding="utf-8")
            self.assertIn('content="noindex,nofollow"',shadow)
            for name in ("broker-preview.html","broker-preview.js",
                         "broker-local-ui.js","cabinet.html","platform.html",
                         ".env.production","tests","production"):
                self.assertFalse((target/name).exists(),name)
            self.assertTrue((target/"art"/"lk-app.svg").is_file())
            self.assertTrue((target/"v5-service-cars.html").is_file())
            service=(target/"v5-service-cars.html").read_text(encoding="utf-8")
            self.assertIn("https://leasingcompass.ru/v5-service-cars.html",service)
            self.assertIn('<meta name="robots" content="index,follow">',service)
            self.assertFalse((target/"index.html").samefile(target/"variant-5.html"))
            root_xml=ElementTree.parse(target/"sitemap.xml")
            locations=[x.text for x in root_xml.iter() if x.tag.endswith("loc")]
            self.assertIn("https://leasingcompass.ru/",locations)
            self.assertIn("https://leasingcompass.ru/v5-service-cars.html",locations)
            self.assertNotIn("https://leasingcompass.ru/broker-preview.html",locations)
            self.assertEqual((target/"approved-test-key-2026.txt").read_text(),
                             "approved-test-key-2026")

if __name__=="__main__":
    unittest.main()
