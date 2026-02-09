#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python app.py & python bot_runner.py
