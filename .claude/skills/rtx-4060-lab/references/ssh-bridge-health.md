# SSH bridge health and recovery

Use this only when the 4060 bridge reports unhealthy. Stop any planned ComfyUI
admission or render first: an unhealthy control plane is not a GPU or model
failure.

## Fixed boundary

The only approved route is:

```text
5080 127.0.0.1:18765 -> SSH -> 4060 127.0.0.1:8766
```

Never substitute the Ethernet address, port 8765, a bearer token, password,
new firewall rule, or a public listener. Never run a ComfyUI command as a
bridge recovery workaround.

## Diagnose in order

1. On the 4060, check only the local app-server readiness endpoint:

   ```powershell
   Invoke-WebRequest http://127.0.0.1:8766/readyz -UseBasicParsing
   Get-NetTCPConnection -State Listen -LocalPort 8766 -ErrorAction SilentlyContinue
   ```

   A healthy 4060 app-server answers HTTP 200 and listens only on loopback.
   If it is down, stop and report that fact to the bridge owner. Do not start
   ComfyUI, download anything, or expose port 8766.

2. On the 5080, check only the local forwarded endpoint:

   ```powershell
   Invoke-WebRequest http://127.0.0.1:18765/readyz -UseBasicParsing
   Get-NetTCPConnection -State Listen -LocalPort 18765 -ErrorAction SilentlyContinue
   ```

   If 8766 is healthy but 18765 is absent or unhealthy, the approved SSH
   forward is missing or has exited. Report that exact split; do not connect
   directly to the 4060 and do not recreate SSH keys, firewall rules, or an
   alternate listener during a bench task.

3. If both checks are healthy, use only the local Codex route:

   ```text
   ws://127.0.0.1:18765
   ```

   Allow one mutating controller at a time. Before any remote mutation, require
   a clean checkout and stop on a Git conflict or unexpected local edit.

## Escalation boundary

The one-time secure SSH/app-server setup is documented in
[RTX4060_CODEX_BRIDGE.md](../../../../docs/RTX4060_CODEX_BRIDGE.md). Use it only
with explicit owner authorization for bridge maintenance. Keep host keys,
private keys, tokens, raw GPU UUIDs, absolute paths, and ignored local receipts
out of Git and chat.

Return a compact report: which endpoint failed, whether 8766 is loopback-only,
whether 18765 has a local listener, and confirmation that no ComfyUI/model/
render action occurred.
