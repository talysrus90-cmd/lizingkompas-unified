"""Static landing-page engine. Review first; production only for explicitly approved records."""
import argparse
import datetime as dt
import html
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "https://leasingcompass.ru/"
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
SAFE_PATH = re.compile(r"(?:lizing|usloviya|regiony)/[a-z0-9]+(?:-[a-z0-9]+)*/")
MARKER = '<!-- compass-seo-hub -->'

def esc(value):
    return html.escape(str(value), quote=True)

def jsonld(value):
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")

def page_file(root, url_path):
    path = url_path.lstrip("/")
    if not path or path.endswith("/"):
        path += "index.html"
    if ".." in pathlib.PurePosixPath(path).parts:
        raise ValueError("unsafe URL")
    return pathlib.Path(root) / path

def load_catalog(path):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    pages = data["pages"]
    seen = {key: set() for key in ("path", "title", "h1", "description")}
    for p in pages:
        if not SAFE_PATH.fullmatch(p["path"]):
            raise ValueError("invalid path: " + p["path"])
        for key, values in seen.items():
            val = p[key].strip().casefold()
            if not val or val in values:
                raise ValueError("empty or duplicate " + key + ": " + p["path"])
            values.add(val)
        if p["status"] not in ("draft", "approved"):
            raise ValueError("unknown status")
        if len(p["blocks"]) < 2 or any(not b["q"].strip() or not b["a"].strip() for b in p["blocks"]):
            raise ValueError("insufficient useful content: " + p["path"])
        if p["status"] == "approved":
            if not p["approved_by"].strip() or not p["source"].strip():
                raise ValueError("approval or source missing: " + p["path"])
            reviewed = dt.date.fromisoformat(p["reviewed_on"])
            if reviewed > dt.date.today():
                raise ValueError("future review date")
            if p["path"].startswith("regiony/") and not all(p.get(k) is True for k in ("demand_verified","service_verified","unique_content_verified")):
                raise ValueError("regional evidence missing")
    return pages

CSS = """*{box-sizing:border-box}body{margin:0;font:16px/1.6 system-ui,sans-serif;color:#20344a;background:#f5f8fb}header,main,footer{max-width:850px;margin:auto;padding:20px}header{display:flex;align-items:center;justify-content:space-between;gap:16px}a{color:#087f5b}header a{font-weight:700}main{background:#fff;border-radius:14px}h1,h2{line-height:1.25;color:#142b45}h1{font-size:clamp(26px,5vw,40px)}h2{font-size:22px}.btn{display:inline-block;background:#087f5b;color:white;border-radius:9px;padding:12px 18px;text-decoration:none}.note{color:#526377;font-size:14px}li{margin:.4em 0}nav{font-size:14px}"""

def layout(title, description, canonical, body, ld, production):
    robots = "index,follow" if production else "noindex,nofollow"
    return f'<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="{robots}"><title>{esc(title)} | Лизинг Компас</title><meta name="description" content="{esc(description)}"><link rel="canonical" href="{esc(canonical)}"><style>{CSS}</style><script type="application/ld+json">{jsonld(ld)}</script></head><body>{body}</body></html>\n'

