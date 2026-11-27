"""Check canonical production URLs, redirects, metadata and indexability. No mutations."""
import argparse, concurrent.futures, json, re, sys, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urlsplit
BASE="https://leasingcompass.ru/"
NS="{http://www.sitemaps.org/schemas/sitemap/0.9}"
class Meta(HTMLParser):
    def __init__(self):
        super().__init__(); self.meta={}; self.canon=[]; self.lang=""; self.h1=0; self.title=0
    def handle_starttag(self,t,attrs):
        a=dict(attrs)
        if t=="meta" and "name" in a: self.meta[a["name"].lower()]=a.get("content","")
        if t=="link" and "canonical" in a.get("rel","").split(): self.canon.append(a.get("href",""))
        if t=="html": self.lang=a.get("lang","")
        if t=="title": self.title+=1
        if t=="h1": self.h1+=1
def request(url,agent="LeasingCompass-LaunchAudit/1.0"):
    req=urllib.request.Request(url,headers={"User-Agent":agent,"Accept":"text/html,application/xml,text/plain,*/*","Cache-Control":"no-cache"})
    with urllib.request.urlopen(req,timeout=12) as r:
        body=r.read(2_000_001)
        if len(body)>2_000_000: raise ValueError("response exceeds audit size limit")
        return r.status,r.geturl(),dict(r.headers.items()),body
def check(url):
    errors=[]
    try:
        status,final,headers,body=request(url)
        if status!=200 or final!=url: errors.append("HTTP/redirect: "+str(status)+" "+final)
        h={k.lower():v.lower() for k,v in headers.items()}
        if "noindex" in h.get("x-robots-tag","") or "none" in h.get("x-robots-tag",""): errors.append("X-Robots-Tag blocks indexing")
        if "text/html" not in h.get("content-type",""): errors.append("not HTML")
        m=Meta(); m.feed(body.decode("utf-8"))
        for k,v in m.meta.items():
            if k in ("robots","googlebot","yandex","bingbot") and re.search(r"\b(noindex|none)\b",v,re.I): errors.append(k+" blocks indexing")
        if m.canon!=[url]: errors.append("canonical "+str(m.canon))
        if m.lang!="ru" or m.h1!=1 or m.title!=1 or not m.meta.get("description"): errors.append("missing required page metadata")
        if b"Leasing Compass" not in body and "Лизинг Компас" not in body.decode("utf-8"): errors.append("site identity not found")
    except Exception as exc: errors.append(str(exc))
    return {"url":url,"ok":not errors,"errors":errors}
def run():
    p=argparse.ArgumentParser(); p.add_argument("--json",action="store_true"); a=p.parse_args()
    errors=[]; urls=[]; results=[]
    try:
        status,final,headers,body=request(BASE+"robots.txt")
        if final!=BASE+"robots.txt" or status!=200: errors.append("robots redirect/status")
        robots=body.decode("utf-8")
        if "Sitemap: "+BASE+"sitemap.xml" not in robots: errors.append("production sitemap missing in robots")
        if re.search(r"^\s*Disallow\s*:\s*/\s*(?:#.*)?$",robots,re.M|re.I): errors.append("possible blanket crawl block")
        status,final,headers,body=request(BASE+"sitemap.xml")
        if final!=BASE+"sitemap.xml" or status!=200: errors.append("sitemap redirect/status")
        urls=[x.text for x in ET.fromstring(body).iter(NS+"loc")]
        if not urls or BASE not in urls or len(urls)!=len(set(urls)): errors.append("empty, incomplete or duplicate sitemap")
        if len(urls)>1000 or any(not u or not u.startswith(BASE) or urlsplit(u).query or urlsplit(u).fragment for u in urls): raise ValueError("unexpected sitemap URLs")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(check,urls))
    except Exception as exc: errors.append(str(exc))
    result={"ready":not errors and bool(results) and all(r["ok"] for r in results),"pages":len(results),"errors":errors,"results":results}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["ready"] else 1
if __name__=="__main__": sys.exit(run())
