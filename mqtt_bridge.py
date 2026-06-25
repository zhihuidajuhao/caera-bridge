#!/usr/bin/env python3
"""
MQTT ↔ HTTP Bridge for Caera AI Camera — Render deployment version

Deploy on Render (free tier) for 24/7 cloud relay.
Flutter App polls this service via HTTP, no MQTT library needed on mobile.

Environment variables:
    PORT        — HTTP port (set by Render automatically, default 5000)
    MQTT_BROKER — MQTT broker address (default: broker.hivemq.com)
    MQTT_PORT   — MQTT broker port (default: 1883)
"""

import json
import os
import time
import threading
from flask import Flask, request, jsonify
import paho.mqtt.client as mqtt

app = Flask(__name__)

# ─── Configuration ─────────────────────────────────────────────
HTTP_PORT = int(os.environ.get("PORT", 5000))
MQTT_BROKER = os.environ.get("MQTT_BROKER", "broker.hivemq.com")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))

# ─── Shared state ──────────────────────────────────────────────
_latest_status = {
    "status": "offline",
    "device": "caera",
    "last_seen": 0,
}
_latest_detections = None
_lock = threading.Lock()


# ─── MQTT ──────────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc, props=None):
    print(f"[Bridge] MQTT connected (rc={rc})", flush=True)
    client.subscribe("caera/status")
    client.subscribe("caera/detections")
    print("[Bridge] Subscribed: caera/status, caera/detections", flush=True)


def on_message(client, userdata, msg):
    global _latest_status, _latest_detections
    try:
        payload = json.loads(msg.payload.decode())
        with _lock:
            if msg.topic == "caera/status":
                payload["last_seen"] = time.time()
                _latest_status = payload
                print(f"[Bridge] Heartbeat: RSSI={payload.get('rssi','?')} "
                      f"uptime={payload.get('uptime','?')}s", flush=True)
            elif msg.topic == "caera/detections":
                _latest_detections = payload
                print(f"[Bridge] Detections: {payload.get('total',0)} fruit(s)", flush=True)
    except Exception as e:
        print(f"[Bridge] MQTT error: {e}", flush=True)


mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message


def start_mqtt():
    print(f"[Bridge] Connecting MQTT → {MQTT_BROKER}:{MQTT_PORT}", flush=True)
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()
    print("[Bridge] MQTT loop started.", flush=True)


# ─── HTTP Endpoints ────────────────────────────────────────────
@app.route("/status")
def get_status():
    with _lock:
        return jsonify(_latest_status)


@app.route("/detections")
def get_detections():
    with _lock:
        return jsonify(_latest_detections)


@app.route("/command", methods=["POST"])
def post_command():
    data = request.get_json(force=True)
    cmd = data.get("cmd")
    if not cmd:
        return jsonify({"error": "missing 'cmd'"}), 400

    cmd_payload = {"cmd": cmd}
    if "value" in data:
        cmd_payload["value"] = data["value"]

    mqtt_client.publish("caera/control", json.dumps(cmd_payload))
    print(f"[Bridge] Sent: {cmd_payload}", flush=True)
    return jsonify({"ok": True, "cmd": cmd})


@app.route("/health")
def health():
    since_last = time.time() - _latest_status.get("last_seen", 0)
    return jsonify({
        "bridge": "ok",
        "device_online": since_last < 90,
    })


# ─── Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    start_mqtt()
    print(f"[Bridge] HTTP → http://0.0.0.0:{HTTP_PORT}", flush=True)
    app.run(host="0.0.0.0", port=HTTP_PORT, debug=False)
