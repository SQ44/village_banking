$ErrorActionPreference = "Stop"

function Copy-IfMissing {
  param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Dest
  )
  if (!(Test-Path -LiteralPath $Dest)) {
    Copy-Item -LiteralPath $Source -Destination $Dest
    Write-Host "Created $Dest from $Source"
  }
}

function Set-EnvValue {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Key,
    [Parameter(Mandatory = $true)][string]$Value
  )

  $text = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop -Encoding UTF8

  if ($text -match "(?m)^\s*${Key}\s*=") {
    $text = [regex]::Replace($text, "(?m)^\s*${Key}\s*=.*$", "${Key}=${Value}")
  } else {
    if (-not $text.EndsWith("`n")) { $text += "`n" }
    $text += "${Key}=${Value}`n"
  }

  # Write UTF-8 without BOM (a BOM on the first key breaks pydantic-settings key parsing).
  [System.IO.File]::WriteAllText($Path, $text, (New-Object System.Text.UTF8Encoding($false)))
}

function Get-EnvValue {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Key
  )
  $match = Select-String -LiteralPath $Path -Pattern "(?m)^\s*${Key}\s*=\s*(.*)\s*$" -AllMatches
  if (-not $match) { return $null }
  return $match.Matches[0].Groups[1].Value
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\\..")

$serverEnvExample = Join-Path $repoRoot "server\\.env.example"
$serverEnv = Join-Path $repoRoot "server\\.env"
$lencoEnvExample = Join-Path $repoRoot "lenco_pay\\.env.example"
$lencoEnv = Join-Path $repoRoot "lenco_pay\\.env"

Copy-IfMissing -Source $serverEnvExample -Dest $serverEnv
Copy-IfMissing -Source $lencoEnvExample -Dest $lencoEnv

$secret = Get-EnvValue -Path $serverEnv -Key "auth_secret_key"
if (-not $secret) { $secret = "" }

if ([string]::IsNullOrWhiteSpace($secret)) {
  $bytes = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $generated = [Convert]::ToBase64String($bytes)
  Set-EnvValue -Path $serverEnv -Key "auth_secret_key" -Value $generated
  Write-Host "Generated auth_secret_key in server/.env"
}

$adminEmail = Get-EnvValue -Path $serverEnv -Key "default_admin_email"
$adminPassword = Get-EnvValue -Path $serverEnv -Key "default_admin_password"

if ([string]::IsNullOrWhiteSpace([string]$adminEmail) -or [string]::IsNullOrWhiteSpace([string]$adminPassword)) {
  Write-Warning "Set default_admin_email and default_admin_password in server/.env to enable admin auto-seeding."
}

Write-Host "Done."
