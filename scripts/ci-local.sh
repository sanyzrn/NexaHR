#!/usr/bin/env bash
# همان کاری که CI می‌کند، روی همین ماشین.
#
# چرا این فایل هست: «سبز است» دو معنا داشت. من محلی `ruff check app` می‌زدم و
# CI `ruff check .` — پس یک فایلِ تستِ تازه lint نشده رفت بالا و CI روی lint
# قرمز شد، در حالی که هر ۱۰۲۹ تست سبز بود. خطا در کد نبود؛ در *اختلافِ دو
# فهرستِ فرمان* بود.
#
# پس اینجا تنها یک قاعده دارد: **هر فرمان باید کلمه‌به‌کلمه همان باشد که در
# `.github/workflows/ci.yml` هست.** اگر آن فایل عوض شد، این هم باید عوض شود؛
# و `--check-drift` همین را می‌سنجد تا فراموش‌شدنش بی‌صدا نماند.
#
# استفاده:
#   scripts/ci-local.sh                # چهار کار، به ترتیبِ ارزانی
#   scripts/ci-local.sh backend        # فقط یک کار (backend|launcher|frontend|e2e)
#   scripts/ci-local.sh --check-drift  # فقط بسنج که فرمان‌ها با ci.yml یکی‌اند
#
# کارِ `e2e` دیتابیسِ `nexahr` را *دور می‌ریزد و از نو می‌سازد*، چون یک‌بار
# سبزیِ دروغین از ردیف‌های اجرای قبلی گرفتیم. برای همین در اجرای پیش‌فرض هم
# هست ولی آخر می‌آید.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/backend/.venv/bin"
[ -x "$VENV/python" ] && export PATH="$VENV:$PATH"

FAILED=()
PASSED=()

c_red=$'\e[31m'; c_green=$'\e[32m'; c_dim=$'\e[2m'; c_bold=$'\e[1m'; c_off=$'\e[0m'

step() { printf '\n%s── %s %s\n' "$c_bold" "$1" "$c_off"; }

# اجرا می‌کند و *ادامه می‌دهد*: خواستنِ فهرستِ کاملِ خرابی‌ها در یک اجرا، کلِ
# هدفِ این اسکریپت است. `set -e` اولین شکست را نشان می‌داد و بقیه پنهان می‌ماند.
run_in() {
  local dir="$1"; shift
  printf '%s$ (%s) %s%s\n' "$c_dim" "$dir" "$*" "$c_off"
  ( cd "$ROOT/$dir" && "$@" )
  local code=$?
  if [ $code -ne 0 ]; then
    FAILED+=("($dir) $* → exit $code")
  else
    PASSED+=("($dir) $*")
  fi
  return 0
}

job_backend() {
  step "backend — ruff check . + pytest -q"
  run_in backend ruff check .
  run_in backend python -m pytest -q
}

job_launcher() {
  step "launcher — ruff check tools + pytest tools/tests -q"
  run_in . ruff check tools
  run_in . python -m pytest tools/tests -q
}

job_frontend() {
  step "frontend — npm run lint + npm test + npm run build"
  run_in frontend npm run lint
  run_in frontend npm test
  run_in frontend npm run build
}

job_e2e() {
  step "e2e-api — دیتابیسِ تازه، سپس سناریوی سرتاسری"
  # دیتابیسِ CI هر بار نو است. اگر این‌جا نو نباشد، ردیف‌های اجرای قبلی
  # ادعاهای سناریو را سبز نگه می‌دارند — همان اشتباهی که یک‌بار افتاد.
  export PGPASSWORD=nexahr_dev_password
  psql -U nexahr -h localhost -d postgres -c "DROP DATABASE IF EXISTS nexahr;" >/dev/null || {
    FAILED+=("(e2e) دیتابیس نتوانست پاک شود — Postgres روشن است؟")
    return 0
  }
  psql -U nexahr -h localhost -d postgres -c "CREATE DATABASE nexahr;" >/dev/null

  export DATABASE_URL="postgresql+psycopg://nexahr:nexahr_dev_password@localhost:5432/nexahr"
  export ENVIRONMENT=development
  export JWT_SECRET_KEY=ci-test-secret-key-not-for-production
  export ENABLE_SCHEDULER=false
  export BOOTSTRAP_ADMIN=false

  run_in backend alembic upgrade head
  run_in . python3 e2e/setup_e2e.py
  run_in . bash e2e/run_e2e.sh --api-only
}