def make_page(p, production):
    url = BASE + p["path"]
    hub = "../../seo-guide/"
    review = "" if not p["reviewed_on"] else f'<p class="note">Проверено: <time datetime="{esc(p["reviewed_on"])}">{esc(p["reviewed_on"])}</time></p>'
    notice = "" if production else '<p class="note">Редакционный предпросмотр. Условия и содержание требуют проверки.</p>'
    blocks = "".join(f'<section><h2>{esc(b["q"])}</h2><p>{esc(b["a"])}</p></section>' for b in p["blocks"])
    body = f'<header><a href="../../">Лизинг Компас</a><a href="{hub}">Все направления</a></header><main><nav><a href="../../">Главная</a> / <a href="{hub}">Направления</a></nav>{notice}<h1>{esc(p["h1"])}</h1><p>{esc(p["description"])}</p>{blocks}{review}<p class="note">Условия определяются индивидуально; информация не является офертой.</p><a class="btn" href="../../#contacts">Связаться со специалистом</a></main><footer>Лизинг Компас · <a href="../../privacy.html">Политика обработки данных</a></footer>'
    ld = {"@context":"https://schema.org","@graph":[{"@type":"Organization","@id":BASE+"#organization","name":"Лизинг Компас","url":BASE},{"@type":"Service","name":p["title"],"description":p["description"],"url":url,"provider":{"@id":BASE+"#organization"}},{"@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"name":"Главная","item":BASE},{"@type":"ListItem","position":2,"name":"Направления","item":BASE+"seo-guide/"},{"@type":"ListItem","position":3,"name":p["title"],"item":url}]}]}
    return layout(p["title"],p["description"],url,body,ld,production)

def write_pages(root,pages,production):
    root = pathlib.Path(root)
    for p in pages:
        target = page_file(root,p["path"])
        if target.exists():
            raise FileExistsError(str(target))
    hub = root/"seo-guide"/"index.html"
    if hub.exists():
        raise FileExistsError(str(hub))
    for p in pages:
        target = page_file(root,p["path"])
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(make_page(p,production),encoding="utf-8")
    links = "".join(f'<li><a href="../{esc(p["path"])}">{esc(p["title"])}</a> — {esc(p["description"])}</li>' for p in pages)
    body=f'<header><a href="../">Лизинг Компас</a></header><main><h1>Направления и условия лизинга</h1><p>Справочник по выбору имущества и параметров сделки.</p><ul>{links}</ul></main><footer><a href="../#contacts">Контакты</a></footer>'
    hub.parent.mkdir(parents=True,exist_ok=True)
    hub.write_text(layout("Направления лизинга","Справочник по выбору имущества и условий финансирования.",BASE+"seo-guide/",body,{"@context":"https://schema.org","@type":"CollectionPage","name":"Направления лизинга","url":BASE+"seo-guide/"},production),encoding="utf-8")

def extend_release(root, pages):
    """Only modify a separate existing production build; never the repository."""
    root = pathlib.Path(root).resolve()
    if root == ROOT or ROOT in root.parents:
        raise ValueError("release must be outside the repository")
    index = root/"index.html"
    sitemap = root/"sitemap.xml"
    source = index.read_text(encoding="utf-8")
    if 'content="index,follow"' not in source or f'href="{BASE}"' not in source:
        raise ValueError("not a production release")
    if MARKER in source:
        raise ValueError("already extended")
    selected=[p for p in pages if p["status"]=="approved"]
    if not selected:
        return 0
    tree=ET.parse(sitemap)
    node=tree.getroot()
    urls={x.text for x in node.iter("{"+NS+"}loc")}
    additions=[BASE+"seo-guide/"]+[BASE+p["path"] for p in selected]
    if any(u in urls for u in additions):
        raise ValueError("duplicate sitemap URL")
    if "</main>" not in source:
        raise ValueError("missing insertion point")
    write_pages(root,selected,True)
    for url in additions:
        entry=ET.SubElement(node,"{"+NS+"}url")
        ET.SubElement(entry,"{"+NS+"}loc").text=url
        match=next((p for p in selected if BASE+p["path"]==url),None)
        if match:
            ET.SubElement(entry,"{"+NS+"}lastmod").text=match["reviewed_on"]
    ET.register_namespace("",NS)
    tree.write(sitemap,encoding="utf-8",xml_declaration=True)
    index.write_text(source.replace("</main>",MARKER+'<section class="section"><div class="container"><h2>Направления лизинга</h2><a class="btn btn-outline" href="./seo-guide/">Справочник направлений и условий</a></div></section></main>',1),encoding="utf-8")
    return len(selected)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--catalog",default=ROOT/"seo/catalog.json",type=pathlib.Path)
    group=ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--review",type=pathlib.Path,help="New noindex preview directory")
    group.add_argument("--extend-release",type=pathlib.Path,help="Existing separate production build; only approved records")
    a=ap.parse_args()
    pages=load_catalog(a.catalog)
    if a.review:
        out=a.review.resolve()
        if out.exists() or out==ROOT or ROOT in out.parents:
            ap.error("use a new directory outside the repository")
        write_pages(out,pages,False)
        # Working offline review navigation, without exposing real forms.
        (out/"index.html").write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><title>Лизинг Компас — проверка</title><main><h1>Редакционный предпросмотр</h1><a href="./seo-guide/">Открыть каталог</a><p id="contacts">Контактная форма в этом предпросмотре не подключена.</p></main></html>',encoding="utf-8")
        (out/"privacy.html").write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><title>Предпросмотр</title><p>Данные не собираются. Рабочая политика будет на основном сайте.</p></html>',encoding="utf-8")
        print("Review pages:",len(pages),"+ hub; noindex")
    else:
        print("Approved pages added:",extend_release(a.extend_release,pages))
    return 0
if __name__=="__main__":
    sys.exit(main())
