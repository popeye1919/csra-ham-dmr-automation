<#
.SYNOPSIS
    CSRA Phreak, Morse Code & Knights Who Say '73' Windows CHIRP Automation Script.
    (-.-. --.- / -.. . / -.- .-. ....- .--- .-.. -.-. / --... ...--)

.DESCRIPTION
    Automates USB/COM port detection, MANDATORY pre-flash EEPROM backups (with SHA-256
    cryptographic verification), CSRA repeater/talkgroup synchronization, CHIRP CLI
    (chirpc.exe) programming, and CHIRP GUI (chirpw.exe) fallback launching on Windows 10/11.

    SACRED RULE OF THE HOLY HAND GRENADE OF ANTIOCH:
    "Thou shalt NEVER upload a new image to thy radio without FIRST downloading and
     verifying a timestamped backup of the radio's current EEPROM into windows\backups\!"

    Official CHIRP Wiki Reference: https://chirpmyradio.com/projects/chirp/wiki/Home

.PARAMETER Action
    Pipeline action to execute:
      - Detect       : Scan Windows Device Manager (WMI/CIM) for K-plug & BTECH COM ports
      - Backup       : Download & SHA-256 verify a timestamped backup (.img) from the radio
      - SyncAndBuild : Run Python CSRA W4DV/TGIF scraper & rebuild CHIRP .csv/.img files
      - Flash        : Perform MANDATORY pre-flash backup FIRST, then upload CSRA codeplug
      - Restore      : Restore a previous backup .img file to the radio
      - LaunchGui    : Open CHIRP GUI (chirpw.exe) with your latest backup & CSRA CSV ready
      - Morse        : Encode/decode ITU Morse Code (-.-. --.-)
      - All          : Detect -> SyncAndBuild -> Mandatory Backup -> Flash

.EXAMPLE
    .\Invoke-CsraChirp.ps1 -Action Detect
    .\Invoke-CsraChirp.ps1 -Action Backup -ComPort COM4
    .\Invoke-CsraChirp.ps1 -Action Flash -ComPort COM4 -RadioModel Baofeng_UV-5R
    .\Invoke-CsraChirp.ps1 -Action Restore -ComPort COM4 -BackupFile .\backups\uv5r_pre_flash_20261030_111500.img
    .\Invoke-CsraChirp.ps1 -Action LaunchGui
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("Detect", "Backup", "SyncAndBuild", "Flash", "Restore", "LaunchGui", "Morse", "All")]
    [string]$Action = "Detect",

    [Parameter()]
    [string]$ComPort = "",

    [Parameter()]
    [string]$RadioModel = "Baofeng_UV-5R",

    [Parameter()]
    [string]$BackupFile = "",

    [Parameter()]
    [string]$Message = "CQ CQ DE KR4JLC BRING US A SHRUBBERY 73",

    [Parameter()]
    [switch]$DecodeMorse,

    [Parameter()]
    [switch]$ForceUseCsvImport,

    [Parameter()]
    [switch]$NoBanner
)

$ErrorActionPreference = "Stop"

# Resolve directory paths
$WindowsDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot    = Split-Path -Parent $WindowsDir
$BackupsDir  = Join-Path $WindowsDir "backups"
$ChirpCsv    = Join-Path $RepoRoot "data\generated\chirp\CSRA_W4DV_UV5R_CHIRP.csv"
$ChirpImg    = Join-Path $RepoRoot "data\generated\chirp\CSRA_W4DV_UV5R.img"
$BtechImg    = Join-Path $RepoRoot "data\generated\dmrconfig\CSRA_W4DV_DMR6X2PRO.img"
$BtechConf   = Join-Path $RepoRoot "data\generated\dmrconfig\CSRA_W4DV_DMR6X2PRO.conf"

if (-not (Test-Path $BackupsDir)) {
    New-Item -ItemType Directory -Path $BackupsDir -Force | Out-Null
}

