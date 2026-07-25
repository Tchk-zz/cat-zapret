# Downloads the latest Flowseal zapret-discord-youtube bundle into vendor\zapret
# so build.bat can embed it into the standalone exe. Runs once; if the bundle
# is already present it does nothing.
$ErrorActionPreference = 'Stop'

$repo = 'Flowseal/zapret-discord-youtube'
$dest = Join-Path $PSScriptRoot 'vendor\zapret'

if (Test-Path (Join-Path $dest 'bin\winws.exe')) {
    Write-Host 'zapret bundle already present in vendor\zapret - skipping download.'
    exit 0
}

# Enable TLS 1.2 AND TLS 1.3 (if available) so GitHub API + release downloads
# work on modern Windows. Windows PowerShell 5.1 only knows about TLS 1.2 by
# default; PowerShell 7+ adds 1.3 automatically. We OR the flags together so
# both versions are happy.
try {
    $tls = [Net.SecurityProtocolType]::Tls12
    if ([enum]::IsDefined([Net.SecurityProtocolType], 12288)) {  # Tls13 = 12288
        $tls = $tls -bor [Net.SecurityProtocolType]12288
    }
    [Net.ServicePointManager]::SecurityProtocol = $tls
} catch {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
}
$headers = @{ 'User-Agent' = 'ZapretGUI-build'; 'Accept' = 'application/vnd.github+json' }

Write-Host 'Querying the latest Flowseal release...'
try {
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases/latest" -Headers $headers
} catch {
    Write-Error "GitHub API call failed: $($_.Exception.Message)"
    Write-Error 'If this is a rate-limit (60 req/hr unauthenticated), wait a few minutes and rerun build.bat.'
    exit 1
}

$tmp = Join-Path $env:TEMP ("zapret_" + [guid]::NewGuid().ToString())
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$zip = Join-Path $tmp 'zapret.zip'

$asset = $rel.assets | Where-Object { $_.name -like '*.zip' } | Select-Object -First 1
if ($asset) {
    Write-Host ("Downloading asset: " + $asset.name)
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -Headers $headers
    # Verify SHA-256 against the digest advertised by GitHub. The API returns
    # it as "sha256:<hex>"; we strip the prefix and compare. A mismatch is a
    # hard error — better to abort the build than ship a corrupted winws.exe.
    if ($asset.digest) {
        $expected = $asset.digest -replace '^sha256:', ''
        $actual = (Get-FileHash -Algorithm SHA256 -Path $zip).Hash.ToLower()
        if ($actual -ne $expected.ToLower()) {
            Write-Error "SHA-256 mismatch: expected $expected, got $actual"
            Write-Error 'The downloaded asset is corrupted or tampered with. Re-run build.bat.'
            exit 1
        }
        Write-Host "SHA-256 verified: $actual"
    }
} else {
    Write-Host 'No zip asset found; downloading source zipball.'
    Invoke-WebRequest -Uri $rel.zipball_url -OutFile $zip -Headers $headers
    # Source zipballs have no asset.digest field — we can't verify them, but
    # we still report the hash so a CI log can compare it across builds.
    $actual = (Get-FileHash -Algorithm SHA256 -Path $zip).Hash.ToLower()
    Write-Host "Source zipball SHA-256: $actual (no GitHub digest to compare)"
}

$ext = Join-Path $tmp 'x'
Expand-Archive -Path $zip -DestinationPath $ext -Force

# Locate the folder that actually contains bin\winws.exe (handles both the
# flat release asset and the nested source zipball layouts).
$winws = Get-ChildItem -Path $ext -Recurse -Filter 'winws.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $winws) {
    Write-Error 'winws.exe was not found in the downloaded archive.'
    exit 1
}
# If winws.exe sits directly inside the extraction folder, "$winws.Directory"
# IS the root we want. Only go one level up when winws is inside a real
# subfolder (e.g. bin\winws.exe or <repo>-main\bin\winws.exe). Previously the
# code always took ".Parent", which on a flat layout would copy the entire
# TEMP directory into vendor\zapret.
if ($winws.Directory.FullName -eq $ext) {
    $srcRoot = $ext
} else {
    $srcRoot = $winws.Directory.Parent.FullName
}

New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item -Path (Join-Path $srcRoot '*') -Destination $dest -Recurse -Force

if (-not (Test-Path (Join-Path $dest 'bin\winws.exe'))) {
    Write-Error 'Downloaded archive was copied, but vendor\zapret\bin\winws.exe is still missing.'
    Write-Error 'The release archive layout is not supported by this build script.'
    exit 1
}

try { Remove-Item -Path $tmp -Recurse -Force -ErrorAction SilentlyContinue } catch {}
Write-Host ("zapret " + $rel.tag_name + " bundle ready at " + $dest)
exit 0
