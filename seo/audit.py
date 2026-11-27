"""Validate preview or production SEO; Python 3 standard library only."""
import argparse, json, pathlib, sys, xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urlsplit
class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lang=None; self.title=0; self.h1=0; self.meta={}; self.canon=[]; self.missing_alt=0; self.hrefs=[]; self.grids={}; self.grid=None; self.ld=[]; self.ld_open=False; self.ld_data=""
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="html": self.lang=a.get("lang")
        if tag=="title": self.title+=1
        if tag=="h1": self.h1+=1
        if tag=="meta" and "name" in a: self.meta[a["name"]]=a.get("content","")
        if tag=="link" and a.get("rel")=="canonical": self.canon.append(a.get("href"))
        if tag=="img" and "alt" not in a: self.missing_alt+=1
        if tag=="a" and "href" in a: self.hrefs.append(a["href"])
        if a.get("id") in ("servicesGrid","blogGrid","casesGrid"):
            self.grids[a["id"]]=True
        if tag=="script" and a.get("type")=="application/ld+json": self.ld_open=True; self.ld_data=""
    def handle_data(self,data):
        if self.ld_open: self.ld_data+=data
    def handle_endtag(self,tag):
        if tag=="script" and self.ld_open:
            self.ld.append(json.loads(self.ld_data)); self.ld_open=False
p=argparse.ArgumentParser()
p.add_argument("--root",default=str(pathlib.Path(__file__).resolve().parents[1]))
p.add_argument("--production",action="store_true")
a=p.parse_args(); root=pathlib.Path(a.root); errors=[]
preview="https://talysrus90-cmd.github.io/lizingkompas-unified/"
prod="https://leasingcompass.ru/"
base=prod if a.production else preview
sitemap=root/("sitemap.xml" if a.production else "seo/sitemap.production.xml")
locs=[e.text for e in ET.parse(sitemap).getroot().iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
if len(locs)!=len(set(locs)): errors.append("Duplicate sitemap URLs")
for url in locs:
    if not url.startswith(prod): errors.append("Wrong sitemap host: "+url); continue
    name=url[len(prod):] or "index.html"; f=root/name
    if not f.is_file(): errors.append("Missing page: "+name); continue
    html=f.read_text(encoding="utf-8"); page=Page()
    try: page.feed(html)
    except Exception as e: errors.append(name+": invalid structured data: "+str(e)); continue
    wanted=base+("" if name=="index.html" else name)
    for ok,detail in [(page.lang=="ru","lang"),(page.title==1,"title"),(page.h1==1,"h1"),(bool(page.meta.get("description")),"description"),(page.canon==[wanted],"canonical"),(page.missing_alt==0,"image alt"),(bool(page.ld),"JSON-LD"),(page.meta.get("robots")==("index,follow" if a.production else "noindex,nofollow"),"robots meta")]:
        if not ok: errors.append(name+": "+detail)
    if name=="index.html":
        service_prefix="./v5-service-" if a.production else "./service-"
        services={urlsplit(x).path for x in page.hrefs if urlsplit(x).path.startswith(service_prefix)}
        articles={urlsplit(x).path for x in page.hrefs if urlsplit(x).path.startswith("./article-")}
        if len(services)<10: errors.append("Missing static service links")
        if len(articles)<6: errors.append("Missing static article links")
    for href in page.hrefs:
        u=urlsplit(href)
        if not u.scheme and not u.netloc and u.path.endswith(".html") and not (f.parent/u.path).is_file(): errors.append(name+": broken local link "+href)
if a.production:
    keys=[p for p in root.glob("*.txt") if p.name!="robots.txt" and 8<=len(p.stem)<=128 and p.read_text(encoding="utf-8").strip()==p.stem]
    if len(keys)!=1: errors.append("Missing or ambiguous IndexNow ownership key")
    for n in ("cabinet.html","self-service.html"):
        if (root/n).exists() and "noindex" not in (root/n).read_text(encoding="utf-8"): errors.append("Private/demo page indexable: "+n)
    if "Sitemap: "+prod+"sitemap.xml" not in (root/"robots.txt").read_text(encoding="utf-8"): errors.append("Production robots sitemap missing")
print("Pages checked:",len(locs))
for e in sorted(set(errors)): print("ERROR",e)
sys.exit(1 if errors else 0)
