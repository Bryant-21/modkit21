# build_nif_ui.ps1 - Build only the ModBox21 NIF UI standalone EXE.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File build_nif_ui.ps1
#   powershell -ExecutionPolicy Bypass -File build_nif_ui.ps1 -SkipClean

param(
    [switch]$SkipClean
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Variant = @{
    Id = "nif"
    ExeName = "ModBox21-NIF"
    Folder = "ModBox21-NIF"
    Icon = "resource\icons\modbox21-nif.ico"
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
    if ((Get-Item $SourcePath).PSIsContainer) {
        New-Item -ItemType Directory -Force -Path $DestPath | Out-Null
        Copy-Item -Recurse -Force "$SourcePath\*" $DestPath
    } else {
        $dstParent = Split-Path -Parent $DestPath
        if (-not (Test-Path $dstParent)) {
            New-Item -ItemType Directory -Force -Path $dstParent | Out-Null
        }
        Copy-Item -Force $SourcePath $DestPath
    }
}

function Copy-NifResources($DestinationRoot) {
    $resourceSrc = Join-Path $ProjectRoot "resource"
    $resourceDst = Join-Path $DestinationRoot "_internal\resource"
    if (-not (Test-Path $resourceSrc)) {
        return
    }
    if (Test-Path $resourceDst) {
        Remove-Item -Recurse -Force $resourceDst
    }
    New-Item -ItemType Directory -Force -Path $resourceDst | Out-Null

    $files = @(
        "icon.ico",
        "monochrome_studio_02_1k.exr",
        "skeleton.nif",
        "skeleton.xml",
        "skeleton.hkx"
    )
    foreach ($file in $files) {
        Copy-ReleaseItem (Join-Path $resourceSrc $file) (Join-Path $resourceDst $file)
    }

    $variantIconSrc = Join-Path $ProjectRoot $Variant.Icon
    if (Test-Path $variantIconSrc) {
        $iconName = Split-Path -Leaf $variantIconSrc
        Copy-ReleaseItem $variantIconSrc (Join-Path (Join-Path $resourceDst "icons") $iconName)
    }
}

Write-Host "=== ModBox21 NIF UI Build ===" -ForegroundColor Cyan

$variantDir = Join-Path $ProjectRoot "dist\$($Variant.Folder)"
$workPath = Join-Path $ProjectRoot "build\$($Variant.Id)"

if (-not $SkipClean) {
    Write-Host "`n[1/3] Cleaning NIF build output..." -ForegroundColor Yellow
    Remove-BuildPath $variantDir
    Remove-BuildPath $workPath
} else {
    Write-Host "`n[1/3] Skipping clean..." -ForegroundColor Gray
}

Write-Host "`n[2/3] Running PyInstaller for $($Variant.ExeName)..." -ForegroundColor Yellow
$env:MODBOX21_EXE_NAME = $Variant.ExeName
$env:MODBOX21_DIST_NAME = $Variant.Folder
$env:MODBOX21_ICON = $Variant.Icon

try {
    $specFile = Join-Path $ProjectRoot "ModBox21.spec"
    & uv run --with pyinstaller pyinstaller $specFile --noconfirm --workpath $workPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed for $($Variant.ExeName) with exit code $LASTEXITCODE"
    }
} finally {
    Remove-Item Env:\MODBOX21_EXE_NAME -ErrorAction SilentlyContinue
    Remove-Item Env:\MODBOX21_DIST_NAME -ErrorAction SilentlyContinue
    Remove-Item Env:\MODBOX21_ICON -ErrorAction SilentlyContinue
}

Write-Host "`n[3/3] Copying NIF runtime resources..." -ForegroundColor Yellow
Copy-NifResources $variantDir
Get-ChildItem -Recurse -Include "*.pdb","*.debug" $variantDir | Remove-Item -Force

Write-Host "`n=== NIF UI Build Complete ===" -ForegroundColor Green
Write-Host "Output: $variantDir"
Write-Host "EXE: $(Join-Path $variantDir "$($Variant.ExeName).exe")"
