# =============================================================================
#  paper/build.ps1 —— 论文 PDF 构建脚本（一条命令从 Markdown 复现 PDF）
#
#  用法：  pwsh -File .\paper\build.ps1
#
#  链路：  reports/00_项目总报告.md
#            --(截取正文 + 公式编号改写)-->  paper/body.md
#            --(pandoc 3.x)--------------->  paper/body.tex
#            --(插入 \needspace 防表题孤行)->  paper/body.tex
#            --(xelatex ×2)--------------->  paper/main.pdf
# =============================================================================
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'

$paper = $PSScriptRoot
$root  = Split-Path $paper -Parent
$src   = Join-Path $root 'reports\00_项目总报告.md'

$pandoc  = 'C:\Program Files\Pandoc\pandoc.exe'
$xelatex = 'D:\SelfDownloadSoftware\texlive\2025\bin\windows\xelatex.exe'
foreach ($exe in @($pandoc, $xelatex)) {
    if (-not (Test-Path $exe)) { throw "找不到 $exe" }
}

Write-Host '[1/4] 提取正文并改写公式编号 ...'
$md = Get-Content $src -Raw -Encoding utf8
$i = $md.IndexOf('## 1 问题背景')
if ($i -lt 0) { throw '未找到正文起点 “## 1 问题背景”' }
$body = $md.Substring($i)
# display math 的 \[ \] 中不允许 \tag，改写为右对齐编号
$body = [regex]::Replace($body, '\\tag\{(\d+)\}', '\qquad($1)')
Set-Content -Path (Join-Path $paper 'body.md') -Value $body -Encoding utf8
Write-Host ('      正文 {0} 行' -f ($body -split "`n").Count)

Write-Host '[2/4] pandoc 转 LaTeX ...'
& $pandoc (Join-Path $paper 'body.md') -f markdown -t latex `
    --shift-heading-level-by=-1 --syntax-highlighting=none `
    -o (Join-Path $paper 'body.tex')
if ($LASTEXITCODE -ne 0) { throw "pandoc 失败（exit=$LASTEXITCODE）" }

Write-Host '[3/4] 插入 \needspace 防止表题孤悬页底 ...'
$tex = Get-Content (Join-Path $paper 'body.tex') -Raw -Encoding utf8
$nTable = ([regex]::Matches($tex, '(?m)^\\textbf\{表 ')).Count
$tex = [regex]::Replace($tex, '(?m)^\\textbf\{表 ', '\needspace{7\baselineskip}\textbf{表 ')
Set-Content -Path (Join-Path $paper 'body.tex') -Value $tex -Encoding utf8 -NoNewline
$nFig = ([regex]::Matches($tex, '\\begin\{figure\}')).Count
Write-Host ("      表 {0} 张、图 {1} 张" -f $nTable, $nFig)

Write-Host '[4/4] xelatex 编译两遍（第二遍生成交叉引用）...'
Push-Location $paper
try {
    for ($pass = 1; $pass -le 2; $pass++) {
        & $xelatex -interaction=nonstopmode -halt-on-error main.tex | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $errs = Select-String -Path main.log -Pattern '^!' | Select-Object -First 8
            $errs | ForEach-Object { Write-Host $_.Line -ForegroundColor Red }
            throw "xelatex 第 $pass 遍失败"
        }
        Write-Host "      第 $pass 遍完成"
    }
}
finally { Pop-Location }

$pdf = Join-Path $paper 'main.pdf'
if (-not (Test-Path $pdf)) { throw 'PDF 未生成' }
$pages = (Select-String -Path (Join-Path $paper 'main.log') -Pattern 'Output written on .* \((\d+) pages?' |
          Select-Object -Last 1).Matches.Groups[1].Value
Write-Host ''
Write-Host ("完成：{0}（{1} 页，{2} KB）" -f $pdf, $pages, [int]((Get-Item $pdf).Length / 1KB)) -ForegroundColor Green
