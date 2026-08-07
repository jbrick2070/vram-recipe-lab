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
| `t2i_low` | smoke | PASS | 11.64 | N/A | no | 7.7s | lab-8199, sage-free | 2026-08-07 | Measured on box (PASS) |
| `t2i_high` | smoke | PASS | 13.12 | N/A | no | 6.7s | lab-8199, sage-free | 2026-08-07 | Measured on box (PASS) |
| `ltx_i2v_low` | smoke | FAIL | 10.84 | N/A | no | 7.5s | lab-8199, sage-free | 2026-08-07 | LTXAV embedding shape mismatch |
| `ltx_i2v_high` | smoke | FAIL | 10.51 | N/A | no | 6.1s | lab-8199, sage-free | 2026-08-07 | LTXAV embedding shape mismatch |
| `wan_ti2v_low` | smoke | FAIL | 15.28 | N/A | no | 19.7s | lab-8199, sage-free | 2026-08-07 | Peak 15.28 GB > 14.5 GB gate line |
| `wan_ti2v_high` | smoke | FAIL | 15.34 | N/A | no | 30.0s | lab-8199, sage-free | 2026-08-07 | Peak 15.34 GB > 14.5 GB gate line |
| `ltx_audio_low` | smoke | FAIL | 10.82 | N/A | no | 4.5s | lab-8199, sage-free | 2026-08-07 | LTXAV audio connector shape mismatch |
| `ltx_lipsync_low` | smoke | BLOCKED | N/A | N/A | no | 0.0s | lab-8199, sage-free | 2026-08-07 | Missing HuMo/lip-sync nodes |
| `h3_t2v_low` | smoke | BLOCKED | 0.00 | N/A | no | N/A | lab-8199, sage-free | 2026-08-07 | Dry prep complete; predicted peak 11.20 GB; weights missing (42.5 GB) |
| `h3_t2v_best` | smoke | BLOCKED | 0.00 | N/A | no | N/A | lab-8199, sage-free | 2026-08-07 | Dry prep complete; predicted peak 13.20 GB (incl 1.0 GB LoRA margin); weights missing |
| `h3_i2v_low` | smoke | BLOCKED | 0.00 | N/A | no | N/A | lab-8199, sage-free | 2026-08-07 | Dry prep complete; predicted peak 11.80 GB; weights missing (42.5 GB) |
| `h3_i2v_best` | smoke | BLOCKED | 0.00 | N/A | no | N/A | lab-8199, sage-free | 2026-08-07 | Dry prep complete; predicted peak 13.40 GB (incl 1.0 GB LoRA margin); weights missing |
| `h3_r2v_low` | smoke | BLOCKED | 0.00 | N/A | no | N/A | lab-8199, sage-free | 2026-08-07 | Dry prep complete; predicted peak 12.10 GB; weights missing (42.5 GB) |
| `h3_r2v_best` | smoke | BLOCKED | 0.00 | N/A | no | N/A | lab-8199, sage-free | 2026-08-07 | Dry prep complete; predicted peak 13.50 GB (incl 1.0 GB LoRA margin); weights missing |

Columns: `tier` = smoke / suite. `status` = PASS / FAIL / BLOCKED / beta.
`VRAM creep?` = yes/no from the suite's per-clip series (yes = FAIL).
`boot lane` = normal or sage-free. Dates absolute (YYYY-MM-DD).
