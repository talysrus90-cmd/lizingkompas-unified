# Compass Document: local import pilot

## Supported adapters in this revision
- PDF: physical page number, extract embedded text, mark empty text for OCR. No OCR or visual layout reconstruction; mixed text/image pages can also need OCR.
- DOCX: main-body paragraphs and top-level table cells, in body order. Word has no stable page numbering in this representation. Headers, footers, comments, tracked changes, embedded pictures and nested tables may be absent.
- XLSX: worksheet/cell/row/column coordinates, literal values; formula cells flagged and never evaluated, hidden sheets labelled. Number/date display formatting not reproduced. An explicit visible worksheet with exactly three literal columns can be converted to a canonical payment schedule draft.
- TXT, CSV (semicolon), TSV: UTF-8 or explicitly selected Windows-1251; line/record/column coordinates. No guessed encoding.
- Browser Finance Pro: direct CSV/TSV/TXT selection and insertion into existing confirmation form; local decoding, no raw file upload. XLSX pilot is CLI, not browser file upload.

## Execution
Use an isolated Python environment, not the CRM production environment:
    python -m pip install -r broker/requirements-document-import.txt
    python -m broker.document_import example.docx --confirm-trusted-anonymised
    python -m broker.document_import example.xlsx --confirm-trusted-anonymised --schedule-sheet "График"

Output JSON contains source SHA-256, source coordinates, text and warnings; optional schedule_draft is NOT automatically saved. Do not redirect output into unapproved shared storage. Dependencies are direct-version pinned for QA, not a fully hashed lock or vulnerability audit.

## Security and readiness
Pilot only for trusted synthetic/anonymised documents. No production upload endpoint, network fetching, formula execution, macros, external Office relationships or archive unpacking to disk. 5 MiB input; Office packages bounded to 32 MiB expanded, 512 entries; PDF maximum 100 pages; extracted text/blocks and spreadsheet dimensions bounded. XML DTD/entities forbidden. These checks do not replace malware scanning, process isolation, memory/CPU/time limits or dependency security review. PDF content decoding can allocate memory before size checks; never process untrusted documents in the CRM process. Human verification required for every extracted value; no assumption that extraction is complete.

## Roadmap
- OCR scans/photos (PDF, JPEG, PNG, TIFF, HEIC, WebP, BMP), with physical page/image reference and confidence.
- ODT/ODS, RTF, legacy DOC/XLS/XLSB, PPT/PPTX through separate tested adapters; conversion sandbox, no active content.
- EML/MSG: message text and attachment inventory; explicit selection of individual attachments, never follow links or execute content.
- JSON/XML/HTML: strict schemas, no scripts, external entities, remote fetching.
- ZIP/7Z/RAR: separate quarantine and bounded extraction policy; archives are not trusted documents.
- Unified file-picker UI for Office/PDF after isolated worker and QA. Source file fingerprint, evidence location, manual approval, no automatic transfer to client or lender.


## Local workbench and additional adapters
Run `python -m broker.document_workbench` using the isolated document environment. The Tk window requires explicit trusted/anonymised confirmation, opens the file in a child process with a 45-second timeout, displays source coordinates, and copies an explicitly generated XLSX/CSV/TSV schedule draft to the clipboard. It does not write CRM records; paste into Finance Pro and confirm the original. Child-process timeout is not a sandbox. No automatic OCR.
- ODT: paragraph element order only, not page numbers.
- ODS: literal cells and row/column coordinates, no formula evaluation or reliable layout/visibility. Not supported for direct schedule conversion.
- EML: unverified header fields, plain text body and attachment filenames/content types. No attachment extraction, HTML rendering or network fetching.
- Still pending: legacy DOC/XLS/XLSB, RTF, image OCR, MSG, PPT/PPTX, archives and structured HTML/XML/JSON adapters. Untrusted files need separately isolated production processing.