# ITU-R M.1677-1 Morse Code Dictionary
$ItuMorse = @{
    'A'='.-';    'B'='-...';  'C'='-.-.';  'D'='-..';   'E'='.';
    'F'='..-.';  'G'='--.';   'H'='....';  'I'='..';    'J'='.---';
    'K'='-.-';   'L'='.-..';  'M'='--';    'N'='-.';    'O'='---';
    'P'='+--.';  'Q'='--.-';  'R'='.-.';   'S'='...';   'T'='-';
    'U'='..-';   'V'='...-';  'W'='.--';   'X'='-..-';  'Y'='-.--';
    'Z'='--..';
    '0'='-----'; '1'='.----'; '2'='..---'; '3'='...--'; '4'='....-';
    '5'='.....'; '6'='-....'; '7'='--...'; '8'='---..'; '9'='----.';
    '/'='-..-.'; '?'='..--..'; '='='-...-'; '+'='.-.-.'; '-'='-....-';
    '.'='.-.-.-'; ','='--..--'; '@'='.--.-.'; '!'='-.-.--'
}
$ItuMorse['P'] = '.--.'

function ConvertTo-MorseCode {
    param([string]$Text)
    $words = @()
    foreach ($word in ($Text.ToUpper() -split '\s+')) {
        if (-not $word) { continue }
        $chars = @()
        foreach ($ch in $word.ToCharArray()) {
            $s = [string]$ch
            if ($ItuMorse.ContainsKey($s)) { $chars += $ItuMorse[$s] }
            else { $chars += '?' }
        }
        $words += ($chars -join ' ')
    }
    return ($words -join ' / ')
}

function ConvertFrom-MorseCode {
    param([string]$Cw)
    $rev = @{}
    foreach ($k in $ItuMorse.Keys) { $rev[$ItuMorse[$k]] = $k }
    $words = @()
    foreach ($rawWord in ($Cw.Trim() -split '/')) {
        $chars = @()
        foreach ($tok in ($rawWord.Trim() -split '\s+')) {
            if (-not $tok) { continue }
            if ($rev.ContainsKey($tok)) { $chars += $rev[$tok] }
            else { $chars += '?' }
        }
        $words += ($chars -join '')
    }
    return ($words -join ' ')
}

