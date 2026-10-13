# Performance plan

**Rules**
- No visible change to any screen and no information dropped. Every item must end up showing exactly
  what users see today, only sooner. Each item is checked against the existing screen tests.
- If loading everything takes time, load the first part first; load all (or a specific item) only
  when the user asks for it.

**Measured 2026-10-13 (laptop → AWS SQL Server):** one network round trip ≈ 54 ms; one app query
≈ 160 ms (connection check + query + connection reset = 3 round trips). Screens run their queries
one after another (visit detail: 7–8 queries ≈ 1.5 s) and nothing is reused between requests.

| # | Item | Same screen, same data? | Status |
|---|---|---|---|
| **A. Fewer and faster database trips** | | | |
| 1 | No per-query connection check / reset: autocommit reads, ping only after 60 s idle | Yes | **Done**: 162 → 55 ms per query; visit detail 1.5 → 0.66 s |
| 2 | Run independent queries at the same time (header, Overview, visit detail, notes, documents, patient list) | Yes, verified: identical data fingerprints old vs new | **Done**: header 0.33 → 0.11 s, visit detail 0.66 → 0.22 s |
| 3 | Visits: ask the database only for real visits by default; "All entries" still loads every entry | Yes, verified on 26 real patients (same rows; display sorted by date, ties now stable) | **Done**: largest chart 3,243 → 385 rows fetched |
| 4 | Visit detail: fetch only that visit's vitals, at the same time as the rest of the visit | Yes, verified on 40 real visits. Fix: visits with several readings (300) now show every reading, not one arbitrary one | **Done**: ~0.1 s saved per visit opened |
| 5 | Chart header: name/address + primary insurance + MRN in one query (crosswalk in parallel) | Yes, verified on 50 real patients; MRN ties now resolved the same way every time | **Done**: 3 queries → 1 |
| **B. Don't load the same thing twice** | | | |
| 6 | Server-side memory cache per patient: 10 min, max 500 entries, copies per caller, errors never cached (SOURCE_CACHE_TTL_SECONDS / SOURCE_CACHE_MAX_ITEMS; 0 = off) | Yes, verified: repeat loads identical for 8 real patients | **Done**: whole chart repeat 1.5 s → ~1 ms of data loading |
| 7 | Keep already-opened tabs in the open page (memory only, max 10 min, never saved to disk); each re-show still writes an audit row via a CSRF-protected ping; expired session → sign-in page | Yes, verified in headless Chrome (fake data): same content and URL; audit rows complete | **Done**: tab revisit ~0.2 s → ~15 ms, no data request |
| **C. Show something sooner** | | | |
| 8 | Visits / Notes / Documents: show the list first, then fill the detail panel | Yes (same panel, appears a moment later) | To do |
| 9 | Cancel outdated requests when typing in search or clicking tabs quickly | Yes | To do |
| 10 | Preload the next scanned page | Yes | To do |
| **D. Web-server tweaks** | | | |
| 11 | Compress pages (gzip) | Yes | To do |
| 12 | Proper browser caching for CSS / JS / fonts | Yes | To do |
| 13 | Lighter middleware; template auto-reload off in production | Yes | To do |
| **F. Big lists: first part first** | | | |
| 15 | Patient list / labs / visits / documents: fetch the visible page from the database first; fetch everything only for "All", filters, trend or PDF. Speed up the patient-list query (1.2 s today) | Yes | To do |
| **E. Deployment (Phase 11)** | | | |
| 14 | Run the app in AWS next to SQL Server (≈ 1 ms per trip instead of 54 ms) | Yes | Phase 11 |

**Kept on purpose:** the browser's back/forward page cache stays disabled (`Cache-Control: no-store`),
because it would store patient data on disk.
