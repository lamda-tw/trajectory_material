[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Workbook,

    [Parameter(Mandatory = $true)]
    [string]$Aggregation,

    [Parameter(Mandatory = $true)]
    [string]$PreviewDirectory
)

$ErrorActionPreference = "Stop"

function Resolve-PdfToPpm {
    if ($env:EVAL_PDFTOPPM) {
        $configured = [IO.Path]::GetFullPath($env:EVAL_PDFTOPPM)
        if (-not (Test-Path -LiteralPath $configured -PathType Leaf)) {
            throw "EVAL_PDFTOPPM does not exist: $configured"
        }
        return $configured
    }

    $discovered = Get-Command pdftoppm.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($null -ne $discovered) {
        return $discovered.Source
    }

    if ($env:EVAL_NODE_MODULES) {
        $nodeRoot = Split-Path -Parent ([IO.Path]::GetFullPath($env:EVAL_NODE_MODULES))
        $dependenciesRoot = Split-Path -Parent $nodeRoot
        $bundled = Join-Path $dependenciesRoot "native\poppler\Library\bin\pdftoppm.exe"
        if (Test-Path -LiteralPath $bundled -PathType Leaf) {
            return $bundled
        }
    }

    throw "pdftoppm is required for the Excel preview fallback; set EVAL_PDFTOPPM"
}

function Release-ComObject {
    param([object]$Value)
    if ($null -ne $Value -and [Runtime.InteropServices.Marshal]::IsComObject($Value)) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($Value)
    }
}

$workbookPath = (Resolve-Path -LiteralPath $Workbook).Path
$aggregationPath = (Resolve-Path -LiteralPath $Aggregation).Path
$previewPath = [IO.Path]::GetFullPath($PreviewDirectory)
[void][IO.Directory]::CreateDirectory($previewPath)
$pdftoppmPath = Resolve-PdfToPpm

$payload = Get-Content -Raw -Encoding UTF8 -LiteralPath $aggregationPath | ConvertFrom-Json
$sheetLayouts = @($payload.workbook_sheets)
if ($sheetLayouts.Count -ne 9) {
    throw "aggregation payload must contain exactly nine workbook_sheets"
}

$excel = $null
$book = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $true
    $excel.WindowState = -4143
    $excel.DisplayAlerts = $false
    $excel.ScreenUpdating = $true
    $book = $excel.Workbooks.Open($workbookPath, 0, $false)
    [void]$book.Activate()
    [Threading.Thread]::Sleep(500)

    foreach ($layout in $sheetLayouts) {
        $sheetName = [string]$layout.name
        $frozenColumns = switch ([string]$layout.kind) {
            "ladder" { 1 }
            "detail" { 2 }
            default { throw "unsupported EI sheet kind: $($layout.kind)" }
        }
        $sheet = $null
        $window = $null
        $usedRange = $null
        $previewRange = $null
        try {
            $sheet = $book.Worksheets.Item($sheetName)
            [void]$sheet.Activate()
            $window = $excel.ActiveWindow
            $window.FreezePanes = $false
            $window.SplitRow = 4
            $window.SplitColumn = $frozenColumns
            $window.FreezePanes = $true
            $usedRange = $sheet.UsedRange
            $rowCount = [Math]::Min(30, [Math]::Max(1, [int]$usedRange.Rows.Count))
            $columnCount = [Math]::Min(12, [Math]::Max(1, [int]$usedRange.Columns.Count))
            $previewRange = $sheet.Range(
                $sheet.Cells.Item(1, 1),
                $sheet.Cells.Item($rowCount, $columnCount)
            )
            $previewPdf = Join-Path $previewPath ($sheetName + ".pdf")
            $previewFile = Join-Path $previewPath ($sheetName + ".png")
            $previewPrefix = Join-Path $previewPath $sheetName
            [void]$previewRange.ExportAsFixedFormat(0, $previewPdf, 0, $true, $true)
            $previousErrorAction = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                $conversionOutput = & $pdftoppmPath -f 1 -singlefile -png -r 144 -- $previewPdf $previewPrefix 2>&1
                $conversionExitCode = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $previousErrorAction
            }
            if ($conversionExitCode -ne 0 -or -not (Test-Path -LiteralPath $previewFile -PathType Leaf)) {
                throw "pdftoppm could not render ${sheetName}: $conversionOutput"
            }
            Remove-Item -LiteralPath $previewPdf
        }
        finally {
            Release-ComObject $previewRange
            Release-ComObject $usedRange
            Release-ComObject $window
            Release-ComObject $sheet
        }
    }
    $book.Save()
}
finally {
    if ($null -ne $book) {
        $book.Close($false)
    }
    if ($null -ne $excel) {
        $excel.Visible = $false
        $excel.Quit()
    }
    Release-ComObject $book
    Release-ComObject $excel
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
