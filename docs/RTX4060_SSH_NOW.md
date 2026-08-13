# RTX 4060: SSH bridge only — current task

This replaces every earlier 4060 preflight, hardware-inventory, ComfyUI, model,
and render instruction for the moment.

## Authorization and limits

The user explicitly authorizes installation of the built-in Windows **OpenSSH
Server** capability if it is missing. That is the only installation allowed.

Do not install or download anything else. Do not run `preflight_4060.py`,
ComfyUI, a model, a benchmark, or a render. Do not touch OTR or the 5080
checkout.

## Do this now

1. From the 4060 lab checkout, fast-forward to the commit named by the 5080:

   ```powershell
   git pull --ff-only origin main
   ```

   If it fails because of local changes, stop and report `git status --short`.
   Do not reset, clean, force-push, or discard anything.

2. Open an **Administrator PowerShell** on the 4060 and follow every step in
   [RTX4060_CODEX_BRIDGE.md](RTX4060_CODEX_BRIDGE.md), in order.

   That document handles exactly these steps:

   - install/check OpenSSH Server only if missing;
   - create missing SSH host keys;
   - permit SSH only from `10.55.0.1` to `10.55.0.2`;
   - restrict the 5080 key to a port-forward only, with no shell; and
   - start a loopback-only Codex app-server on `127.0.0.1:8766`.

3. Stop after the document's requested report. Return only:

   - whether `sshd` is running;
   - the 4060 SSH host-key `SHA256:` fingerprint;
   - whether port 8766 is ready on **loopback only**; and
   - confirmation that no ComfyUI/model/preflight action occurred.

Never paste any private key, bearer token, or password into Git or chat.
