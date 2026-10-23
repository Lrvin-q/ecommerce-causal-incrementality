# =============================================================================
#  paper/build.ps1 —— 论文 PDF 构建脚本（一条命令从 Markdown 复现 PDF）
#
#  用法：  & .\paper\build.ps1
#
#  链路：  reports/00_项目总报告.md
#            --(截取正文)----------------->  paper/body.md
#            --(pandoc 3.x)--------------->  paper/body.tex
#            --(公式改 equation 环境)------>  paper/body.tex
#            --(插入 \needspace 防表题孤行)->  paper/body.tex
#            --(xref.py 补锚点+蓝色引用)--->  paper/body.tex
#            --(xelatex ×2)--------------->  paper/main.pdf
# =============================================================================
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'

$paper = $PSScriptRoot
$root  = Split-Path $paper -Parent
$src   = Join-Path $root 'reports\00_项目总报告.md'

$pandoc  = 'C:\Program Files\Pandoc\pandoc.exe'
$xelatex = 'D:\SelfDownloadSoftware\texlive\2025\bin\windows\xelatex.exe'
$python  = Join-Path $root '.venv\Scripts\python.exe'
foreach ($exe in @($pandoc, $xelatex, $python)) {
    if (-not (Test-Path $exe)) { throw "找不到 $exe" }
}

Write-Host '[1/5] 提取正文 ...'
$md = Get-Content $src -Raw -Encoding utf8
$i = $md.IndexOf('## 1 引言')
if ($i -lt 0) { throw '未找到正文起点 “## 1 引言”' }
$body = $md.Substring($i)
Set-Content -Path (Join-Path $paper 'body.md') -Value $body -Encoding utf8
Write-Host ('      正文 {0} 行' -f ($body -split "`n").Count)

Write-Host '[2/5] pandoc 转 LaTeX ...'
& $pandoc (Join-Path $paper 'body.md') -f markdown -t latex `
    --shift-heading-level-by=-1 --syntax-highlighting=none `
    -o (Join-Path $paper 'body.tex')
if ($LASTEXITCODE -ne 0) { throw "pandoc 失败（exit=$LASTEXITCODE）" }

# 公式编号右对齐：pandoc 把 $$...\tag{N}...$$ 输出为 \[ ... \tag{N} ... \]，
# 而 \tag 只在 equation/align 环境里合法。留在 \[ \] 里会报错或被居中显示，
# 编号紧贴公式体、不在右端。这里把含 \tag 的 \[...\] 改写成 equation 环境。
$tex = Get-Content (Join-Path $paper 'body.tex') -Raw -Encoding utf8
$tex = [regex]::Replace(
    $tex,
    '(?s)\\\[(.*?\\tag\{[0-9]+\}.*?)\\\]',
    '\begin{equation}$1\end{equation}')
$nEq = ([regex]::Matches($tex, '\\begin\{equation\}')).Count
Write-Host ("      公式 {0} 个（已改为 equation 环境，编号右对齐）" -f $nEq)

Write-Host '[3/5] 插入 \needspace 防止表题孤悬页底 ...'
$nTable = ([regex]::Matches($tex, '(?m)^\\textbf\{表 ')).Count
# 11 个 baselineskip ≈ 「两行表题 + 8 行表体」所需高度。原来只留 7，
# 表 6（7 行 × 9 列、表题两行）会出现「表题在页底、表体翻到下一页」。
$tex = [regex]::Replace($tex, '(?m)^\\textbf\{表 ', '\needspace{11\baselineskip}\textbf{表 ')
# 表 B1 是附录里的整表；若在页底再插 needspace，会把整表推到下一页并留下近空白页。
# 其余表仍在题注前预留 11 行，防止“题注在页底、表体翻页”。
$tex = $tex.Replace('\needspace{11\baselineskip}\textbf{表 B1', '\textbf{表 B1')
# 表 C1 同理：它在附录 C 标题之后，若在页底预留空间会把标题单独留在上一页（实测出现过整页空白）。
$tex = $tex.Replace('\needspace{11\baselineskip}\textbf{表 C1', '\textbf{表 C1')
Set-Content -Path (Join-Path $paper 'body.tex') -Value $tex -Encoding utf8 -NoNewline
$nFig = ([regex]::Matches($tex, '\\begin\{figure\}')).Count
Write-Host ("      表 {0} 张、图 {1} 张" -f $nTable, $nFig)

Write-Host '[4/5] 补交叉引用锚点（表/图/公式 → 蓝色可跳转）...'
& $python (Join-Path $paper 'xref.py') (Join-Path $paper 'body.tex')
if ($LASTEXITCODE -ne 0) { throw "xref.py 失败（exit=$LASTEXITCODE）" }

Write-Host '[5/5] xelatex 编译两遍（第二遍生成交叉引用）...'
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
