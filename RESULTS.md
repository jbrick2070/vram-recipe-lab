# Results Ledger

Human-readable ledger table tracking the status of every recipe variant in the lab.

| recipe | status | peak VRAM (GB) | notes |
|---|---|---|---|
| t2i_low | FAIL | 0.00 | Aborted on Preflight #2 (GPU idle): GPU allocated VRAM is 1723.0 MB (limit < 1536 MB) |
| t2i_high | PASS | 1.64 | Run #3; boot lane: lab-8199, sage-free |
| h3_t2v_low | BLOCKED | 0.00 | Dry prep complete; weights not on disk (42.5 GB) |
| h3_t2v_high | BLOCKED | 0.00 | Dry prep complete; weights not on disk (42.5 GB) |