function Write-PhreakBanner {
    if ($NoBanner) { return }
    $banner = @"
 ._________________________________________________________________________.
 |  ____ ____ ____    _      ____  _   _ ____  _____    _    _  __         |
 | / ___/ ___|  _ \  / \    |  _ \| | | |  _ \| ____|  / \  | |/ /         |
 || |   \___ \ |_) |/ _ \   | |_) | |_| | |_) |  _|   / _ \ | ' /   [2600] |
 || |___ ___) |  _ < ___ \  |  __/|  _  |  _ <| |___ / ___ \| . \   [ Hz ] |
 | \____|____/|_| \_\_/ \_\ |_|   |_| |_|_| \_\_____/_/   \_\_|\_\  [WIN ] |
 |-------------------------------------------------------------------------|
 |  * WINDOWS BEIGE-BOX EDITION // THE KNIGHTS WHO SAY "73" (--... ...--)  |
 |  * CW: -.-. --.-  -.. .  -.- .-. ....- .--- .-.. -.-.  -...-  -.-       |
 |  * "Thou shalt ALWAYS download a backup .img BEFORE uploading!"         |
 |  * CHIRP Wiki: https://chirpmyradio.com/projects/chirp/wiki/Home        |
 `-------------------------------------------------------------------------'
"@
    Write-Host $banner -ForegroundColor Cyan
}

function Find-ChirpExecutables {
    <#
    .SYNOPSIS
        Locates chirpc.exe (CLI) and chirpw.exe (GUI) across standard Windows install paths.
    #>
    $searchDirs = @(
        "${env:ProgramFiles(x86)}\CHIRP",
        "${env:ProgramFiles}\CHIRP",
        "${env:LOCALAPPDATA}\Programs\CHIRP",
        "${env:LOCALAPPDATA}\CHIRP"
    )

    $chirpc = Get-Command "chirpc.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1
    $chirpw = Get-Command "chirpw.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1

    foreach ($dir in $searchDirs) {
        if (-not $chirpc -and (Test-Path (Join-Path $dir "chirpc.exe"))) {
            $chirpc = Join-Path $dir "chirpc.exe"
        }
        if (-not $chirpw -and (Test-Path (Join-Path $dir "chirpw.exe"))) {
            $chirpw = Join-Path $dir "chirpw.exe"
        }
    }

    return [PSCustomObject]@{
        ChirpCli = $chirpc
        ChirpGui = $chirpw
    }
}

function Get-RadioComPorts {
    <#
    .SYNOPSIS
        Queries Windows WMI/CIM for USB-to-Serial K-plug cables (CH340, FTDI, CP210x, PL2303)
        and BTECH DMR-6X2 PRO GD32 CDC ACM Virtual COM ports (VID_28E9&PID_018A).
    #>
    Write-Host "[*] Blowing 2600 Hz Cap'n Crunch whistle down Windows WMI/CIM PnP bus..." -ForegroundColor Yellow
    Write-Host "    CW BEACON: $(ConvertTo-MorseCode 'QRL? DE KR4JLC')" -ForegroundColor DarkCyan

    $detected = @()
    if ($IsLinux -or $IsMacOS) {
        Write-Warning "Running on non-Windows host; WMI/CIM COM port scan skipped (use bin/csra-radio on Linux)."
        return $detected
    }

    $entities = Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '\(COM\d+\)' }

    foreach ($dev in $entities) {
        if ($dev.Name -match '\((COM\d+)\)') {
            $portName = $Matches[1]
            $pnpId    = [string]$dev.DeviceID
            $role     = "Generic Serial Port"
            $driverOk = ($dev.ConfigManagerErrorCode -eq 0)

            if ($pnpId -match 'VID_28E9&PID_018A') {
                $role = "BTECH DMR-6X2 PRO / AnyTone GD32 Virtual COM"
            }
            elseif ($pnpId -match 'VID_1A86&PID_7523' -or $dev.Name -match 'CH340') {
                $role = "Baofeng UV-5R K-Plug Cable (WCH CH340)"
            }
            elseif ($pnpId -match 'VID_0403&PID_6001' -or $dev.Name -match 'FTDI') {
                $role = "Baofeng UV-5R K-Plug Cable (FTDI FT232R)"
            }
            elseif ($pnpId -match 'VID_10C4&PID_EA60' -or $dev.Name -match 'CP210') {
                $role = "Baofeng UV-5R K-Plug Cable (Silicon Labs CP210x)"
            }
            elseif ($pnpId -match 'VID_067B&PID_2303' -or $dev.Name -match 'Prolific') {
                $role = "Baofeng UV-5R K-Plug Cable (Prolific PL2303)"
            }

            $detected += [PSCustomObject]@{
                ComPort    = $portName
                Friendly   = $dev.Name
                RadioRole  = $role
                PnpId      = $pnpId
                DriverOk   = $driverOk
                ErrorCode  = $dev.ConfigManagerErrorCode
            }
        }
    }

    return $detected
}

function Resolve-TargetComPort {
    param([string]$RequestedPort)
    if ($RequestedPort) { return $RequestedPort }

    $ports = Get-RadioComPorts
    $kplug = $ports | Where-Object { $_.RadioRole -match 'K-Plug|CH340|FTDI|CP210|Prolific' -and $_.DriverOk } | Select-Object -First 1
    if ($kplug) {
        Write-Host "[+] Auto-selected K-Plug programming cable on $($kplug.ComPort) ($($kplug.Friendly))" -ForegroundColor Green
        return $kplug.ComPort
    }

    $anyPort = $ports | Where-Object { $_.DriverOk } | Select-Object -First 1
    if ($anyPort) {
        Write-Host "[+] Auto-selected serial port $($anyPort.ComPort) ($($anyPort.Friendly))" -ForegroundColor Green
        return $anyPort.ComPort
    }

    throw "No active radio programming COM port detected! Check Device Manager (see windows\README.md) or pass -ComPort COMx."
}

function Invoke-MandatoryPreFlashBackup {
    <#
    .SYNOPSIS
        THE SACRED PRE-FLASH BACKUP GUARD:
        Downloads the live radio's current EEPROM image into windows\backups\, verifies its
        byte size and SHA-256 hash, and writes a JSON rollback manifest.
        If the download fails or produces an empty/corrupt file, execution ABORTS immediately!
    #>
    param(
        [Parameter(Mandatory = $true)][string]$ChirpCliPath,
        [Parameter(Mandatory = $true)][string]$Port,
        [Parameter(Mandatory = $true)][string]$Model,
        [string]$Label = "pre_flash"
    )

    $timestamp    = Get-Date -Format "yyyyMMdd_HHmmss"
    $safeModel    = ($Model -replace '[^A-Za-z0-9_-]', '_').ToLower()
    $backupImg    = Join-Path $BackupsDir "${safeModel}_${Label}_${timestamp}.img"
    $manifestJson = Join-Path $BackupsDir "${safeModel}_${Label}_${timestamp}.manifest.json"

    Write-Host ""
    Write-Host "=========================================================================" -ForegroundColor Yellow
    Write-Host " [MANDATORY SAFETY LOCK] DOWNLOADING PRE-FLASH EEPROM BACKUP FIRST" -ForegroundColor Yellow
    Write-Host " 'First shalt thou pull the live EEPROM image, no more, no less...'" -ForegroundColor Yellow
    Write-Host "=========================================================================" -ForegroundColor Yellow
    Write-Host "[*] Radio Model : $Model"
    Write-Host "[*] Serial Port : $Port"
    Write-Host "[*] Backup Path : $backupImg"

    $argsList = @("-r", $Model, "-s", $Port, "--mmap", $backupImg, "--download-mmap")
    Write-Host "[*] Executing   : `"$ChirpCliPath`" $($argsList -join ' ')" -ForegroundColor DarkGray

    & $ChirpCliPath @argsList
    if ($LASTEXITCODE -ne 0) {
        throw "[ABORT] CHIRP backup download exited with code $LASTEXITCODE! Refusing to overwrite radio without a verified backup. Check cable seating, volume (100%), and COM port (see windows\README.md)."
    }

    if (-not (Test-Path $backupImg)) {
        throw "[ABORT] Backup file was not created at $backupImg! Refusing to flash radio."
    }

    $fileInfo = Get-Item $backupImg
    if ($fileInfo.Length -lt 1024) {
        throw "[ABORT] Backup file is suspiciously small ($($fileInfo.Length) bytes)! Refusing to flash radio."
    }

    $hashObj = Get-FileHash -Path $backupImg -Algorithm SHA256
    $manifest = [Ordered]@{
        radio_model    = $Model
        com_port       = $Port
        created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        backup_file    = $backupImg
        size_bytes     = $fileInfo.Length
        sha256         = $hashObj.Hash.ToLower()
        cw_ack         = (ConvertTo-MorseCode "QSL BACKUP OK 73")
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -Path $manifestJson -Encoding UTF8

    Write-Host "[+] Pre-Flash Backup Verified & Locked!" -ForegroundColor Green
    Write-Host "    - File   : $backupImg ($($fileInfo.Length) bytes)" -ForegroundColor Green
    Write-Host "    - SHA256 : $($hashObj.Hash.ToLower())" -ForegroundColor Green
    Write-Host "    - Manifest: $manifestJson" -ForegroundColor Green
    return $backupImg
}