#: فرمان‌هایی که باید در `ci.yml` پیدا شوند. اگر کسی آن‌جا فرمانی را عوض کرد و
#: این‌جا نه، `--check-drift` می‌گیردش — وگرنه این اسکریپت دقیقاً همان دامی
#: می‌شد که برای رفعش نوشته شده: یک «سبزِ» محلی که معنایش با CI فرق دارد.
CI_COMMANDS=(
  "ruff check ."
  "pytest -q"
  "ruff check tools"
  "python -m pytest tools/tests -q"
  "alembic upgrade head"
  "python3 e2e/setup_e2e.py"
  "bash e2e/run_e2e.sh --api-only"
  "npm run lint"
  "npm test"
  "npm run build"
)

check_drift() {
  local workflow="$ROOT/.github/workflows/ci.yml"
  local missing=0
  step "drift — فرمان‌های این اسکریپت در ci.yml هستند؟"
  for cmd in "${CI_COMMANDS[@]}"; do
    if grep -qF -- "$cmd" "$workflow"; then
      printf '  %s✓%s %s\n' "$c_green" "$c_off" "$cmd"
    else
      printf '  %s✗%s %s  ← در ci.yml نیست\n' "$c_red" "$c_off" "$cmd"
      missing=1
    fi
  done
  # و برعکس: هر `- run:` در ci.yml باید این‌جا پوشیده باشد.
  #
  # گام‌های *نصب* (`pip install`، `npm ci`) بیرون می‌مانند: آن‌ها چیزی
  # نمی‌سنجند و محلی از قبل انجام شده‌اند (venv و node_modules). هر فرمانِ
  # دیگری که در ci.yml اضافه شود، این‌جا صدا در می‌آورد.
  while IFS= read -r cmd; do
    [ -z "$cmd" ] && continue
    local found=0
    for known in "${CI_COMMANDS[@]}"; do
      [ "$known" = "$cmd" ] && found=1 && break
    done
    if [ $found -eq 0 ]; then
      printf '  %s✗%s %s  ← در ci.yml هست ولی این اسکریپت اجرایش نمی‌کند\n' \
        "$c_red" "$c_off" "$cmd"
      missing=1
    fi
  done < <(grep -oP '^\s*-\s+run:\s+\K.*' "$workflow" | grep -vE '^(pip install|npm ci)')
  return $missing
}

case "${1:-all}" in
  --check-drift) check_drift; exit $? ;;
  backend)  job_backend ;;
  launcher) job_launcher ;;
  frontend) job_frontend ;;
  e2e)      job_e2e ;;
  all)
    check_drift || FAILED+=("drift: فرمان‌های این اسکریپت با ci.yml یکی نیستند")
    job_launcher   # ارزان‌ترین، پس اول
    job_backend
    job_frontend
    job_e2e        # گران‌ترین و دیتابیس را دور می‌ریزد، پس آخر
    ;;
  *)
    echo "کارِ ناشناخته: $1 (backend|launcher|frontend|e2e|all|--check-drift)" >&2
    exit 2
    ;;
esac

step "خلاصه"
for line in "${PASSED[@]}"; do printf '  %s✓%s %s\n' "$c_green" "$c_off" "$line"; done
if [ ${#FAILED[@]} -eq 0 ]; then
  printf '\n%s✓ همان چیزی که CI می‌سنجد، این‌جا سبز است.%s\n' "$c_green" "$c_off"
  exit 0
fi
printf '\n'
for line in "${FAILED[@]}"; do printf '  %s✗%s %s\n' "$c_red" "$c_off" "$line"; done
printf '\n%s✗ %d مورد شکست خورد.%s\n' "$c_red" "${#FAILED[@]}" "$c_off"
exit 1
