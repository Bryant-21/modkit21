# build_previs_ui.ps1 - Build only the ModBox21 Previs and Precombines standalone EXE.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File build_previs_ui.ps1
#   powershell -ExecutionPolicy Bypass -File build_previs_ui.ps1 -SkipClean

param(
    [switch]$SkipClean
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Variant = @{
    Id = "previs"
    ExeName = "ModBox21-Previs"
    Folder = "ModBox21-Previs"
    Icon = "resource\icon.ico"
}

function Assert-WithinProject($Path) {
    $root = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd("\", "/")
    $full = [System.IO.Path]::GetFullPath($Path)
    $rootWithSeparator = "$root$([System.IO.Path]::DirectorySeparatorChar)"
    if (-not ($full.Equals($root, [System.StringComparison]::OrdinalIgnoreCase) -or
        $full.StartsWith($rootWithSeparator, [System.StringComparison]::OrdinalIgnoreCase))) {
        throw "Refusing to operate outside project root: $full"
    }
    return $full
}

function Remove-BuildPath($Path) {
    $full = Assert-WithinProject $Path
    if (Test-Path -LiteralPath $full) {
        Remove-Item -LiteralPath $full -Recurse -Force
    }
}

function Copy-ReleaseItem($SourcePath, $DestPath) {
    if (-not (Test-Path $SourcePath)) {
        return
    }
    $dstParent = Split-Path -Parent $DestPath
    if (-not (Test-Path $dstParent)) {
        New-Item -ItemType Directory -Force -Path $dstParent | Out-Null
    }
    Copy-Item -Force $SourcePath $DestPath
}

# The previs workspace drives creation_lib directly, so it needs no bundled
# modkit and no renderer resources: only the window icon.
function Copy-PrevisResources($DestinationRoot) {
    $resourceDst = Join-Path $DestinationRoot "_internal\resource"
    if (Test-Path $resourceDst) {
        Remove-Item -Recurse -Force $resourceDst
    }
    New-Item -ItemType Directory -Force -Path $resourceDst | Out-Null
    Copy-ReleaseItem (Join-Path $ProjectRoot $Variant.Icon) (Join-Path $resourceDst "icon.ico")
}

Write-Host "=== ModBox21 Previs UI Build ===" -ForegroundColor Cyan

$variantDir = Join-Path $ProjectRoot "dist\$($Variant.Folder)"
$workPath = Join-Path $ProjectRoot "build\$($Variant.Id)"

if (-not $SkipClean) {
    Write-Host "`n[1/3] Cleaning Previs build output..." -ForegroundColor Yellow
    Remove-BuildPath $variantDir
    Remove-BuildPath $workPath
} else {
    Write-Host "`n[1/3] Skipping clean..." -ForegroundColor Gray
}

Write-Host "`n[2/3] Running PyInstaller for $($Variant.ExeName)..." -ForegroundColor Yellow
$env:MODBOX21_EXE_NAME = $Variant.ExeName
$env:MODBOX21_DIST_NAME = $Variant.Folder
$env:MODBOX21_ICON = $Variant.Icon
$env:MODBOX21_RESOURCE_PROFILE = "minimal"

try {
    $specFile = Join-Path $ProjectRoot "ModBox21.spec"
    & uv run --with pyinstaller pyinstaller $specFile --noconfirm --workpath $workPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed for $($Variant.ExeName) with exit code $LASTEXITCODE"
    }
} finally {
    Remove-Item Env:\MODBOX21_EXE_NAME -ErrorAction SilentlyContinue
    Remove-Item Env:\MODBOX21_DIST_NAME -ErrorAction SilentlyContinue
    Remove-Item Env:\MODBOX21_RESOURCE_PROFILE -ErrorAction SilentlyContinue
    Remove-Item Env:\MODBOX21_ICON -ErrorAction SilentlyContinue
}

Write-Host "`n[3/3] Copying Previs runtime resources..." -ForegroundColor Yellow
Copy-PrevisResources $variantDir
Get-ChildItem -Recurse -Include "*.pdb","*.debug" $variantDir | Remove-Item -Force

Write-Host "`n=== Previs UI Build Complete ===" -ForegroundColor Green
Write-Host "Output: $variantDir"
Write-Host "EXE: $(Join-Path $variantDir "$($Variant.ExeName).exe")"
