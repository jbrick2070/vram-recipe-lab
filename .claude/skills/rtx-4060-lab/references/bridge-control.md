# Healthy bridge control

Read this only after the approved local health endpoint answers HTTP 200:

```text
5080 127.0.0.1:18765 -> SSH -> 4060 127.0.0.1:8766
```

It is a control-plane check, not permission to boot ComfyUI or render.

## Confirm the full route

1. Check `http://127.0.0.1:18765/readyz` from the 5080.
2. Authenticate one local WebSocket session to `ws://127.0.0.1:18765` with
   the app-server `initialize` handshake before relying on the bridge for a
   bench task.
3. Run one bounded read-only command in the known 4060 checkout: report branch,
   short status, current commit, and whether port 18299 has a listener.
4. Treat a clean `main` checkout with no port-18299 listener as the only
   starting point for the execution ladder.

Never substitute the Ethernet address, port 8765, a bearer token, SSH password,
or a new listener. Do not expose 8766 beyond loopback.

## Current client behavior

- `codex --remote ws://127.0.0.1:18765` is an interactive TUI route.
- The current CLI rejects `codex exec --remote`; that is a client limitation,
  not a tunnel failure. Use the local app-server JSON-RPC client only if a
  headless controller is genuinely needed.
- Keep the protocol narrow: `initialize`, `initialized`, then only a bounded
  read-only inspection or an allowed runner command. Capture the command,
  exit code, and summarized outcome.

## Windows sandbox and Git

An explicit Windows `workspaceWrite` sandbox override can deny Git metadata
writes such as `.git/FETCH_HEAD`, even when the bridge itself is healthy.
Do not escalate to arbitrary full access to work around that error.

If the remote app-server's configured policy can read the known clean checkout,
the only permitted update is:

```powershell
git pull --rebase origin main
```

Then require a clean status and stop on any conflict. Never reset, force-push,
discard an edit, or use a broad stash. Do not diagnose broad process state with
WMI/CIM: an unprivileged controller may get access denied. The isolated runner's
port ownership and immutable receipts remain the source of truth.

## Controller discipline

- Allow one mutating controller at a time.
- Use `gpt-5.3-codex-spark` for bounded remote tasks where an agent is needed.
- Mutate the bench only through `eightgb_bench/runner_4060.py` after the
  execution ladder's static checks, private-config staging, preflight, and
  admission review.
- Report only safe summaries. Keep raw GPU UUIDs, absolute laptop paths,
  profiles, tokens, keys, logs, and ignored receipts out of chat and Git.
