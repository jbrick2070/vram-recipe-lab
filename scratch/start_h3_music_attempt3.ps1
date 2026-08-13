param(
    [switch]$Run
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$LabRoot = "C:\Users\jeffr\Documents\ComfyUI\vram-recipe-lab"
$Python = "C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe"
$Campaign = Join-Path $LabRoot "scratch\run_h3_unconditioned_music_campaign.py"
$Recorder = Join-Path $LabRoot "scratch\record_h3_music_operator_launch.py"
$AttemptId = "h3music-20260810T023023Z-97ca44b2-attempt-003"
$OperatorRoot = Join-Path $LabRoot "results\h3_unconditioned_music_campaign\operator_logs"
$AttemptDirectory = Join-Path $OperatorRoot $AttemptId
$StdoutLog = Join-Path $AttemptDirectory "stdout.log"
$StderrLog = Join-Path $AttemptDirectory "stderr.log"
$LaunchReceipt = Join-Path $AttemptDirectory "launch.json"

$CampaignArguments = @(
    "-u",
    $Campaign,
    "--run",
    "--resume-attempt-002",
    "--campaign-id",
    $AttemptId,
    "--operator-stdout-log",
    $StdoutLog,
    "--operator-stderr-log",
    $StderrLog
)

$Plan = [ordered]@{
    schema_version = 1
    authority = "operator transport only"
    default_read_only = $true
    attempt_id = $AttemptId
    working_directory = $LabRoot
    executable = $Python
    argv = @($Python) + $CampaignArguments
    attempt_directory = $AttemptDirectory
    stdout_log = $StdoutLog
    stderr_log = $StderrLog
    launch_receipt = $LaunchReceipt
    campaign_exit_source = "System.Diagnostics.Process.ExitCode after Start-Process -Wait -PassThru"
}

if (-not $Run) {
    $Plan | ConvertTo-Json -Depth 6
    exit 0
}

foreach ($RequiredFile in @($Python, $Campaign, $Recorder)) {
    $Item = Get-Item -LiteralPath $RequiredFile -Force -ErrorAction Stop
    if (-not $Item.PSIsContainer -and -not ($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        continue
    }
    throw "Required launch file is not a real regular file: $RequiredFile"
}

$CampaignResults = Split-Path -Parent $OperatorRoot
$CampaignResultsItem = Get-Item -LiteralPath $CampaignResults -Force -ErrorAction Stop
if (-not $CampaignResultsItem.PSIsContainer -or ($CampaignResultsItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
    throw "Campaign results root is not a real directory: $CampaignResults"
}

if (-not (Test-Path -LiteralPath $OperatorRoot)) {
    $null = New-Item -ItemType Directory -Path $OperatorRoot -ErrorAction Stop
}
$OperatorRootItem = Get-Item -LiteralPath $OperatorRoot -Force -ErrorAction Stop
if (-not $OperatorRootItem.PSIsContainer -or ($OperatorRootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
    throw "Operator-log root is not a real directory: $OperatorRoot"
}

# New-Item without -Force is the attempt's atomic claim.  Any collision consumes
# this attempt id and fails closed; this script never removes or reuses it.
if (Test-Path -LiteralPath $AttemptDirectory) {
    throw "Attempt directory already exists; refusing reuse: $AttemptDirectory"
}
$AttemptDirectoryItem = New-Item -ItemType Directory -Path $AttemptDirectory -ErrorAction Stop
if (-not $AttemptDirectoryItem.PSIsContainer -or ($AttemptDirectoryItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
    throw "Claimed attempt path is not a real directory: $AttemptDirectory"
}
if (@(Get-ChildItem -LiteralPath $AttemptDirectory -Force).Count -ne 0) {
    throw "Claimed attempt directory is not empty: $AttemptDirectory"
}
foreach ($Target in @($StdoutLog, $StderrLog, $LaunchReceipt)) {
    if (Test-Path -LiteralPath $Target) {
        throw "Attempt transport target already exists: $Target"
    }
}

$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# Both streams go directly to distinct regular files.  No pipeline, Tee, or
# inherited Codex/terminal pipe is part of the campaign transport.
$CampaignProcess = Start-Process `
    -FilePath $Python `
    -ArgumentList $CampaignArguments `
    -WorkingDirectory $LabRoot `
    -RedirectStandardOutput $StdoutLog `
    -RedirectStandardError $StderrLog `
    -WindowStyle Hidden `
    -Wait `
    -PassThru
$CampaignProcess.Refresh()
$CampaignExitCode = $CampaignProcess.ExitCode
$CampaignStartedAtUtc = $CampaignProcess.StartTime.ToUniversalTime().ToString("o")
$CampaignEndedAtUtc = $CampaignProcess.ExitTime.ToUniversalTime().ToString("o")

foreach ($Target in @($StdoutLog, $StderrLog)) {
    $Item = Get-Item -LiteralPath $Target -Force -ErrorAction Stop
    if ($Item.PSIsContainer -or ($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw "Campaign transport log is not a real regular file: $Target"
    }
}

$RecorderArguments = @(
    $Recorder,
    "--write",
    "--quiet",
    "--pid",
    [string]$CampaignProcess.Id,
    "--started-at-utc",
    $CampaignStartedAtUtc,
    "--ended-at-utc",
    $CampaignEndedAtUtc,
    "--exit-code",
    [string]$CampaignExitCode,
    "--cwd",
    $LabRoot,
    "--stdout-log",
    $StdoutLog,
    "--stderr-log",
    $StderrLog
)
$RecorderProcess = Start-Process `
    -FilePath $Python `
    -ArgumentList $RecorderArguments `
    -WorkingDirectory $LabRoot `
    -WindowStyle Hidden `
    -Wait `
    -PassThru
$RecorderProcess.Refresh()
if ($RecorderProcess.ExitCode -ne 0) {
    throw "Operator launch receipt recorder exited $($RecorderProcess.ExitCode)"
}
if (-not (Test-Path -LiteralPath $LaunchReceipt -PathType Leaf)) {
    throw "Operator launch receipt was not published: $LaunchReceipt"
}
if ($CampaignExitCode -ne 0) {
    throw "Attempt-003 exited $CampaignExitCode; immutable transport evidence was retained"
}

[ordered]@{
    status = "RECORDED"
    attempt_id = $AttemptId
    pid = $CampaignProcess.Id
    exit_code = $CampaignExitCode
    stdout_log = $StdoutLog
    stderr_log = $StderrLog
    launch_receipt = $LaunchReceipt
} | ConvertTo-Json -Depth 4
