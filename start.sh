#!/bin/bash
# Start command for Render deployment
gunicorn mqtt_bridge:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
