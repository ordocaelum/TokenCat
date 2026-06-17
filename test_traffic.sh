#!/usr/bin/env bash
set -euo pipefail
if [[ ! -f .env.local ]]; then
  echo "❌ Error: .env.local missing. Copy .env.local.example to .env.local and update configuration keys." >&2
  exit 1
fi
# Source verbatim (preserves '=', quotes, and special chars in secrets).
set -a; source .env.local; set +a
: "${TOKENCAT_API_KEY:?TOKENCAT_API_KEY must be set in .env.local}"
echo "🐳 Spinning up container resources..."
docker compose --env-file .env.local up -d --build
echo "📡 Monitoring gateway heartbeat availability..."
until curl -s http://localhost:8080/dashboard > /dev/null; do
  sleep 2
done
echo "🚀 Dispatching mock verification payload..."
curl -N -X POST http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer ${TOKENCAT_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [
      {"role": "system", "content": "You are a dense technical translator. Return code snippets clean."},
      {"role": "user", "content": "Write a python matrix generation routine. Explain performance scaling benchmarks using verbose documentation commentary inside the payload."}
    ],
    "stream": true
  }'
echo -e "\n\n📊 Complete. Inspect dashboard panel metrics live at: http://localhost:8080/dashboard"
