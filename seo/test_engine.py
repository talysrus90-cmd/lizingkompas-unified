import copy, json, pathlib, tempfile, unittest, xml.etree.ElementTree as ET
from engine import ROOT, BASE, load_catalog, write_pages, extend_release, page_file, make_page

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.pages=load_catalog(ROOT/"seo/catalog.json")
        self.tmp=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def catalog(self, p):
        f=self.root/"catalog.json"
        f.write_text(json.dumps({"pages":p},ensure_ascii=False),encoding="utf-8")
        return f
    def release(self):
        d=self.root/"release";d.mkdir()
        (d/"index.html").write_text(f'<meta name="robots" content="index,follow"><link rel="canonical" href="{BASE}"><main></main>',encoding="utf-8")
        (d/"sitemap.xml").write_text(f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>{BASE}</loc></url></urlset>',encoding="utf-8")
        return d
    def approved(self):
        p=copy.deepcopy(self.pages[0])
        p.update(status="approved",approved_by="Synthetic QA fixture",reviewed_on="2025-01-01",source="Synthetic fixture; not a real approval")
        return p
    def test_review_all_noindex(self):
        write_pages(self.root,self.pages,False)
        self.assertTrue((self.root/"seo-guide/index.html").is_file())
        for p in self.pages:
            self.assertIn('content="noindex,nofollow"',page_file(self.root,p["path"]).read_text(encoding="utf-8"))
    def test_duplicate(self):
        with self.assertRaises(ValueError):
            load_catalog(self.catalog([self.pages[0],self.pages[0]]))
    def test_invalid_path(self):
        p=copy.deepcopy(self.pages[0]);p["path"]="../outside/"
        with self.assertRaises(ValueError):load_catalog(self.catalog([p]))
    def test_unapproved_rejected(self):
        p=copy.deepcopy(self.pages[0]);p["status"]="approved"
        with self.assertRaises(ValueError):load_catalog(self.catalog([p]))
    def test_region_evidence(self):
        p=self.approved();p["path"]="regiony/test/"
        with self.assertRaises(ValueError):load_catalog(self.catalog([p]))
    def test_drafts_not_published(self):
        d=self.release()
        self.assertEqual(extend_release(d,self.pages),0)
        self.assertFalse((d/"seo-guide").exists())
    def test_approved_sitemap_and_links(self):
        d=self.release();p=self.approved();validated=load_catalog(self.catalog([p,self.pages[1]]))
        self.assertEqual(extend_release(d,validated),1)
        self.assertIn(BASE+p["path"],(d/"sitemap.xml").read_text(encoding="utf-8"))
        self.assertNotIn(BASE+self.pages[1]["path"],(d/"sitemap.xml").read_text(encoding="utf-8"))
        self.assertIn('content="index,follow"',page_file(d,p["path"]).read_text(encoding="utf-8"))
        self.assertIn("./seo-guide/",(d/"index.html").read_text(encoding="utf-8"))
    def test_escape(self):
        p=copy.deepcopy(self.pages[0]);p["h1"]="<script>alert(1)</script>"
        self.assertIn("&lt;script&gt;",make_page(p,False))
    def test_existing_file_protected(self):
        write_pages(self.root,self.pages,False)
        with self.assertRaises(FileExistsError):write_pages(self.root,self.pages,False)

if __name__=="__main__":unittest.main()
