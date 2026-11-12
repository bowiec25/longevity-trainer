# What real sources look like (M2 Step 3)

> **In plain words:** before writing the code that checks sources, I saved three real ones by hand, one per tier, to see what goes wrong. These are the findings; the `source_vetter` SPEC (Step 4) and the fan-out brief (Step 5) are built on them.

**Pinned** (records in `data/sources/`, documents in `data/raw/`, gitignored):
| Source | Tier | Format | Size |
|---|---|---|---|
| WHO *Physical activity* fact sheet | A | HTML page | 116 KB |
| *Measuring biological aging in humans: A quest* (Aging Cell, 2020) | B | JATS XML from Europe PMC | 415 KB |
| PEARL trial results (Aging, 2025) | C | JATS XML from Europe PMC | 248 KB |
| *Hallmarks of aging: An expanding universe* (Cell, 2023), from M1 | B | PDF | 5.1 MB |

## Findings
1. **Many official sites block programs.** NIH Office of Dietary Supplements, NIA and CDC refused a downloader that says what it is (403/405). WHO, NHS, Europe PMC and the Spanish repository (M1) allowed it. Pretending to be a browser is not allowed (Claude Code blocks it, rightly), so **blocked sites are skipped**, as ADR 0007 already says for paywalls. Step 5 must check that a source downloads *before* proposing it.
2. **Three formats, not one.** M1 only handled PDF. Now: **PDF** (pages), **HTML** (one long page with menus and scripts around the text), **JATS XML** (the standard format for journal articles, from Europe PMC: no pages, but clean sections). The quote check needs text from all three, and a "page" only exists for PDFs.
3. **Europe PMC is the best road to journal articles.** Its free API (made for programs) gives the full text of open-access articles as XML, plus machine-readable facts: journal, article type (review or research), the DOI and the **licence** (e.g. CC BY 4.0). The vetter can read the licence instead of trusting what someone typed. Its PDF links, by contrast, block programs.
4. **Paywalls are common for top reviews.** The *Nature Aging* mTOR review (2023) has no open full text, so it's skipped. Open-access reviews in *Aging Cell*, *Cell* and others exist for most topics.
5. **Preprint twins.** PEARL also exists as a medRxiv preprint (DOI starting `10.1101/`). Preprints never count (ADR 0007), so the vetter rejects preprint DOIs and servers.
6. **Web pages change.** The WHO page was last modified on 2026-11-04, and two downloads seconds apart matched, but the next update will change its SHA-256. That's what M5's freshness job is for; until then a changed page fails its pin loudly (`DownloadError`), which is the right behaviour.
7. **Journals outside ADR 0007's examples.** PEARL is in *Aging* (Impact Journals) and the review in *Aging Cell* (Wiley): fine under tier C and B rules, but the vetter needs an explicit publisher list, grown by PR with a reason.

## What this changes
- **Step 4** becomes two parts: `source_text` (get plain text from PDF, HTML or JATS XML, so `receipts` can quote-check any format; a "page" for PDFs, a section for the others) and `source_vetter` (tier, publisher list, preprint check, pin, licence).
- **Source records gain fields:** `publisher`, `tier`, `format`, `topics` (and `doi` where there is one). The M1 record was updated to match.
- **Step 5's agents** search Europe PMC first for tiers B and C, and check each URL downloads before proposing it.
