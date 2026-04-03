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
    "runs",
    "runtime",
    "outputs",
    "node_modules",
    "frontend\node_modules",
    ".release-staging"
)

$EXCLUDE_FILES = @(
    "config.yaml",
    "*.zip"
)

# 1. 检查 frontend/dist 是否存在
if (-not (Test-Path "$ROOT\frontend\dist\index.html")) {
    Write-Host "前端未编译，先执行 npm run build..." -ForegroundColor Yellow
    Push-Location "$ROOT\frontend"
    npm run build
    Pop-Location
    if (-not (Test-Path "$ROOT\frontend\dist\index.html")) {
        Write-Host "错误：前端编译失败" -ForegroundColor Red
        exit 1
    }
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

# 3. 清理暂存目录中不需要的内容
# 删除前端源码中的 node_modules（如果被复制进来）
if (Test-Path "$TEMP_DIR\frontend\node_modules") {
    Remove-Item "$TEMP_DIR\frontend\node_modules" -Recurse -Force
}
# 删除 data/products 中的示例数据
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
Write-Host "  2. 右键 setup.ps1 → 使用 PowerShell 运行"
Write-Host "  3. 编辑 config.yaml 中的多空间浏览器路径"
Write-Host "  4. 双击 start.bat"
