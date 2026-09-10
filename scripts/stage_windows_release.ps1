param(
    [Parameter(Mandatory = $true)]
    [string]$GMonsterExePath,
    [Parameter(Mandatory = $true)]
    [string]$WumExePath
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$stageDirectory = Join-Path $projectRoot "release\stage"

foreach ($filePath in @($GMonsterExePath, $WumExePath)) {
    if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
        throw "Required executable was not found at $filePath"
    }
}

if (Test-Path -LiteralPath $stageDirectory) {
    Remove-Item -LiteralPath $stageDirectory -Recurse -Force
}
New-Item -ItemType Directory -Path $stageDirectory -Force | Out-Null
Copy-Item -LiteralPath $GMonsterExePath -Destination (Join-Path $stageDirectory "GMonster.exe")
Copy-Item -LiteralPath $WumExePath -Destination (Join-Path $stageDirectory "WUM.exe")
