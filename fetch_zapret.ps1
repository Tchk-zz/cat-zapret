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

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$headers = @{ 'User-Agent' = 'ZapretGUI-build'; 'Accept' = 'application/vnd.github+json' }

Write-Host 'Querying the latest Flowseal release...'
$rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases/latest" -Headers $headers

$tmp = Join-Path $env:TEMP ("zapret_" + [guid]::NewGuid().ToString())
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$zip = Join-Path $tmp 'zapret.zip'

$asset = $rel.assets | Where-Object { $_.name -like '*.zip' } | Select-Object -First 1
if ($asset) {
    Write-Host ("Downloading asset: " + $asset.name)
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -Headers $headers
} else {
    Write-Host 'No zip asset found; downloading source zipball.'
    Invoke-WebRequest -Uri $rel.zipball_url -OutFile $zip -Headers $headers
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
$srcRoot = $winws.Directory.Parent.FullName

New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item -Path (Join-Path $srcRoot '*') -Destination $dest -Recurse -Force

Write-Host ("zapret " + $rel.tag_name + " bundle ready at " + $dest)
exit 0
