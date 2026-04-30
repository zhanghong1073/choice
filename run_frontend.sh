#!/usr/bin/env bash
set -e
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
