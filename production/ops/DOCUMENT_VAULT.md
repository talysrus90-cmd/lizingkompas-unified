# Compass Document: controlled deployment

**Current status: disabled.** This is a private PDF-original vault, not an OCR
engine, document classifier, contract review or electronic signature service.
Only the server-side operator process may expose these routes. The local A/B/C
financial workstation must not accept originals or personal data.

## Storage and scope
- One immutable original PDF per registered quote, max 5 MiB. Duplicates within
  the deal are rejected. No original file name stored. The original can contain
  personal/confidential information: do not ingest without a lawful basis.
- The bytes and document/case/quote identifiers are bound by authenticated
  encryption. SHA-256 and byte count are checked before download. Files are not
  placed under static/media URLs. The upload handler is bounded and memory-only.
- Role checks require quote and original-document permissions, scoped by assigned
  case. Upload requires change_quote and add_originaldocument. Public ingress
  rejects the whole /admin path. Internal financial-only cases are excluded.
- No automatic verification of the commercial terms: broker confirmation of
  terms remains separate. Files are downloaded as attachments, never rendered
  inline. Every successful upload and download is audited.

## Before approval on a Russian test server
1. Confirm operator/legal scope including original documents, access, retention,
   erasure procedures and incident response. Approve the corresponding policy.
2. Migrate and test against a disposable PostgreSQL database with synthetic PDFs,
   independent keys, no customer records. Test restore including document bytes,
   separate key recovery and equality of the original digest before/after restore.
   The general restore drill alone is insufficient.
3. Deploy ClamAV with current official signatures and monitored updates. Use a
   private Unix socket accessible only to the scanner and operator. Set stream
   and scan limits above 5 MiB and make sure limit exhaustion and encrypted or
   uninspectable documents cannot receive a clean verdict. Restrict scanner
   privileges, filesystem access and outbound access. No public TCP listener.
4. Mount only the dedicated socket directory into the operator container via a
   reviewed compose override (never Docker socket or arbitrary host directory).
   Check permissions for container UID/GID 10001. Example socket path inside
   operator: /run/compass-av/clamd.sock. Set the corresponding environment
   variable. Do not modify the public app or Caddy routes.
5. Exercise real clean synthetic PDF, safe standard malware-test sample in an
   isolated test environment, scanner stopped, oversized files, access denial,
   duplicate, altered ciphertext, encrypted/uninspectable PDF and recovery.
   Official protocol: https://docs.clamav.net/manual/Usage/ClamdProtocol.html .
6. Confirm storage quota, backup capacity and retention. DB ciphertext is
   included in PostgreSQL dumps; document-specific decrypt/restore must actually
   pass. Verify throughput and memory consumption. Antivirus is not a guarantee
   against every dangerous document.
7. Only after explicit approval, use the document-specific flags in
   .env.production.example and a controlled rollout. They are assertions of
   completed evidence, not proof by themselves. Keep feature off otherwise.

## Current automated evidence
Windows Django integration tests on a disposable database include upload/download,
encryption, role isolation, rejection of invalid/multiple files, duplicate upload,
tampered data and scanner denial. The scanner return values are mocked in these
tests; a real ClamAV instance has not been verified. Production deployment, OCR,
retention/erasure execution and document backup recovery remain outstanding.
