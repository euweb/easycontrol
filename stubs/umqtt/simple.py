"""
MicroPython `umqtt.simple` stub for CPython
============================================
Implements the same API as micropython-umqtt.simple,
backed by paho-mqtt internally.

Compatibility:
  - MQTTClient(client_id, server, port, user, password, keepalive, ssl, ssl_params)
  - connect() / disconnect()
  - set_callback(f)   → f(topic_bytes, payload_bytes)
  - subscribe(topic)
  - publish(topic, msg, retain, qos)
  - check_msg()       → paho handles messages in a background thread
  - wait_msg()        → short sleep, then return
"""

import paho.mqtt.client as _mqtt


class MQTTClient:
    def __init__(
        self,
        client_id,
        server,
        port=1883,
        user=None,
        password=None,
        keepalive=60,
        ssl=False,
        ssl_params=None,
    ):
        self._server = server
        self._port = port
        self._keepalive = keepalive or 60
        self._callback = None
        self._connected = False

        self._client = _mqtt.Client(
            _mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )

        if user:
            self._client.username_pw_set(user, password)

        def _on_message(mqttc, userdata, msg):
            if self._callback:
                # MicroPython delivers bytes for both topic and payload
                self._callback(msg.topic.encode(), msg.payload)

        self._client.on_message = _on_message

    # ── Public API (identical to umqtt.simple) ───────────────────────────────

    def set_callback(self, f):
        self._callback = f

    def set_last_will(self, topic, msg, retain=False, qos=0):
        if isinstance(msg, str):
            msg = msg.encode()
        self._client.will_set(topic, msg, qos=qos, retain=retain)

    def connect(self, clean_session=True):
        if self._connected:
            return  # handle duplicate connect() calls gracefully
        self._client.connect(self._server, self._port, self._keepalive)
        self._client.loop_start()  # receive messages in background thread
        self._connected = True
        print(f"[umqtt] connected to {self._server}:{self._port}")

    def disconnect(self):
        if self._connected:
            self._client.disconnect()
            self._client.loop_stop()
            self._connected = False

    def subscribe(self, topic, qos=0):
        self._client.subscribe(topic, qos)
        print(f"[umqtt] subscribed  {topic}")

    def publish(self, topic, msg, retain=False, qos=0):
        if isinstance(msg, str):
            msg = msg.encode()
        self._client.publish(topic, msg, qos=qos, retain=retain)

    def check_msg(self):
        """
        In umqtt.simple: blockiert kurz und verarbeitet eine Nachricht.
        Hier: no-op, da paho den Empfang in einem Hintergrund-Thread erledigt.
        """

    def wait_msg(self):
        import time
        time.sleep(0.05)
