# build-release.ps1 - 打包即梦内容工厂发布 ZIP
# 运营拿到 ZIP 解压后，运行 setup.ps1 → start.bat 即可

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$VERSION = "1.0"
$RELEASE_NAME = "jimeng-factory-v$VERSION"
$OUT_ZIP = "$ROOT\$RELEASE_NAME.zip"
$TEMP_DIR = "$ROOT\.release-staging\$RELEASE_NAME"

Write-Host "=== 打包即梦内容工厂 v$VERSION ===" -ForegroundColor Cyan

# 清理旧的暂存目录
if (Test-Path "$ROOT\.release-staging") {
    Remove-Item "$ROOT\.release-staging" -Recurse -Force
}

# 定义要排除的目录和文件
$EXCLUDE_DIRS = @(
    ".git",
    ".claude",
    ".tmp_validation",
    ".agentbridge",
    "runs",
    "runtime",
    "outputs",
    "node_modules",
    "frontend\node_modules",
    "frontend\src",
    "docs\handoffs",
    "scripts",
    "__pycache__",
    ".release-staging"
)

$EXCLUDE_FILES = @(
    "config.yaml",
    "config.example.yaml",
    "build-release.ps1",
    "CLAUDE.md",
    ".gitignore",
    "*.zip",
    "*.pyc"
)

# 1. 前置检查：frontend/dist 必须已编译
if (-not (Test-Path "$ROOT\frontend\dist\index.html")) {
    Write-Host "错误：frontend/dist 不存在，请先编译前端" -ForegroundColor Red
    Write-Host "  cd frontend && npm install && npm run build" -ForegroundColor Yellow
    exit 1
}

# 2. 用 robocopy 复制文件（排除开发目录）
Write-Host "复制文件..." -ForegroundColor Yellow
$excludeDirArgs = $EXCLUDE_DIRS | ForEach-Object { "/XD", "$ROOT\$_" }
$excludeFileArgs = $EXCLUDE_FILES | ForEach-Object { "/XF", $_ }

$roboArgs = @($ROOT, $TEMP_DIR, "/E", "/NJH", "/NJS", "/NP", "/NFL", "/NDL") + $excludeDirArgs + $excludeFileArgs
& robocopy @roboArgs | Out-Null
if ($LASTEXITCODE -ge 8) {
    Write-Host "错误：文件复制失败 (robocopy exit code $LASTEXITCODE)" -ForegroundColor Red
    Remove-Item "$ROOT\.release-staging" -Recurse -Force -ErrorAction SilentlyContinue
    exit 1
}

# 3. 清理暂存目录中的开发残留
Get-ChildItem -Path $TEMP_DIR -Directory -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path $TEMP_DIR -File -Recurse -Filter "*.pyc" | Remove-Item -Force
if (Test-Path "$TEMP_DIR\frontend\node_modules") {
    Remove-Item "$TEMP_DIR\frontend\node_modules" -Recurse -Force
}
# 前端开发文件（运营只需要 dist）
foreach ($devFile in @("package.json", "package-lock.json", "vite.config.js", "index.html")) {
    $p = "$TEMP_DIR\frontend\$devFile"
    if (Test-Path $p) { Remove-Item $p -Force }
}
# 示例产品数据
if (Test-Path "$TEMP_DIR\data\products") {
    Remove-Item "$TEMP_DIR\data\products\*" -Recurse -Force -ErrorAction SilentlyContinue
}

# 4. 创建空目录占位（运营解压后目录结构完整）
New-Item -ItemType Directory -Force -Path "$TEMP_DIR\runtime" | Out-Null
New-Item -ItemType Directory -Force -Path "$TEMP_DIR\outputs" | Out-Null
New-Item -ItemType Directory -Force -Path "$TEMP_DIR\data\products" | Out-Null

# 5. 打包 ZIP
Write-Host "打包 ZIP..." -ForegroundColor Yellow
if (Test-Path $OUT_ZIP) {
    Remove-Item $OUT_ZIP -Force
}
Compress-Archive -Path $TEMP_DIR -DestinationPath $OUT_ZIP -CompressionLevel Optimal

# 6. 清理暂存
Remove-Item "$ROOT\.release-staging" -Recurse -Force

# 7. 输出结果
$size = [math]::Round((Get-Item $OUT_ZIP).Length / 1MB, 1)
Write-Host "`n=== 打包完成 ===" -ForegroundColor Cyan
Write-Host "文件: $OUT_ZIP" -ForegroundColor Green
Write-Host "大小: ${size} MB" -ForegroundColor Green
Write-Host "`n分发给运营后，告知：" -ForegroundColor White
Write-Host "  1. 解压到任意目录"
Write-Host "  2. 双击 setup.bat 安装依赖"
Write-Host "  3. 编辑 config.yaml 中的多空间浏览器路径"
Write-Host "  4. 双击 start.bat"
