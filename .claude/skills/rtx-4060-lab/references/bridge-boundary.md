# Bridge Boundary

The user-authorized local control plane is an SSH forward:

```text
5080 127.0.0.1:18765 -> 4060 127.0.0.1:8766
```

Check it read-only before delegation:

```powershell
Invoke-WebRequest http://127.0.0.1:18765/readyz -UseBasicParsing
```

Use the local Codex CLI with `--remote ws://127.0.0.1:18765` only when ready.
Never connect directly to `10.55.0.2`, port 8765, a bearer token, or an SSH
password. Do not install SSH, alter a firewall, replace keys, or create a new
listener as part of a bench task.

The restricted SSH key provides transport only; the authenticated app-server
is still powerful. Allow a single mutating controller at a time. Read-only
diagnosis may be parallel, but server admission and renders must acquire the
4060-local coordinator and GPU leases.

Do not put private keys, app-server tokens, host private keys, raw GPU UUIDs,
absolute laptop paths, private profiles, model paths, logs, outputs, or ignored
receipts in Git or a chat handoff.

For a remote coding task, request a bounded report containing the exact command,
outcome, changed/examined paths, tests, receipt paths/hashes, whether ComfyUI
started, and the shutdown result. A remote agent must stop rather than attempt
unapproved recovery.
