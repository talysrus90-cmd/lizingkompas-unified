"""IndexNow: preview payload by default; submit only changed canonical live URLs."""
import argparse, hashlib, json, pathlib, re, sys, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
from live_check import BASE, NS, check, request
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True,help="Local production build")
    p.add_argument("--previous",help="Previous deployed production build; if omitted all URLs are first-deployment candidates")
    p.add_argument("--key",required=True)
    p.add_argument("--submit",action="store_true",help="Explicitly notify IndexNow after successful production deployment")
    a=p.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]{8,128}",a.key): p.error("Invalid ownership key")
    root=pathlib.Path(a.root).resolve()
    urls=[x.text for x in ET.parse(root/"sitemap.xml").iter(NS+"loc")]
    if not urls or len(urls)!=len(set(urls)) or len(urls)>10000: p.error("Invalid sitemap URL count")
    selected=[]
    for url in urls:
        u=urlsplit(url)
        if u.scheme!="https" or u.netloc!=urlsplit(BASE).netloc or u.query or u.fragment or "%" in u.path: p.error("Unexpected sitemap URL")
        f=u.path.lstrip("/")\n        if not f or f.endswith("/"): f+="index.html"
        if ".." in pathlib.PurePosixPath(f).parts: p.error("Invalid path")
        file=root/f
        if not file.is_file(): p.error("Missing file "+f)
        text=file.read_text(encoding="utf-8")
        if 'content="index,follow"' not in text or 'href="'+url+'"' not in text: p.error("Not a production build: "+f)
        if a.previous:
            old=pathlib.Path(a.previous)/f
            if old.is_file() and hashlib.sha256(old.read_bytes()).digest()==hashlib.sha256(file.read_bytes()).digest(): continue
        selected.append(url)
    payload={"host":urlsplit(BASE).netloc,"key":a.key,"keyLocation":BASE+a.key+".txt","urlList":selected}
    print(json.dumps(payload,ensure_ascii=False,indent=2))
    if not a.submit:
        print("DRY RUN: no external request sent"); return 0
    if not selected: print("No changed pages"); return 0
    status,final,_,body=request(payload["keyLocation"])
    if status!=200 or final!=payload["keyLocation"] or body.decode("utf-8").strip()!=a.key: p.error("Public ownership key missing or mismatched")
    for url in selected:
        result=check(url)
        if not result["ok"]: p.error("Not index-ready: "+str(result))
    req=urllib.request.Request("https://api.indexnow.org/indexnow",data=json.dumps(payload).encode("utf-8"),headers={"Content-Type":"application/json; charset=utf-8"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            print("IndexNow HTTP",r.status,"accepted for processing; indexing is not guaranteed")
            return 0 if r.status in (200,202) else 1
    except urllib.error.HTTPError as e:
        print("IndexNow rejected:",e.code,file=sys.stderr); return 1
if __name__=="__main__": sys.exit(main())
