"""Build an isolated indexable V5 production site, never publish automatically.

Only whitelisted site assets are copied. Broker, account and development preview
files are NEVER part of production static output. Customer applications are
served by the separately protected Django /apply/ endpoint on the same domain.
"""
import argparse
import pathlib
import re
import secrets
import shutil
from xml.etree.ElementTree import Element, SubElement, ElementTree, register_namespace

ROOT=pathlib.Path(__file__).resolve().parents[1]
PROD="https://leasingcompass.ru/"
PREVIEW="https://talysrus90-cmd.github.io/lizingkompas-unified/"
MAIN="variant-5.html"
SERVICES=sorted(path.name for path in ROOT.glob("v5-service-*.html"))
COMPARISONS=sorted(path.name for path in ROOT.glob("v5-comparison-*.html"))
ARTICLES=sorted(path.name for path in ROOT.glob("article-*.html"))
INDEXABLE=[MAIN]+SERVICES+COMPARISONS+ARTICLES
LEGAL=["privacy.html","consent.html"]
OTHER=["leasing-checklist.html","partner-calculator.html"]
ASSETS={
    "lk-ui-v504.js","lk-ui-v505.js","lk-share-v3.js","lk-growth-v2.js",
    "lk-widget-v1.js","lk-public-tools.css","service-theme.css",
    "lk-app.webmanifest","leasing-compass.vcf","max.svg","telegram.svg",
    "vk.svg","whatsapp.svg","youtube.svg",
}
IMG_EXTS={".svg",".png",".jpg",".jpeg",".webp",".avif",".gif",".ico",".woff2"}
p=argparse.ArgumentParser()
p.add_argument("--output",required=True)
p.add_argument("--indexnow-key")
p.add_argument("--confirm-ready",action="store_true",
               help="Human-approved RKN/policy, host, TLS, sources and images")
a=p.parse_args()
if not a.confirm_ready:
    p.error("Approval required. Do not make an indexable build of an unapproved site")
out=pathlib.Path(a.output).resolve()
if out.exists() or out==ROOT or ROOT in out.parents:
    p.error("Output must be a NEW folder outside the repository")
if len(INDEXABLE)<10:
    p.error("V5 public service files missing")
for name in INDEXABLE+LEGAL+OTHER+list(ASSETS):
    if not (ROOT/name).is_file():p.error("Missing required V5 file: "+name)
key=a.indexnow_key or secrets.token_hex(16)
if not re.fullmatch(r"[A-Za-z0-9-]{8,128}",key):p.error("Invalid IndexNow key")

def canonical(text,url):
    text=re.sub(r'<link\s+rel=["\']canonical["\'][^>]*>','',text,flags=re.I)
    text=text.replace("</head>",f'<link rel="canonical" href="{url}">\n</head>',1)
    if 'rel="canonical"' not in text:
        raise RuntimeError("Cannot set canonical: missing head closing tag")
    return text

def transform(text,name):
    text=text.replace(PREVIEW,PROD)
    text=text.replace('href="./variant-5.html"','href="/"')
    text=text.replace('href="variant-5.html"','href="/"')
    text=re.sub(r'<meta\s+name=["\']robots["\']\s+content=["\']noindex,nofollow["\']\s*/?>',
                '<meta name="robots" content="index,follow">',text,count=1,flags=re.I)
    if '<meta name="robots" content="index,follow">' not in text:
        raise RuntimeError("Missing index guard for "+name)
    target=PROD if name==MAIN else PROD+name
    text=canonical(text,target)
    # Explicit application entry on the real domain only.
    if name==MAIN:
        cta=('\n<div style="padding:12px 18px;text-align:center;background:#e9f4f1;'
             'border-bottom:1px solid #c1ddd6"><a href="/apply/" '
             'style="display:inline-block;color:#fff;background:#226b65;'
             'border-radius:11px;padding:12px 22px;font:700 16px system-ui;'
             'text-decoration:none">Подать заявку на лизинг</a></div>\n')
        if "</header>" not in text:raise RuntimeError("Missing site header")
        text=text.replace("</header>","</header>"+cta,1)
        text=text.replace('href="#request"','href="/apply/"')
    return text

out.mkdir(parents=True)
try:
    # Copy files from explicit allowlists, not broad recursive tree.
    for name in LEGAL+OTHER+list(ASSETS):
        source=ROOT/name
        target=out/name
        content=source.read_bytes()
        if source.suffix in (".html",".js",".webmanifest",".css"):
            try:
                content=content.decode("utf-8").replace(PREVIEW,PROD).encode("utf-8")
            except UnicodeDecodeError:
                raise RuntimeError("Non-UTF8 asset: "+name)
        target.write_bytes(content)

    art=ROOT/"art"
    if not art.is_dir():raise RuntimeError("Missing art assets")
    for source in art.rglob("*"):
        if not source.is_file():continue
        if source.is_symlink():raise RuntimeError("Unexpected linked asset")
        if source.suffix.lower() not in IMG_EXTS:continue
        relative=source.relative_to(ROOT)
        target=out/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)

    for name in INDEXABLE:
        text=(ROOT/name).read_text(encoding="utf-8")
        converted=transform(text,name)
        target="index.html" if name==MAIN else name
        (out/target).write_text(converted,encoding="utf-8")

    # Legacy preview link remains available but nonindexable to prevent duplicate URLs.
    main_text=(ROOT/MAIN).read_text(encoding="utf-8").replace(PREVIEW,PROD)
    main_text=canonical(main_text,PROD)
    (out/MAIN).write_text(main_text,encoding="utf-8")
    # Don't accidentally create public admin, broker or laboratory pages.
    forbidden={"broker-preview.html","cabinet.html","platform.html",
               "self-service.html","preview-419.html","broker-local-ui.js"}
    if any((out/name).exists() for name in forbidden):
        raise RuntimeError("Private/demo asset reached production build")
    register_namespace("", "http://www.sitemaps.org/schemas/sitemap/0.9")
    urlset=Element("{http://www.sitemaps.org/schemas/sitemap/0.9}urlset")
    for name in INDEXABLE:
        item=SubElement(urlset,"{http://www.sitemaps.org/schemas/sitemap/0.9}url")
        loc=SubElement(item,"{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
        loc.text=PROD if name==MAIN else PROD+name
    ElementTree(urlset).write(out/"sitemap.xml",encoding="utf-8",xml_declaration=True)
    (out/"robots.txt").write_text(
        "User-agent: *\nAllow: /\nDisallow: /apply/\n"
        "Sitemap: "+PROD+"sitemap.xml\n",encoding="utf-8")
    (out/(key+".txt")).write_text(key,encoding="utf-8")
except Exception:
    shutil.rmtree(out,ignore_errors=True)
    raise

print("V5 production build created without publishing:",out)
print("Public HTML pages:",len(INDEXABLE))
print("IndexNow ownership key:",key)
print("Store the key safely for next release. No DNS/hosting or search submission performed.")
