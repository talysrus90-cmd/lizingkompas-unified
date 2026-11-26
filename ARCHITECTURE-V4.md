# Unified V4.1 — implementation and launch gates
## Provenance
- V2.14 is the code base: original logo, messenger SVG assets, callback demo, finance tools, client cabinet and legal page files.
- Qwen visual preview: result panel, two-column service cards, broker comparison, numbered process, examples and market chips. Residual value is included in discounted annuity formula. No simulated tax savings or real-offer claims.
- V1 reviewed: editable CMS and lead CSV concept retained as a future requirement, not copied because it uses local browser data and cannot provide secure multi-user access.
## Current state
Static demo only. No real lead submission, no authentication, no real leasing-company/BKI/EDO adapters. Platform roles are illustrative read-only views on fictional data; no authorization claims.
## Production architecture
1. Separate frontend component modules, shared typed calculation engine, server-verified input and fixed-point monetary values; independently test schedule, residual, fees and rounding.
2. FastAPI or equivalent backend with PostgreSQL, migrations and RBAC plus object-level access checks. Partner may see only assigned applications; client only own application; broker scoped to organization. Enforce stages on server and log every transition.
3. Secure session management, MFA for staff, persistent managed encryption keys, rotating secrets, server-side rate limiting, encrypted object storage and backups; never use default credentials or browser localStorage for real applications.
4. Separate adapters for each real leasing partner, only mark offers real after verified receipt; legal and commercial agreements before integration. BKI/EDO only after verified access and consent.
5. CMS role for approved text/config changes, revision history, draft/publish, audit. No secrets or rates supplied by untrusted browser storage.
6. Tax estimates only after explicit validated inputs and current tax/legal review, no guaranteed savings.
7. Russian deployment and personal data compliance verification prior to enabling actual submissions; confirm messenger account links and callback delivery. No legal compliance claim from demo.