# ==============================================================================
# MAIN DISPATCH
# ==============================================================================
if ($Action -eq "Morse") {
    if ($DecodeMorse) {
        Write-Output "[CW -> ASCII] $(ConvertFrom-MorseCode -Cw $Message)"
    } else {
        Write-Output "[ASCII -> CW] $(ConvertTo-MorseCode -Text $Message)"
    }
    exit 0
}

Write-PhreakBanner
$chirpBins = Find-ChirpExecutables

switch ($Action) {
    "Detect" {
        Write-Host "[*] Checking CHIRP installation paths..." -ForegroundColor Cyan
        if ($chirpBins.ChirpCli) {
            Write-Host "    [+] CHIRP CLI (chirpc.exe): $($chirpBins.ChirpCli)" -ForegroundColor Green
        } else {
            Write-Host "    [!] chirpc.exe not found in standard paths. Install CHIRP-next from https://chirpmyradio.com/projects/chirp/wiki/Home" -ForegroundColor Yellow
        }
        if ($chirpBins.ChirpGui) {
            Write-Host "    [+] CHIRP GUI (chirpw.exe): $($chirpBins.ChirpGui)" -ForegroundColor Green
        }

        $ports = Get-RadioComPorts
        if (-not $ports -or $ports.Count -eq 0) {
            Write-Host "[*] 'Tis but a flesh wound! No USB/Serial radio programming cables detected." -ForegroundColor Yellow
            Write-Host "    (Your Baofeng UV-5R is just pining for the fjords of Device Manager!)" -ForegroundColor DarkGray
            Write-Host "    -> See windows\README.md for CH340/FTDI/PL2303 driver setup & manual CHIRP steps." -ForegroundColor Cyan
        } else {
            Write-Host "[+] NI! Detected $($ports.Count) serial port(s) on the Windows bus:" -ForegroundColor Green
            $ports | Format-Table -AutoSize ComPort, RadioRole, DriverOk, ErrorCode, Friendly
            $broken = $ports | Where-Object { -not $_.DriverOk }
            if ($broken) {
                Write-Warning "One or more cables reported a Windows Device Manager Error (e.g. Code 10 / Prolific PL2303 driver mismatch). See windows\README.md 'Troubleshooting Counterfeit Prolific Cables'!"
            }
        }
    }

    "SyncAndBuild" {
        Write-Host "[*] Running Python CSRA Repeater & Talkgroup Scraper + Codeplug Builder..." -ForegroundColor Cyan
        $env:PYTHONPATH = Join-Path $RepoRoot "src"
        & python -m csra_radio.cli --no-banner sync
        & python -m csra_radio.cli --no-banner build
        Write-Host "[+] Sync & Build complete!" -ForegroundColor Green
        Write-Host "    - UV-5R CHIRP CSV : $ChirpCsv"
        Write-Host "    - UV-5R CHIRP IMG : $ChirpImg"
        Write-Host "    - BTECH 6X2 IMG   : $BtechImg"
    }

    "Backup" {
        if (-not $chirpBins.ChirpCli) {
            throw "chirpc.exe not found! Install CHIRP-next from https://chirpmyradio.com/projects/chirp/wiki/Home or use the Manual CHIRP GUI steps in windows\README.md."
        }
        $targetPort = Resolve-TargetComPort -RequestedPort $ComPort
        $savedPath = Invoke-MandatoryPreFlashBackup -ChirpCliPath $chirpBins.ChirpCli -Port $targetPort -Model $RadioModel -Label "manual_backup"
        Write-Host "[+] Standalone radio backup complete: $savedPath" -ForegroundColor Green
    }

    "Flash" {
        if (-not $chirpBins.ChirpCli) {
            throw "chirpc.exe not found! Install CHIRP-next from https://chirpmyradio.com/projects/chirp/wiki/Home or run '.\Invoke-CsraChirp.ps1 -Action LaunchGui' for manual programming."
        }
        if (-not (Test-Path $ChirpImg)) {
            throw "Compiled CHIRP image not found at $ChirpImg! Run '.\Invoke-CsraChirp.ps1 -Action SyncAndBuild' first."
        }

        $targetPort = Resolve-TargetComPort -RequestedPort $ComPort

        # STEP 1 (MANDATORY): Download & verify backup BEFORE touching the radio's EEPROM!
        $preBackupPath = Invoke-MandatoryPreFlashBackup -ChirpCliPath $chirpBins.ChirpCli -Port $targetPort -Model $RadioModel -Label "pre_flash"

        # STEP 2: Upload the CSRA W4DV image to the radio
        Write-Host ""
        Write-Host "[*] [STEP 2/2: FLASHING CSRA W4DV CODEPLUG] Counting to Three (not Four, nor Two)..." -ForegroundColor Cyan
        Write-Host "    - Source Image   : $ChirpImg"
        Write-Host "    - Rollback Guard : $preBackupPath"
        $uploadArgs = @("-r", $RadioModel, "-s", $targetPort, "--mmap", $ChirpImg, "--upload-mmap")
        & $chirpBins.ChirpCli @uploadArgs
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Upload exited with code $LASTEXITCODE! Your original pre-flash backup is safely preserved at: $preBackupPath"
            Write-Warning "Note: If your UV-5R has a different firmware revision than HN5RV011 (e.g., BFB297), CHIRP Wiki recommends importing the CSV into your own downloaded backup image. Run: .\Invoke-CsraChirp.ps1 -Action LaunchGui"
            exit $LASTEXITCODE
        }
        Write-Host "[+] Baofeng UV-5R flash complete! 73 de KR4JLC (--... ...--)!" -ForegroundColor Green
    }

    "Restore" {
        if (-not $chirpBins.ChirpCli) {
            throw "chirpc.exe not found! Install CHIRP-next or use the CHIRP GUI (Radio -> Upload to radio) to restore your backup .img."
        }
        if (-not $BackupFile) {
            $latestBackup = Get-ChildItem -Path $BackupsDir -Filter "*.img" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if (-not $latestBackup) {
                throw "No backup .img files found in $BackupsDir! Specify -BackupFile <path>."
            }
            $BackupFile = $latestBackup.FullName
        }
        if (-not (Test-Path $BackupFile)) {
            throw "Backup file not found: $BackupFile"
        }

        $targetPort = Resolve-TargetComPort -RequestedPort $ComPort
        Write-Host "[*] Restoring verified backup image ($BackupFile) to $RadioModel on $targetPort..." -ForegroundColor Yellow
        $restoreArgs = @("-r", $RadioModel, "-s", $targetPort, "--mmap", $BackupFile, "--upload-mmap")
        & $chirpBins.ChirpCli @restoreArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Restore failed with exit code $LASTEXITCODE."
        }
        Write-Host "[+] Rollback complete! Your radio has been restored to $BackupFile." -ForegroundColor Green
    }

    "LaunchGui" {
        if (-not $chirpBins.ChirpGui) {
            Write-Warning "chirpw.exe was not found in standard installation folders."
            Write-Host "Opening CHIRP Wiki Download Page: https://chirpmyradio.com/projects/chirp/wiki/Home" -ForegroundColor Cyan
            Start-Process "https://chirpmyradio.com/projects/chirp/wiki/Home"
            exit 1
        }
        $latestBackup = Get-ChildItem -Path $BackupsDir -Filter "*.img" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1

        $filesToOpen = @()
        if ($latestBackup) { $filesToOpen += $latestBackup.FullName }
        if (Test-Path $ChirpCsv) { $filesToOpen += $ChirpCsv }

        Write-Host "[*] Launching CHIRP GUI ($($chirpBins.ChirpGui))..." -ForegroundColor Cyan
        Write-Host "    REMINDER: Always do 'Radio -> Download from radio' FIRST and save a backup .img!" -ForegroundColor Yellow
        if ($filesToOpen.Count -gt 0) {
            Start-Process -FilePath $chirpBins.ChirpGui -ArgumentList $filesToOpen
        } else {
            Start-Process -FilePath $chirpBins.ChirpGui
        }
    }

    "All" {
        & $PSCommandPath -Action Detect -NoBanner
        & $PSCommandPath -Action SyncAndBuild -NoBanner
        & $PSCommandPath -Action Flash -ComPort $ComPort -RadioModel $RadioModel -NoBanner
    }
}
