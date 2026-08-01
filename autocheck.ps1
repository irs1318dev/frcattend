# Format, lint, and type-check the source and test code.

$targets = "src/frcattend", "tests"

Write-Host "==> ruff format" -ForegroundColor Cyan
uv run ruff format $targets

Write-Host "==> ruff check" -ForegroundColor Cyan
uv run ruff check --fix $targets

Write-Host "==> pyright" -ForegroundColor Cyan
uv run pyright $targets
