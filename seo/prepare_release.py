"""Build separate production copy. Does not upload or modify preview."""
import argparse, pathlib, shutil, re, secrets
ROOT=pathlib.Path(__file__).resolve().parents[1]
PUBLIC=["index.html","comparison-direct.html","comparison-compass.html","service-cars.html","service-used.html","service-used-machines.html","service-trucks.html","service-machines.html","service-equipment.html","service-property.html","service-buyout.html","service-return.html","service-support.html","article-leasing-tax-check.html","article-leasing-subsidy-check.html","article-compare-leasing-offers.html","article-return-leasing.html","article-broker-or-direct.html","article-leasing-contract-check.html"]
PREVIEW="https://talysrus90-cmd.github.io/lizingkompas-unified/"
PROD="https://leasingcompass.ru/"
p=argparse.ArgumentParser()
p.add_argument("--output", required=True)
p.add_argument("--indexnow-key", help="Existing 8-128 character IndexNow ownership key; omit to generate")
p.add_argument("--confirm-ready", action="store_true", help="Confirm DNS, HTTPS, legal and content checks completed")
a=p.parse_args()
if not a.confirm_ready: p.error("Complete launch checklist before building indexable pages")
out=pathlib.Path(a.output).resolve()
if out.exists() or out==ROOT or ROOT in out.parents: p.error("Use a new folder outside source repository")
for f in PUBLIC:
    if not (ROOT/f).is_file(): p.error("Missing "+f)
key=a.indexnow_key or secrets.token_hex(16)
if not re.fullmatch(r"[A-Za-z0-9-]{8,128}",key): p.error("Invalid IndexNow ownership key")
# Production artifacts are restricted to public web asset types. Never copy backups,
# environment files, source tooling, or hidden repository content.
allowed={".html",".css",".js",".mjs",".json",".svg",".png",".jpg",".jpeg",".webp",".avif",".gif",".ico",".woff",".woff2",".ttf",".pdf",".txt",".xml",".webmanifest"}
blocked={"seo","node_modules","backups","tests","scripts","docs","__pycache__","CNAME"}
def exclude(directory,names):
    return [n for n in names if n.startswith(".") or n in blocked or
        ((pathlib.Path(directory)/n).is_file() and pathlib.Path(n).suffix.lower() not in allowed)]
shutil.copytree(ROOT,out,ignore=exclude)
for f in PUBLIC:
    path=out/f
    html=path.read_text(encoding="utf-8")
    html,n=re.subn(r'<meta\s+name="robots"\s+content="noindex,nofollow"\s*/?>','<meta name="robots" content="index,follow">',html,count=1,flags=re.I)
    if n!=1: raise RuntimeError("Missing preview guard: "+f)
    html=html.replace(PREVIEW,PROD)
    path.write_text(html,encoding="utf-8")
shutil.copyfile(ROOT/"seo/sitemap.production.xml",out/"sitemap.xml")
shutil.copyfile(ROOT/"seo/robots.production.txt",out/"robots.txt")
(out/(key+".txt")).write_text(key,encoding="utf-8")
print("Prepared production copy only:",out)
print("IndexNow public ownership key:",key)
print("Keep this key for subsequent releases: --indexnow-key",key)
print("No publishing or search engine notifications performed.")
