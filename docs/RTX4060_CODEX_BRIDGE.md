# RTX 4060 Codex bridge: one-time SSH handoff

## Purpose and boundary

This makes the 4060 available to the 5080's Codex terminal without exposing a
Codex app-server on the Ethernet. It is **not** a ComfyUI task: do not download
or install anything, boot ComfyUI, load a model, render, alter the lab runner,
or touch OTR.

The prior Ethernet listener on port 8765 must not be used directly. A token
was shared in chat, so treat it as revoked. Stop its app-server process and
remove/disable its port-8765 firewall rule before doing anything else. The
supported route is an SSH tunnel to a new loopback-only app-server on port 8766.

The only permitted 5080 public key is
[`authorized_5080_ed25519.pub`](../eightgb_bench/bridge/authorized_5080_ed25519.pub).
Its OpenSSH fingerprint is:

```text
SHA256:kFQt5VvqlGBXhV9tXD0/U5r1GHd+8Hyl7ZjvpvlfY0E
```

When installed, the key must be restricted to port-forwarding only, and only to
`127.0.0.1:8766`. It must not get a shell, PTY, agent forwarding, X11, or an
unrestricted forwarding capability. The key itself is additionally bound to the
5080 Ethernet address (`10.55.0.1`), rather than relying on the firewall alone.

## First, update without losing known work

From the 4060 repository root, inspect the checkout before changing it. If the
only local change is the known old preflight edit, preserve it; otherwise stop
and report the status rather than stashing unknown work.

```powershell
$status = @(git status --porcelain=v1)
if ($status.Count -eq 1 -and $status[0] -eq ' M eightgb_bench/preflight_4060.py') {
    git stash push -m 'preserve-old-4060-preflight-before-bridge' -- eightgb_bench/preflight_4060.py
    if ($LASTEXITCODE -ne 0) { throw 'Known preflight edit could not be stashed.' }
    $status = @(git status --porcelain=v1)
}
if ($status.Count -ne 0) { throw 'STOP: checkout has unknown local changes; report git status --short.' }
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw 'STOP: fast-forward pull failed.' }
if (@(git status --porcelain=v1).Count -ne 0) { throw 'STOP: checkout is not clean after pull.' }
```

Do not pop the stash. The checked-in version is the source of truth.

## Guarded existing-install-only SSH setup

Run the following only from an Administrator PowerShell on the 4060. It is
allowed to start and configure an **already installed** OpenSSH Server. If the
server capability or `sshd` service is absent, stop and report it; do not
install it.

1. Retire the exposed app-server. Verify that PID 9956 is the expected old
   Codex app-server before stopping it. Remove or disable only the existing
   `Codex-4060-AppServer-8765` rule; do not broaden it or replace it with a
   generic port-8765 rule. Confirm that `10.55.0.2:8765` no longer listens.

   ```powershell
   $old = Get-CimInstance Win32_Process -Filter 'ProcessId = 9956' -ErrorAction Stop
   if ($old.Name -notmatch '^codex(\.exe)?$' -or $old.CommandLine -notmatch 'app-server') {
     throw 'STOP: PID 9956 is not the expected Codex app-server.'
   }
   Stop-Process -Id 9956 -ErrorAction Stop
   Get-NetFirewallRule -Name 'Codex-4060-AppServer-8765' -ErrorAction Stop |
     Remove-NetFirewallRule
   if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
     throw 'STOP: port 8765 is still listening; do not kill an unrecognized process.'
   }
   ```

2. Verify the peer addresses and existing SSH service:

   ```powershell
   Get-NetIPAddress -IPAddress 10.55.0.2 -ErrorAction Stop | Format-List IPAddress,InterfaceAlias,AddressState
   Get-Service sshd -ErrorAction SilentlyContinue | Format-List Name,Status,StartType
   ```

   The service must exist. Confirm the Ethernet network is Private before
   creating the firewall rule. Do not expose port 22 to any other address.

   If the installed OpenSSH Server has no ED25519 host public key yet, generate
   only the missing default host keys. This is necessary for the 4060 to prove
   its SSH identity; it is not an OpenSSH installation and it does not download
   anything. `-A` preserves existing host keys rather than replacing them:

   ```powershell
   $sshKeygen = "$env:WINDIR\System32\OpenSSH\ssh-keygen.exe"
   $ed25519HostPublicKey = Join-Path $env:ProgramData 'ssh\ssh_host_ed25519_key.pub'
   if (-not (Test-Path -LiteralPath $ed25519HostPublicKey)) {
     & $sshKeygen -A
     if ($LASTEXITCODE -ne 0) { throw 'STOP: OpenSSH host-key generation failed.' }
   }
   if (-not (Test-Path -LiteralPath $ed25519HostPublicKey)) {
     throw 'STOP: ED25519 host public key is still absent after generation.'
   }
   & $sshKeygen -lf $ed25519HostPublicKey -E sha256
   ```

   Record the printed `SHA256:` fingerprint for the 5080. Never put the host
   private keys or any app-server token into Git or chat.

