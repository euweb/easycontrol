#!/usr/bin/env python3
"""
debugmqtt.py – MQTT broker monitor
====================================
Reads broker credentials from a config.json and prints all incoming
messages on the configured basic_topic to the console.

Usage:
    python debugmqtt.py config.json
    python debugmqtt.py config-simulator.json
    python debugmqtt.py config.json --topic "home-assistant/#"
    python debugmqtt.py config.json --publish "home-assistant/cover/1/set" OPEN
"""

import argparse
import json
import signal
import sys
import time

import paho.mqtt.client as mqtt


def load_config(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[error] File not found: {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[error] Invalid JSON in {path}: {e}")
        sys.exit(1)


def on_connect(client, userdata, flags, reason_code, properties):
    topic = userdata["topic"]
    if reason_code == 0:
        print(f"[mqtt]  connected  →  {userdata['broker']}")
        print(f"[mqtt]  subscribed →  {topic}")
        print(f"[mqtt]  {'─' * 60}")
        client.subscribe(topic)
    else:
        print(f"[error] Connection failed: {reason_code}")
        sys.exit(1)


def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8", errors="replace")
    retained = " [retained]" if msg.retain else ""
    print(f"  {msg.topic}  →  {payload}{retained}")


def on_disconnect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        print(f"[mqtt]  connection lost (code {reason_code}), reconnecting …")


def main():
    parser = argparse.ArgumentParser(
        description="MQTT debug monitor – prints all messages on the configured topic."
    )
    parser.add_argument("config", help="Path to config.json")
    parser.add_argument(
        "--topic",
        default=None,
        help="Override topic (default: basic_topic/# from config)",
    )
    parser.add_argument(
        "--publish",
        nargs=2,
        metavar=("TOPIC", "PAYLOAD"),
        help="Publish a single message and then keep listening",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    mqtt_cfg = cfg.get("mqtt", {})

    broker = mqtt_cfg.get("broker")
    port = int(mqtt_cfg.get("port", 1883))
    client_id = mqtt_cfg.get("client_id", "debugmqtt")
    username = mqtt_cfg.get("username")
    password = mqtt_cfg.get("password")
    basic_topic = mqtt_cfg.get("basic_topic", "#")

    subscribe_topic = args.topic if args.topic else f"{basic_topic}/#"

    print(f"[mqtt]  Broker    : {broker}:{port}")
    print(f"[mqtt]  Client-ID : {client_id}_debug")
    print(f"[mqtt]  Topic     : {subscribe_topic}")
    print()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"{client_id}_debug",
    )
    if username:
        client.username_pw_set(username, password)

    client.user_data_set({"broker": f"{broker}:{port}", "topic": subscribe_topic})
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    client.connect(broker, port, keepalive=60)

    if args.publish:
        pub_topic, pub_payload = args.publish
        # wait briefly until connected, then publish
        client.loop_start()
        time.sleep(1.0)
        client.publish(pub_topic, pub_payload)
        print(f"[mqtt]  published   →  {pub_topic}  :  {pub_payload}")
        client.loop_stop()
        client.loop_forever()
    else:
        def _shutdown(sig, frame):
            print("\n[mqtt]  Stopped.")
            client.disconnect()
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)
        client.loop_forever()


if __name__ == "__main__":
    main()
