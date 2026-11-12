# 0007: Trusted sources and licences

- **Status:** Accepted (2026-11-12)
- **In plain words:** a card's receipt must come from one of three kinds of source: an official guideline, a review in a major journal, or (only for claims about that study) the study's own paper. Blogs, news, company sites, preprints and the primer never count. We commit each source's record and short quotes, never the document itself.

## Context
ADR 0004 says every card carries a receipt from a trusted source; M1 used one (the 2023 hallmarks review in *Cell*). M2 Step 5 sends agents to find sources for 59 topics, so "trusted" must be defined in a way a script can check (the `source_vetter` block, Step 4). Longevity is full of confident claims from sellers, so the bar must exclude them.

## Decision
**Three tiers.** A source must fit one; its record says which.

| Tier | What | Examples | Use it for |
|---|---|---|---|
| **A: guideline** | Guidance, fact sheets or consensus statements from a named public or professional body | NIH (incl. NIA, Office of Dietary Supplements), CDC, FDA, WHO, NHS, NICE, Cochrane reviews, USPSTF, AASM, Endocrine Society, ACC/AHA, Menopause Society | Anything in its scope: what something is, how sure we are, the catch |
| **B: review** | A review article in a peer-reviewed journal from a major publisher | *Cell*, *Nature* / *Nature Aging* / *Nature Medicine*, *Science*, *Lancet*, *NEJM*, *JAMA*, *BMJ*, *Annual Reviews*, *Aging Cell* | Mechanisms and the overall state of the evidence |
| **C: the study itself** | The paper (or official registration) of one trial or study | the ITP mouse papers, PEARL, VITAL, SELECT, TAME's registration | **Only** claims about that study: what it tested, in whom, what it found |

**Never a source:** news and magazines, blogs, podcasts, company or clinic websites, press releases, preprints (not yet peer-reviewed), Wikipedia, AI answers, and the primer itself (the syllabus, ADR 0004).

**Rules that go with the tiers:**
- **Pinned** (as in M1): URL, size, SHA-256, retrieved date and a local path; the vetter checks it.
- **Population named:** a claim about how sure we are names who it was shown in (mice, healthy people, patients), as `docs/LEARNING_GOALS.md` requires. A tier C mouse paper can never back a human claim.
- **When tiers disagree, the higher tier wins**, and the card says so (e.g. "promising in mice; no benefit shown in people").
- **Paywalled or download-blocked sources are skipped:** we can only pin and quote-check what we can download.
- **Dated facts** (the `after-m5` topics) need a source whose date we record; they wait for M5.

**Licences:**
- **Commit the record and short quotes only** (a quote is a sentence or two, enough to prove the answer). Never commit the document: it downloads to `data/raw/` (gitignored), verified by SHA-256. This is the same rule for every tier, so there is one rule to check, even where a document is public domain (US government) or openly licensed.
- The record keeps a one-line licence note (e.g. "US government work, public domain", "CC BY 4.0", "© publisher; repository copy").

## Why / alternatives considered
- **Only tier A:** safest, but guidelines rarely explain mechanisms (how mTOR works), which is half of what the user wants to learn.
- **Any peer-reviewed paper:** single studies contradict each other; one mouse paper becomes "X extends life". Tier C limits a study to claims about itself.
- **Commit open-licence documents:** possible for some, but two rules are easier to get wrong than one, and the SHA-256 pin already makes the download reproducible.

## Consequences
- ✅ A script can check a source: its tier, its publisher on the list, its pin, its licence note (Step 4, `source_vetter`).
- ✅ Agents in Step 5 get a clear brief of what to look for and what to reject.
- ⚠️ Some topics may have no free tier A/B source (paywalls); they are marked "no trusted source yet" in the topic map, not filled with weaker sources.
- ⚠️ The publisher list will grow; adding a publisher is a PR to the vetter's list, with a reason.
