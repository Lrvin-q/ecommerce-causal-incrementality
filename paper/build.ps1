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
# 表 B1 / C1 是附录里的整表（B1 有 17 行、多数单元格折 2–4 行，约占半页）。
# 第 4 轮审稿 N2：整条删掉 needspace 后，B1 的题注被留在页底、表体翻到下一页；
# 同样的分页在内容整体上移后也会轮到 C1。修法不是把 11 行预约加回来（那会把整表
# 推走、多占一页），而是：
#   ① 题注前只留 6 行预约，保证题注本身不会孤零零落在页底最后一行；
#   ② 题注后用 \nopagebreak[4] 把「题注 + 后面那个不可分页的 minipage」绑成一块。
# TeX 于是只能在题注**之前**换页：题注与表体永远同页，也不会平白多占一页。
foreach ($tbl in @('B1', 'C1')) {
    $tex = $tex.Replace(
        '\needspace{11\baselineskip}\textbf{表 ' + $tbl,
        '\needspace{6\baselineskip}\textbf{表 ' + $tbl)
    $tex = [regex]::Replace(
        $tex,
        '(\\textbf\{表 ' + $tbl + '\}[^\r\n]*\r?\n\r?\n)(\{\\def\\LTcaptype\{none\})',
        '$1' + "`n" + '\nopagebreak[4]' + "`n" + '$2')
}
# 表 A1 由 8 行拆成 18 行（一参数一行）后，同样的预留也会在附录 A 标题之后触发换页：
# 标题单独留在上一页、整表落到下一页，实测多出 1 页且那一页近空白（16 页）。
# 附录 A 标题之后紧接着就是表格题注，不存在“题注孤悬页底”的问题，故一并去掉预约空间。
$tex = $tex.Replace('\needspace{11\baselineskip}\textbf{表 A1', '\textbf{表 A1')
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
