# Secure intake V1 — isolated reference implementation
Stable website V5.08 and public GitHub Pages untouched. This code is intentionally not deployed. GitHub Pages cannot run Python or persist private data. Do not use real data until operator confirms approved documents, hosting and authorization.
## Run locally using synthetic data only
Python 3.11+; standard library. From repository root:
```
python -m unittest discover -s intake -p "test_*.py" -v
```
For service startup set LK_DB to an absolute private location, LK_ORIGIN to verified HTTPS origin, LK_CONSENT_VERSION to actual approved consent revision and LK_ENABLE_INTAKE=approved only after all launch gates. Default returns 503 for submission. Server binds 127.0.0.1:8088. WSGI reference server for local QA only; for public use select a maintained production WSGI runner and reverse proxy.
## Production gates (not fulfilled)
- Verify operator address, consent text, policy, retention/withdrawal process, any required Roskomnadzor notification and localization obligations with qualified counsel. Current consent.html is a draft with unconfirmed address.
- Russia-hosted HTTPS application + database, dedicated least-privilege service account, storage encryption/key management, encrypted backups, log redaction, restore test, monitoring and incident response. No personal data in Git, public static files or third-party analytics.
- Reverse proxy per-client rate limit, bot mitigation, TLS, max request body, timeouts; origin check is not authentication. App's global ceiling is only a safety fallback.
- Implement authorized operator queue with MFA, audit trail and retention/deletion workflows before launch. SQLite is a starter for low volume, not a substitute for production access management; migrate to managed PostgreSQL as needed.
- Integrate frontend same-origin POST /api/leads only after gates; capture separate affirmative consent and exact approved revision. Disable real submission until configured. No actual data transmitted by current site.
- Receipt indicates durable record only, not successful callback, offer or delivery to a leasing company. Do not auto-forward to partners.
- Use UTM tags for attribution, never names/INN/phone in UTM. Add CRM only with approved processor agreements and verified access.
## Next integrations
1. Organization lookup from verified provider using INN (only requested fields, server-side key).
2. Private CRM pipeline with deduplication and callback SLA; notification contains ticket ID only, authenticated operator opens queue.
3. MAX bot via approved profile and official API; no token in frontend. Keep sending actual documents separate.
4. Metrics for accepted, qualified and contracted leads, no PII in events.
5. Provider offers catalog with source, effective date, eligibility and review; deterministic financial calculations before AI commentary.
