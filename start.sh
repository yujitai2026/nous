#!/bin/bash
# Nous 神智 启动脚本
cd "$(dirname "$0")"
export DASHSCOPE_API_KEY=$(grep api_key /home/agentuser/persona-chat/app.py | head -1 | sed 's/.*api_key="\(.*\)".*/\1/')
export JWT_SECRET="nous-$(hostname)-secret-2024"
mkdir -p logs data
exec ./venv/bin/uvicorn src.app:app --host 0.0.0.0 --port 8767 --log-level info
