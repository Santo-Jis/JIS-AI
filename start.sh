#!/bin/bash
# ============================================================
# JIS-AI — Python FastAPI + Node.js Baileys একসাথে চালাও
# Railway এ এই script দিয়ে দুটো service শুরু হবে
# ============================================================

echo "🚀 JIS-AI starting..."

# Node.js dependencies install (প্রথমবার)
echo "📦 Baileys dependencies install করছি..."
cd baileys && npm install --production && cd ..

# Baileys gateway background এ চালাও
echo "📱 Baileys Gateway শুরু হচ্ছে (port 3001)..."
node baileys/index.js &
BAILEYS_PID=$!

# একটু অপেক্ষা করো
sleep 3

# FastAPI চালাও
echo "🐍 FastAPI শুরু হচ্ছে (port 8000)..."
python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}

# FastAPI বন্ধ হলে Baileys ও বন্ধ করো
kill $BAILEYS_PID