3. Resolve the current user's effective `AuthorizedKeysFile` from the existing
   `sshd` configuration. The normal-user path is `%USERPROFILE%\.ssh\authorized_keys`;
   administrator accounts can instead use the protected ProgramData file. Do
   not guess and do not overwrite an existing key file or its ACL.

   Read the current configuration and use `sshd -T -C` for the actual account.
   For example, with the actual Windows account substituted explicitly:

   ```powershell
   & "$env:WINDIR\System32\OpenSSH\sshd.exe" -T -C 'user=<actual-4060-account>,host=10.55.0.2,addr=10.55.0.1' |
     Select-String -Pattern '^authorizedkeysfile '
   ```

   If the effective key path cannot be established unambiguously, stop and
   report it. Append exactly one line, if it is not already present:

   ```text
   from="10.55.0.1",restrict,port-forwarding,permitopen="127.0.0.1:8766",command="cmd.exe /c exit 1" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEr4mG1bxvEsbLM8A/ShGV2sPpIvqX7d6UyGpeCp0APr codex-4060-app-server-tunnel
   ```

   Preserve the owner and permissions required by the existing OpenSSH
   configuration. This forced command makes an ordinary shell or remote-command
   request exit immediately; an `ssh -N -L ...` tunnel does not create such a
   session and remains permitted.

   Add a narrow block at the end of the existing `sshd_config` for the actual
   local account that owns this key. Do not change global password settings or
   add a broad `Match all` block:

   ```text
   Match User <actual-4060-account> Address 10.55.0.1
       PasswordAuthentication no
       KbdInteractiveAuthentication no
       PubkeyAuthentication yes
       AuthenticationMethods publickey
       AllowTcpForwarding local
       GatewayPorts no
       PermitOpen 127.0.0.1:8766
       PermitTTY no
       X11Forwarding no
       AllowAgentForwarding no
   ```

   Validate the configuration before restarting the service:

   ```powershell
   & "$env:WINDIR\System32\OpenSSH\sshd.exe" -t
   ```

   If validation fails, undo only the new bridge block and stop to report the
   validation error. Do not restart an invalid SSH service.

4. Start `sshd` and add precisely this Private-profile firewall allowance:

   ```powershell
   Set-Service -Name sshd -StartupType Manual
   if ((Get-Service -Name sshd).Status -eq 'Running') {
     Restart-Service -Name sshd
   } else {
     Start-Service -Name sshd
   }
   New-NetFirewallRule `
     -Name 'Codex4060-SshFrom5080' `
     -DisplayName 'Codex 4060 SSH tunnel from 5080 only' `
     -Direction Inbound -Action Allow -Protocol TCP `
     -LocalAddress 10.55.0.2 -RemoteAddress 10.55.0.1 `
     -LocalPort 22 -Profile Private
   ```

   If a rule with that name already exists, inspect it and correct it only when
   it is scoped exactly as above. Do not make a broad port-22 rule.

## Add a safe second app-server; do not cut over yet

Start a new app-server bound **only** to loopback on port 8766. Use the already
installed Codex CLI; do not install or update it.

```powershell
codex app-server --listen ws://127.0.0.1:8766
```

It may be launched as a separate background process, but record its PID locally
under `eightgb_bench/local/` only. Confirm from the 4060 that
`http://127.0.0.1:8766/readyz` returns HTTP 200. Do not create a firewall rule
for 8766.

## Stop point and report

At this point, stop and report only:

- whether `sshd` was already installed and is running;
- that the firewall rule is exact (never paste keys or tokens);
- that the loopback-only 8766 readiness check passed; and
- the OpenSSH host-key fingerprint for the 4060, so the 5080 can verify it.

Also prove the restricted key behavior from the 5080 only after the 5080 has
received the host-key fingerprint out of band: an ordinary `ssh ... exit` must
fail, while an `ssh -N -L ...` connection may stay open. Do not test this with
an arbitrary remote command.

The 5080 will next prove the SSH tunnel. Do not create any rule for port 8766,
and do not restore the old port-8765 listener.
