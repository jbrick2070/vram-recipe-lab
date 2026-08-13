param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Canonical", "Followup")]
    [string]$Mission,

    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Za-z0-9_.-]{1,120}$")]
    [string]$CampaignId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Za-z0-9_.-]{1,120}$")]
    [string]$OperatorRunId,

    [switch]$Resume,

    [ValidatePattern("^[A-Za-z0-9_.-]{1,120}$")]
    [string]$ResumeFromCampaignId,

    [switch]$Run
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$LabRoot = "C:\Users\jeffr\Documents\ComfyUI\vram-recipe-lab"
$Python = "C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe"
$Recorder = Join-Path $LabRoot "scratch\record_h3_campaign_operator_transport.py"
$MissionValue = $Mission.ToLowerInvariant()

if ($MissionValue -eq "canonical" -and $Resume) {
    throw "Canonical transport does not accept -Resume"
}
if ($MissionValue -eq "followup" -and -not [string]::IsNullOrEmpty($ResumeFromCampaignId)) {
    throw "Follow-up transport does not accept -ResumeFromCampaignId"
}
if ($MissionValue -eq "canonical" -and $ResumeFromCampaignId -eq $CampaignId) {
    throw "Canonical resume source must differ from CampaignId"
}

foreach ($RequiredFile in @($Python, $Recorder)) {
    $Item = Get-Item -LiteralPath $RequiredFile -Force -ErrorAction Stop
    if ($Item.PSIsContainer -or ($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw "Required transport file is not a real regular file: $RequiredFile"
    }
}
$LabRootItem = Get-Item -LiteralPath $LabRoot -Force -ErrorAction Stop
if (-not $LabRootItem.PSIsContainer -or ($LabRootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
    throw "Lab root is not a real directory: $LabRoot"
}

$RecorderArguments = @(
    "-B",
    $Recorder,
    "--mission",
    $MissionValue,
    "--campaign-id",
    $CampaignId,
    "--operator-run-id",
    $OperatorRunId
)
if ($Resume) {
    $RecorderArguments += "--resume"
}
if (-not [string]::IsNullOrEmpty($ResumeFromCampaignId)) {
    $RecorderArguments += @("--resume-from-campaign-id", $ResumeFromCampaignId)
}

if (-not $Run) {
    & $Python @RecorderArguments --plan
    if ($LASTEXITCODE -ne 0) {
        throw "Read-only operator transport plan failed with exit $LASTEXITCODE"
    }
    exit 0
}

$PrepareRaw = (& $Python @RecorderArguments --prepare | Out-String)
if ($LASTEXITCODE -ne 0) {
    throw "Operator transport prepare failed with exit $LASTEXITCODE"
}
$Prepared = $PrepareRaw | ConvertFrom-Json
if ($Prepared.kind -ne "h3-local-operator-transport-preflight") {
    throw "Recorder returned an unexpected preflight object"
}
$Plan = $Prepared.plan
if ($Plan.executable -ne $Python -or $Plan.working_directory -ne $LabRoot) {
    throw "Recorder launch identity does not match the pinned local transport"
}
if ($Plan.process_contract.api -ne "Windows Start-Process" -or
    -not $Plan.process_contract.wait -or
    $Plan.process_contract.window_style -ne "Hidden") {
    throw "Recorder process contract drifted"
}

$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONDONTWRITEBYTECODE = "1"

$CampaignArguments = [string[]]$Plan.arguments
$CampaignProcess = Start-Process `
    -FilePath $Plan.executable `
    -ArgumentList $CampaignArguments `
    -WorkingDirectory $Plan.working_directory `
    -RedirectStandardOutput $Plan.stdout_log `
    -RedirectStandardError $Plan.stderr_log `
    -WindowStyle Hidden `
    -Wait `
    -PassThru
$CampaignProcess.Refresh()
$CampaignExitCode = $CampaignProcess.ExitCode
$CampaignPid = $CampaignProcess.Id
$CampaignStartedAtUtc = $CampaignProcess.StartTime.ToUniversalTime().ToString("o")
$CampaignEndedAtUtc = $CampaignProcess.ExitTime.ToUniversalTime().ToString("o")

$FinalizeArguments = @(
    $RecorderArguments
    "--finalize"
    "--pid"
    [string]$CampaignPid
    "--started-at-utc"
    $CampaignStartedAtUtc
    "--ended-at-utc"
    $CampaignEndedAtUtc
    "--exit-code"
    [string]$CampaignExitCode
)
$FinalizeRaw = (& $Python @FinalizeArguments | Out-String)
if ($LASTEXITCODE -ne 0) {
    throw "Operator transport finalize failed; preflight and stream bytes were preserved"
}
$Finalized = $FinalizeRaw | ConvertFrom-Json
if ($Finalized.status -ne "RECORDED") {
    throw "Recorder did not publish a completed transport receipt"
}
if (-not (Test-Path -LiteralPath $Plan.launch_receipt -PathType Leaf)) {
    throw "Operator launch receipt was not published: $($Plan.launch_receipt)"
}
if ($CampaignExitCode -ne 0) {
    throw "Campaign exited $CampaignExitCode; immutable local transport evidence was retained"
}

$FinalizeRaw
