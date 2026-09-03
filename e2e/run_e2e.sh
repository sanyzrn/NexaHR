#!/bin/bash
# اجرای کلِ محیطِ همکار + سناریوی سرتسری در یک نشست:
#   ./run_e2e.sh --api-only   → فقط سناریوی API (بی مرورگر، بی vite)
#   ./run_e2e.sh              → سرورها را بالا نگه می‌دارد تا خودتان در مرورگر ببینید
#
# پیش‌نیازها: دیتابیسِ آمادهٔ مایگریشن + «python3 e2e/setup_e2e.py» که یک‌بار اجرا شده باشد.
#
# `--api-only` عمداً *فرانت‌اند را بالا نمی‌آورد*: سناریوی API فقط با
# `127.0.0.1:8000` حرف می‌زند، و بالا آوردنِ vite برای آن یعنی `npm ci` و
# چند ده ثانیه بی هیچ سودی — همان چیزی که این سوئیت را از CI بیرون نگه
# داشته بود. با این تفکیک، اجرای API-only در CI یک کارِ سبک است.
set -e
API_ONLY=0
if [ "$1" = "--api-only" ]; then API_ONLY=1; fi
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://nexahr:nexahr_dev_password@localhost:5432/nexahr}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-dev-only-secret-change-me-0123456789abcdef}"
export ENABLE_SCHEDULER="${ENABLE_SCHEDULER:-false}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS="$(mktemp -d)"

cleanup() {
  pkill -f "uvicorn app.main:app" 2>/dev/null || true
  pkill -f "mock_llm.py" 2>/dev/null || true
  pkill -f "vite" 2>/dev/null || true
  fuser -k 8000/tcp 2>/dev/null || true
  fuser -k 8100/tcp 2>/dev/null || true
  fuser -k 5173/tcp 2>/dev/null || true
}
trap cleanup EXIT
cleanup || true
sleep 1

# مسیرها از `$ROOT` ساخته می‌شوند و نه از `dirname "$BASH_SOURCE"`: آن یکی
# *نسبی* است و اسکریپت وسطِ کار `cd` می‌کند. مسیرِ `--api-only` دقیقاً همین‌جا
# می‌شکست — و همان تنها مسیری بود که کسی خودکار اجرایش نمی‌کرد.
E2E="$ROOT/e2e"
python3 "$E2E/mock_llm.py" > "$LOGS/mock_llm.log" 2>&1 &
cd "$ROOT/backend"
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > "$LOGS/backend.log" 2>&1 &
if [ "$API_ONLY" = "0" ]; then
  cd "$ROOT/frontend"
  npm run dev -- --port 5173 --strictPort > "$LOGS/frontend.log" 2>&1 &
fi

# صبر تا بالا آمدن همه
for i in $(seq 1 30); do
  ok=1
  curl -s -o /dev/null http://127.0.0.1:8000/docs || ok=0
  if [ "$API_ONLY" = "0" ]; then
    curl -s -o /dev/null http://localhost:5173/ || ok=0
  fi
  if [ "$ok" = "1" ]; then break; fi
  sleep 1
done
MOCK_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8100/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"سلام"}]}')
FRONT_CODE="skipped"
if [ "$API_ONLY" = "0" ]; then
  FRONT_CODE=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:5173/)
fi
echo "servers up: backend=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/docs) frontend=$FRONT_CODE mock=$MOCK_CODE"
if [ "$MOCK_CODE" != "200" ]; then
  echo "MOCK LLM UNHEALTHY:"; tail -20 "$LOGS/mock_llm.log"; exit 1
fi

if [ "$API_ONLY" = "1" ]; then
  python3 "$E2E/e2e_api_test.py"
else
  echo "READY — backend :8000, frontend :5173, mock LLM :8100 (logs in $LOGS)"
  sleep 600
fi
