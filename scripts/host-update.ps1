# Host updater: fetch origin/main, pull when safe, restart app and cpolar in the background.
param(
    [switch]$RegisterTasks,
    [switch]$SkipPull
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Log = Join-Path $env:USERPROFILE "coffeebar-host.log"
$UrlFile = Join-Path $env:USERPROFILE "coffeebar-cpolar-url.txt"
$AllowedDirty = @(
    "web/package-lock.json",
    ".cursor/mcp.json"
)

function Write-Log([string]$Message) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $Log -Value $line -Encoding utf8
    Write-Host $line
}

function Import-DotEnv {
    $envFile = Join-Path $Root ".env"
    if (-not (Test-Path $envFile)) { return }
    foreach ($raw in Get-Content $envFile -Encoding utf8) {
        $line = $raw.Trim()
        if (-not $line -or $line.StartsWith("#") -or $line -notmatch "=") { continue }
        $pair = $line.Split("=", 2)
        $key = $pair[0].Trim()
        $val = $pair[1].Trim().Trim("'").Trim('"')
        if (-not [Environment]::GetEnvironmentVariable($key, "Process")) {
            [Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}

function Get-DirtyPaths {
    Push-Location $Root
    try {
        git status --porcelain | ForEach-Object {
            if ($_ -and $_.Length -ge 4) { $_.Substring(3).Trim().Replace("\", "/") }
        }
    } finally {
        Pop-Location
    }
}

function Test-SafeToPull {
    foreach ($path in Get-DirtyPaths) {
        if ($AllowedDirty -notcontains $path) {
            Write-Log ("skip pull, dirty: " + $path)
            return $false
        }
    }
    return $true
}

function Save-WindowsMcp {
    $mcp = Join-Path $Root ".cursor\mcp.json"
    $dir = Split-Path $mcp
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    $exe = (Join-Path $Root ".venv\Scripts\coffeebar-mcp.exe") -replace "\\", "\\"
    $envPath = (Join-Path $Root ".env") -replace "\\", "\\"
    $path = ((Join-Path $Root ".venv\Scripts"), (Join-Path $env:USERPROFILE ".local\bin"), "C:\WINDOWS\system32", "C:\WINDOWS") -join ";"
    $path = $path -replace "\\", "\\"
    $json = @"
{
  "mcpServers": {
    "coffeebar": {
      "type": "stdio",
      "command": "$exe",
      "envFile": "$envPath",
      "namespaceUseInstructions": "Build bean cards from photos; do not guess weight or price.",
      "env": {
        "COFFEEBAR_URL": "http://127.0.0.1:8000",
        "PATH": "$path"
      }
    }
  }
}
"@
    [System.IO.File]::WriteAllText($mcp, $json, [System.Text.UTF8Encoding]::new($false))
}

function Invoke-RepoPull {
    if ($SkipPull) { return $false }
    Push-Location $Root
    try {
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
        git fetch origin 2>&1 | Out-Null
        $behind = git rev-list --count HEAD..origin/main 2>$null
        if (-not $behind -or [int]$behind -le 0) {
            Write-Log "already up to date"
            return $false
        }
        if (-not (Test-SafeToPull)) { return $false }
        git restore -- web/package-lock.json 2>$null
        git pull --ff-only origin main
        if ($LASTEXITCODE -ne 0) {
            Write-Log "git pull failed, leave running app alone"
            return $false
        }
        Save-WindowsMcp
        Write-Log ("pulled " + (git log -1 --oneline))
        return $true
    } finally {
        Pop-Location
    }
}

function Invoke-Install {
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    Push-Location $Root
    try {
        Write-Log "uv sync + npm build"
        uv sync
        if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
        Set-Location (Join-Path $Root "web")
        npm install --no-fund --no-audit
        if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
    } finally {
        Pop-Location
    }
}

function Get-ListenerPid([int]$Port) {
    $line = netstat -ano | Select-String "LISTENING" | Select-String ":$Port\s" | Select-Object -First 1
    if (-not $line) { return $null }
    ($line.ToString().Trim() -split "\s+")[-1]
}

function Stop-Port([int]$Port) {
    $procId = Get-ListenerPid $Port
    if ($procId) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}

function Start-AppDetached {
    $listening = Get-ListenerPid 8000
    if ($listening) {
        Write-Log ("app already on :8000 pid " + $listening)
        return
    }
    $bat = Join-Path $PSScriptRoot "host-app.bat"
    Start-Process -FilePath $bat -WorkingDirectory $Root -WindowStyle Hidden
    $ok = $false
    foreach ($i in 1..20) {
        Start-Sleep -Seconds 1
        if (Get-ListenerPid 8000) { $ok = $true; break }
    }
    if ($ok) { Write-Log "app started in background on :8000" }
    else { Write-Log "app did not start, see host log" }
}

function Restart-AppDetached {
    Stop-Port 8000
    Start-Sleep -Seconds 1
    Start-AppDetached
}

function Find-Cpolar {
    $cmd = Get-Command cpolar -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "cpolar\cpolar.exe"),
        (Join-Path $env:LOCALAPPDATA "cpolar\cpolar\cpolar.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\cpolar\cpolar.exe"),
        "C:\Program Files\cpolar\cpolar.exe",
        "C:\cpolar\cpolar.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Write-CpolarUrl {
    foreach ($api in @("http://127.0.0.1:9200/api/tunnels", "http://127.0.0.1:4040/api/tunnels")) {
        try {
            $data = Invoke-RestMethod -Uri $api -TimeoutSec 3
            $https = @($data.tunnels) | Where-Object { $_.public_url -like "https://*" } | Select-Object -First 1
            $any = @($data.tunnels) | Select-Object -First 1
            $url = $https.public_url
            if (-not $url) { $url = $any.public_url }
            if ($url) {
                Set-Content -Path $UrlFile -Value $url -Encoding utf8
                Write-Log ("cpolar url " + $url)
                return
            }
        } catch { }
    }
    Write-Log "cpolar running; public url not read yet"
}

function Start-CpolarDetached {
    Import-DotEnv
    $exe = Find-Cpolar
    if (-not $exe) {
        Write-Log "cpolar.exe not found; intranet still works. Put CPOLAR_AUTHTOKEN in .env after installing cpolar."
        return
    }
    $token = [Environment]::GetEnvironmentVariable("CPOLAR_AUTHTOKEN", "Process")
    if (-not $token) {
        Write-Log "cpolar installed; put CPOLAR_AUTHTOKEN in .env to open the tunnel"
        return
    }
    & $exe authtoken $token 2>$null
    $running = Get-Process -Name "cpolar" -ErrorAction SilentlyContinue
    if ($running) {
        Write-Log ("cpolar already running pid " + ($running.Id -join ","))
        Write-CpolarUrl
        return
    }
    $out = Join-Path $env:USERPROFILE "coffeebar-cpolar.log"
    $err = Join-Path $env:USERPROFILE "coffeebar-cpolar.err.log"
    Start-Process -FilePath $exe -ArgumentList @("http", "8000", "-log=stdout", "-inspect-addr=127.0.0.1:4040") -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err
    Start-Sleep -Seconds 3
    if (Get-Process -Name "cpolar" -ErrorAction SilentlyContinue) {
        Write-Log "cpolar started in background"
        Start-Sleep -Seconds 2
        Write-CpolarUrl
    } else {
        Write-Log "cpolar failed; set CPOLAR_AUTHTOKEN in .env"
    }
}

function Register-HostTasks {
    $ps = Join-Path $PSHOME "powershell.exe"
    $script = Join-Path $PSScriptRoot "host-update.ps1"
    $tr = "$ps -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
    schtasks /Create /TN "coffeebar-update" /SC MINUTE /MO 15 /TR $tr /F /RL LIMITED | Out-Null
    $startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\coffeebar-host.bat"
    $startupBody = "@echo off`r`nstart `"`" /min $ps -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`"`r`n"
    [System.IO.File]::WriteAllText($startup, $startupBody, [System.Text.UTF8Encoding]::new($false))
    Write-Log "scheduled coffeebar-update every 15 min; startup shortcut coffeebar-host.bat"
}

Import-DotEnv
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"

if ($RegisterTasks) {
    Register-HostTasks
}

$pulled = Invoke-RepoPull
if ($pulled) {
    Invoke-Install
    Restart-AppDetached
} else {
    Start-AppDetached
}
Start-CpolarDetached
Write-Log "done"
