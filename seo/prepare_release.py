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
    "lk-ui-v504.js","lk-ui-v505.js","lk-share-v3.js","lk-growth-v2.js","client-entry.js",
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

def replace_legacy_demo_forms(html):
    """Remove four disabled preview-only PII forms from the public release.

    A single HTTPS Django /apply/ is the only authorized intake. Never transmit
    unsent form inputs through URL query strings, cookies or localStorage.
    """
    pattern=re.compile(
        r'<form\b[^>]*onsubmit="submitForm\(event,[^"]+"[^>]*>'
        r'[\s\S]*?</form>',
        flags=re.I,
    )
    sequence=[
        ("calc-lead-box","", "Индивидуальный расчёт",
         "Чтобы получить индивидуальное предложение, откройте защищённую форму."),
        ("","", "Получить подбор",
         "Ваш расчёт готов к следующему шагу. Для связи с брокером откройте защищённую форму."),
        ("card","", "Партнёрская заявка",
         "Свяжитесь с брокером через единую защищённую форму. Укажите в комментарии, что вы партнёр."),
        ("card",'id="request"', "Заявка на лизинг",
         "Данные вводятся и отправляются только через защищённую форму на нашем сервере."),
    ]
    number=0
    def upgrade(match):
        nonlocal number
        if number>=len(sequence):
            raise RuntimeError("Unexpected extra legacy intake form")
        cls,element_id,heading,description=sequence[number]
        number+=1
        css_class=(' class="'+cls+'"' if cls else '')
        identity=(' '+element_id if element_id else '')
        return (
            '<div'+css_class+identity+' data-compass-intake="production">'
            '<h4>'+heading+'</h4><p>'+description+'</p>'
            '<a href="/apply/" class="btn btn-primary"'
            ' style="display:inline-flex;min-height:48px;align-items:center;'
            'justify-content:center">Открыть защищённую заявку</a></div>'
        )
    html=pattern.sub(upgrade,html)
    if number!=len(sequence) or 'onsubmit="submitForm(' in html:
        raise RuntimeError("Legacy application forms changed; update secure release converter")
    return html


def replace_callback_demo(html):
    """Turn disabled red callback dialog into entry to working Django form."""
    start='<p class="demo-note">Номер остаётся на устройстве.'
    end='<p id="callbackResult"'
    if html.count(start)!=1 or html.count(end)!=1:
        raise RuntimeError("Callback dialog layout changed; secure converter needs update")
    left=html.index(start)
    right=html.index(end,left)
    stub=(
        '<p>Закажите звонок на защищённой странице. Телефон отправится только '
        'после вашего отдельного согласия.</p>'
        '<a href="/callback/" class="btn btn-primary" '
        'style="display:inline-flex;align-items:center;justify-content:center;'
        'min-height:48px;margin:10px 0 16px">Заказать обратный звонок</a>'
        '<div hidden aria-hidden="true">'
        '<input id="callbackPhone" type="tel">'
        '<input id="callbackConsent" type="checkbox">'
        '<button type="button" id="callbackDemo" disabled></button></div>'
    )
    return html[:left]+stub+html[right:]


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
        text=replace_legacy_demo_forms(text)
        text=replace_callback_demo(text)
        cta=('\n<div style="padding:12px 18px;text-align:center;background:#e9f4f1;'
             'border-bottom:1px solid #c1ddd6"><a href="/apply/" '
             'style="display:inline-block;color:#fff;background:#226b65;'
             'border-radius:11px;padding:12px 22px;font:700 16px system-ui;'
             'text-decoration:none">Подать заявку на лизинг</a></div>\n')
        if "</header>" not in text:raise RuntimeError("Missing site header")
        text=text.replace("</header>","</header>"+cta,1)
        text=text.replace('href="#request"','href="/apply/"')
        text=text.replace('</body>','<script src="/client-entry.js" defer></script>\n</body>',1)
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

    # Keep old/share URLs working on the real domain without serving demo forms.
    # Reuse the already transformed production page; only indexing differs.
    main_text=(out/"index.html").read_text(encoding="utf-8")
    main_text=main_text.replace(
        '<meta name="robots" content="index,follow">',
        '<meta name="robots" content="noindex,nofollow">',1)
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
        "User-agent: *\nAllow: /\nDisallow: /apply/\nDisallow: /client/\n"
        "Sitemap: "+PROD+"sitemap.xml\n",encoding="utf-8")
    (out/(key+".txt")).write_text(key,encoding="utf-8")
except Exception:
    shutil.rmtree(out,ignore_errors=True)
    raise

print("V5 production build created without publishing:",out)
print("Public HTML pages:",len(INDEXABLE))
print("IndexNow ownership key:",key)
print("Store the key safely for next release. No DNS/hosting or search submission performed.")
