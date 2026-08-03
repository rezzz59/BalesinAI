#!/bin/bash
cd "$(dirname "$0")"

# Kill existing processes
pkill -f "uvicorn app.main" 2>/dev/null
pkill -f "ngrok http 8000" 2>/dev/null
sleep 1

# Start uvicorn
nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
echo "Starting uvicorn..."
sleep 2

# Start ngrok
nohup ngrok http 8000 --log=stdout > /tmp/ngrok.log 2>&1 &
echo "Starting ngrok..."
sleep 5

# Get URL
echo ""
echo "=== SETUP COMPLETE ==="
curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    for t in d['tunnels']:
        print(f'Webhook URL: {t[\"public_url\"]}/webhook/whatsapp/')
except:
    print('Fetching URL from ngrok log...')
" || tail -3 /tmp/ngrok.log

echo ""
echo "=== NEXT STEPS ==="
echo "1. Copy the Webhook URL above"
echo "2. Go to https://dashboard.fonnte.com"
echo "3. Settings → Webhook"
echo "4. Set Webhook URL to: https://sofia-unprocreated-magdalen.ngrok-free.dev/webhook/whatsapp/"
echo "5. (Optional) Add Header: Authorization if needed"
echo "6. (Optional) Add Header: X-Tenant-ID if needed"
echo "======================"
