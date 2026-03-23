#!/bin/bash

echo "========================================="
echo "🏀 Starting Hoops Reporter App 🏀"
echo "========================================="

# Stop script on error
set -e

# Start FastAPI Backend in the background
echo "Starting FastAPI Backend (Port 8000)..."
source myvenv/bin/activate
python backend/server.py &
BACKEND_PID=$!

# Wait a couple seconds for it to boot
sleep 2

# Start Frontend Server in the background
echo "Starting Frontend UI (Port 8080)..."
cd frontend
python3 -m http.server 8080 &
FRONTEND_PID=$!

echo "========================================="
echo "✅ System Online!"
echo "👉 Open your browser to: http://localhost:8080"
echo "========================================="
echo "(Press Ctrl+C to stop both servers)"

# Wait for user interrupt
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait
