# Document Extraction and Verification Checklist

> **Note:** The raw PDFs, OCR output and page images mentioned below are kept locally and are
> not published in this repository, because their redistribution terms have not yet been
> reviewed. Official source URLs and dates are listed in `data/sources.yaml`, and the
> documents can be re-collected from those sources.

Purpose: Track file completeness, OCR consistency, visual verification, and current validity separately.

## NID-001 — Form 6
- [x] PDF present; 2 page-level text files accounted for.
- [x] Manual transcription created and reviewed.
- [x] Both page images visually reviewed by the author.
- [x] Page 2 transcription includes instructions (1) through (8).
- [x] Verification notes recorded in verification.txt.
- [ ] Resolve any remaining uncertain wording against the original PDF.
- [ ] Check current official guidance before presenting requirements as current.
- Note: Do not use the noisy OCR drafts as authoritative text. The manually reviewed transcription is the preferred text source. This form refers to the 2014 rules; visual review does not establish current validity.

## NID-007 — National Identity Registration Rules, 2014
- [x] PDF present; 23 page-level text files accounted for.
- [x] Combined OCR rebuilt from page-level text.
- [x] All 23 combined page sections match their page-level files.
- [x] Page 1 visually inspected; corrections made.
- [x] Page 15 manually inspected against the original PDF; corrections made.
- [ ] Compare remaining pages against the original PDF.
- [ ] Check legal references and eligibility requirements for OCR errors.
- Note: OCR consistency does not establish transcription accuracy. This is a historical legal document.

## NID-008 — 2015 Amendment
- [x] PDF present; 2 page-level text files accounted for.
- [x] Both page images visually reviewed by the author.
- [x] Page-level text files reviewed and corrected against the scans.
- [x] Combined OCR rebuilt from the corrected page-level text.
- [x] Combined OCR content matches page-level text after whitespace normalization.
- [x] Fee table visually verified against the original PDF.
- [x] Verification record documents the source dates and historical fee figures.
- [ ] Resolve any remaining uncertain legal wording against the original scan.
- [ ] Check later amendments and current official guidance before answering current-fee or legal-requirement questions.
- Note: The amendment dates to February 2015. Verified fees are historical, not confirmed current fees.

## NID-009 — 2014 Regulation
- [x] PDF present; 20 page-level text files accounted for.
- [x] Combined OCR rebuilt from page-level text.
- [x] All 20 combined page sections match their page-level files.
- [x] Pages 14 and 16 visually inspected; corrections made.
- [x] Rule 11 fee table visually checked against the original Gazette.
- [ ] Verify remaining pages and legal wording.
- Note: Historical fees must not be presented as current without verification.

## NID-010 — 2023 Amendment
- [x] PDF present; 3 page-level text files accounted for.
- [x] Combined OCR rebuilt from page-level text.
- [x] All 3 combined page sections match their page-level files.
- [x] Pages 1 and 2 manually compared against the original PDF; identified mismatches corrected.
- [x] Page 3 visually inspected; corrections made.
- [ ] Independently verify remaining wording and the complete fee table against the original PDF.
- [ ] Verify effective-date wording and subsequent amendments.
- Note: OCR-transcribed fees are not confirmed current fees.

## NID-011 — Form 2
- [x] PDF present; 2 page-level text files accounted for.
- [x] Both page-level text files manually compared against the original PDF; identified mismatches corrected.
- [x] Combined OCR rebuilt from the corrected page-level text.
- [x] Both combined page sections match their page-level files.
- [x] Form fields, correction categories, and instructions reviewed against the original PDF during manual comparison.
- [ ] Independently verify all applicable evidence requirements and legal wording.
- [ ] Check current requirements against official, up-to-date sources.
- Note: The original PDF remains authoritative. OCR consistency does not establish current legal validity.

## Project-wide checks
- [x] Six PDFs accounted for: 52 pages and 52 page-level text files.
- [x] No empty processed text files found in the structural audit.
- [x] No processed text files under 100 non-whitespace characters found.
- [x] No remaining HTML captures found in the earlier audit.
- [x] Combined OCR files for NID-007, NID-009, NID-010, and NID-011 rebuilt from page-level text.
- [x] Combined OCR consistency checks passed for NID-007, NID-009, NID-010, and NID-011.
- [x] NID-008 combined OCR content matches page-level text after whitespace normalization.
- [ ] Review remaining OCR warning patterns in context.
- [ ] Confirm authoritative source URLs and publication dates.
- [ ] Verify current validity before using legal rules, fees, or requirements in public-facing answers.

## Status definitions
- [x] Completed check only; does not imply every word is accurate or the information is current.
- [ ] Not yet completed.