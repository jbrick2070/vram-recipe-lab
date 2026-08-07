# Antigravity Quota Hold

Antigravity failed on quota/credit/rate-limit usage. Suggested retry after 1h (2026-08-07T17:48-07:00).

Kibitz detected provider quota, credit, or rate-limit markers for this lane.
The active driver should acknowledge this to the user and ask when to retry.
If the user does not choose a time, use the suggested retry window above.

To change the built-in retry window, set `KIBITZ_QUOTA_RETRY_AFTER`
(examples: `30m`, `1h`, `4h`, `1d`) before rerunning Kibitz.

## Diagnostic

Antigravity quota/backend exhaustion detected in recent CLI log C:\Users\jeffr\.gemini\antigravity-cli\log\cli-20260807_164307.log:
"status": "RESOURCE_EXHAUSTED"
ERROR: logging before google.Init: W0807 16:46:07.071756     249 cache.go:56] Cache(loadCodeAssistResponse): Singleflight refresh failed: RESOURCE_EXHAUSTED (code 429): Resource has been exhausted (e.g. check quota).
ERROR: logging before google.Init: E0807 16:46:07.071756     249 errorreport.go:223] RESOURCE_EXHAUSTED (code 429): Resource has been exhausted (e.g. check quota).
ERROR: logging before google.Init: E0807 16:46:07.071756     249 credits_manager.go:42] failed to refresh G1 credits: failed to get load code assist response: RESOURCE_EXHAUSTED (code 429): Resource has been exhausted (e.g. check quota).
ERROR: logging before google.Init: E0807 16:46:07.071756    4448 generation.go:726] Failed to record ConversationOffered metrics: failed to get load code assist response: RESOURCE_EXHAUSTED (code 429): Resource has been exhausted (e.g. check quota).
ERROR: logging before google.Init: W0807 16:46:07.071756    4463 cache.go:79] Failed to refresh cache in background: RESOURCE_EXHAUSTED (code 429): Resource has been exhausted (e.g. check quota).
