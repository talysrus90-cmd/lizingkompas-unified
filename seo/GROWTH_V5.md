# Growth tools V5.03
Preview only, no collection of leads, cookies, contact list or external tracking SDK.
- Calc share: explicit action, validated bounded parameters in URL fragment (not transmitted in standard HTTP request); recipient recomputes at current rates. Never put customer IDs or documents in URL. Sharing still exposes chosen values to recipient.
- Partner embed: isolated responsive iframe; code is a self-assigned demo UTM tag, not authenticated account. Production requires allowed partner registry, signed attribution, deduplication, fraud review, actual CRM receipt, documented partner terms and legal review before payouts.
- QR and vCard target preview. Replace with verified canonical production URL before printing/public use. Confirm phone/email and branding.
- OG image uses existing compass artwork; messaging app rendering and cache require real-device QA. No guaranteed rich previews.
- MAX mini app: widget may serve as prototype; actual launch requires verified MAX business profile, bot registration, moderation, secure backend if identity or leads are processed. Do not publish bot token. https://dev.max.ru/docs/webapps/introduction
- Analytics: UTM tags are available, no provider connected here. Count landing sessions/qualified leads after approved analytics integration; no claims of send success merely from opening OS share.
- Test widths 320/360/390/412/768/1440, actual Android/iOS and embedded iframe. Test native share cancel, fallback copy, scan QR, vCard import, browser history, calc restore and no overlap with sticky summary. Tests cover pure functions only.
