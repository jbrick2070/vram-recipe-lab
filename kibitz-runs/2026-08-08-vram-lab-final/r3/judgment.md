# R3 Driver Judgment

Antigravity completed on `gemini-3.6-flash-low`; Claude remained unavailable
from the previously confirmed expired OAuth token. Every claim below was checked
against the current files.

## Accepted

- CONFIRMED `[P7]`: nonce + owner create-time are required, already present in
  the driver anchor. Direct-parent and one-coordinator checks remain mandatory.
- CONFIRMED `[P5]`: source-delivery preview verification needs an elementary
  video stream hash. This belongs in the separate mux helper/receipt, not inside
  the diagnostic render's gate.
- CONFIRMED `[P7]`: pre-child settled median and post-minus-pre delta improve
  interpretation of retained model memory and were added to the plan.
- CONFIRMED `[P8]`: the generic media gate does not yet enforce a mode-specific
  target-duration contract. The exact timing fields and one-frame tolerance are
  now explicit implementation requirements.
- CONFIRMED IN PART `[P7]`: shutdown must be bounded and cannot prevent receipt
  evidence. However, final PASS must be written after cleanup result is known,
  while the coordinator is still held—not before shutdown as proposed.
- CONFIRMED `[P5]`: runtime gain/normalization nodes must not be added; the four
  graph identities already use frozen matched bytes.

## Rejected

- MISREAD `[P7]`: the current evaluator already compares S1, S2 and S3 against
  S0 for peak, net peak and settled median. Only its extra final-vs-first
  “monotonic” message is redundant and should be removed.
- REJECTED `[P7]`: hardcoded ComfyUI/model roots are deliberate, documented
  workstation invariants in this local lab. Making them portable is unrelated
  scope.
- MISREAD `[P7]`: `LAB_SUITE_OWNER_PID` need not be passed to the ComfyUI boot
  command; it authorizes the direct `run_recipe` child, not the server process.

## Verify at build

- FFmpeg streamhash syntax and equality on a real remuxed artifact.
- Mini Mime ffprobe duration fields on the 90-frame output.
- Bounded shutdown result survives both success and refusal tests.
