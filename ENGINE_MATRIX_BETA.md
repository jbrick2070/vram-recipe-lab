# Engine Matrix — LAB BETA

The lab's own living copy of the video engine matrix. Rules:

- **Seeded from** `research/ENGINE_MATRIX_OTR_SNAPSHOT_2026-08-07.md` — a dated,
  frozen snapshot of OTR's generated `docs/ENGINE_MATRIX.md`. Never edit the
  snapshot; never write anything back to the OTR repo. This beta graduates into
  OTR only by hand, by Jeffrey or a Claude session.
- This file ADDS what the canonical matrix lacks: **measured numbers from this
  box.** The snapshot's windows and contracts are declarations; the columns
  below are receipts.
- One row per engine/recipe variant the lab has touched. Update the row after
  every gated run. An engine nobody has measured yet simply has no row — do not
  pre-fill rows with guesses.
- New engines under evaluation (e.g. `minimax_h3`) live here FIRST, marked
  `beta`, and exist nowhere in OTR until measurements justify promotion.

| engine / recipe | tier | status | peak VRAM smoke (GB) | peak VRAM suite (GB) | VRAM creep? | wall clock / clip | boot lane | last measured | notes |
|---|---|---|---|---|---|---|---|---|---|

Columns: `tier` = smoke / suite. `status` = PASS / FAIL / BLOCKED / beta.
`VRAM creep?` = yes/no from the suite's per-clip series (yes = FAIL).
`boot lane` = normal or sage-free. Dates absolute (YYYY-MM-DD).
