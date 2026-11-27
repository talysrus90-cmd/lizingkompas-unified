# SEO Engine v1 — isolated development
Current public site and variant 5 are unchanged. Catalog: 13 draft landing pages and 15 regional research candidates; no keyword-volume or office claims. This is a content registry, not a browser admin panel. All entries require real editorial approval, verified service/terms and sources before indexing. Regions require distinct useful content, evidence of demand and actual service coverage, no fabricated addresses. No blanket geo clones.

## Workflow
- python -m unittest discover -s seo -p test_engine.py -v
- python seo/engine.py --review ../lk-seo-review
- Open ../lk-seo-review/index.html; noindex, no real forms.
- Edit seo/catalog.json after qualified review; status approved, actual approved_by, reviewed_on ISO date, source. For geo entries also demand_verified, service_verified, unique_content_verified.
- Existing production release command remains separate. After approval, run python seo/engine.py --extend-release ../leasingcompass-production. This only adds approved pages and updates sitemap and home link in that separate build. Do not run on working repo.
- Existing audit and IndexNow need directory URL handling (included in this branch). Production launch requires verified DNS, HTTPS, legal/PD review, actual form backend and validated content.
- Test reports are not proof of ranking, field Core Web Vitals or live indexability.

## Monitoring
Use Search Console, Yandex Webmaster, Bing Webmaster, actual query data and consent-aware analytics; do not scrape Google SERPs. Before launch run mobile Lighthouse/PSI on priority pages; target LCP <=2.5s, INP <=200ms, CLS <=0.1 at field p75, separated mobile/desktop; lab data and TBT are not measured field INP. Track TTFB <=600ms as internal target. Weekly: valid indexed pages, sitemap/robots errors, impressions/clicks/CTR, real leads, conversion rate, query/landing-page performance. AI discovery: helpful factual material, expert review, crawlability; no special schema or guaranteed citations.
No tokens, customer data or real submissions in public repo. Search accounts and host require explicit verified access.

References:
- https://developers.google.com/search/docs/appearance/ai-features
- https://developers.google.com/search/docs/essentials/spam-policies
- https://developers.google.com/search/docs/appearance/core-web-vitals
- https://yandex.ru/support/webmaster/ru/site-geography/site-region
- https://www.indexnow.org/documentation
