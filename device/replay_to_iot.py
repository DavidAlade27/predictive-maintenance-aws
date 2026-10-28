"""
Publishes CWRU bearing vibration windows to AWS IoT Core over MQTT.

Run this on YOUR computer (not in this sandbox) — it needs network access
to your AWS account's IoT endpoint, which isn't reachable from here.

Install dependencies first:
    pip install awsiotsdk numpy

Fill in the CONFIG section below with your Thing's cert paths and endpoint,
then run:
    python replay_to_iot.py
"""
import json
import time
from datetime import datetime, timezone

import numpy as np
from awscrt import mqtt, io
from awsiot import mqtt_connection_builder

# ---------------- CONFIG: fill these in ----------------
ENDPOINT = "YOUR_ENDPOINT-ats.iot.eu-north-1.amazonaws.com"  # from IoT Core > Settings
CERT_PATH = "certs/YOUR_CERT_ID-certificate.pem.crt"
KEY_PATH = "certs/YOUR_CERT_ID-private.pem.key"
ROOT_CA_PATH = "certs/AmazonRootCA1.pem"
CLIENT_ID = "pdm_sensor_device"          # must match your Thing name
TOPIC = "pdm/telemetry"
import os, glob
_chosen = os.environ.get("DATA_FILE")
DATA_FILE = glob.glob(f"CWRU_Bearing_NumPy/Data/*/{_chosen}")[0] if _chosen else "CWRU_Bearing_NumPy/Data/1797 RPM/1797_IR_7_DE12.npz"  # swap to a fault file to simulate a failing bearing
LABEL = "healthy" if "Normal" in DATA_FILE else "faulty"
SAMPLE_RATE_HZ = 12000
SPEED_MULTIPLIER = 1.0   # 1.0 = real time (1 msg/sec). Raise it to replay faster while testing.
# ---------------------------------------------------------


def compute_window_stats(window: np.ndarray) -> dict:
    return {
        "mean": float(np.mean(window)),
        "std": float(np.std(window)),
        "rms": float(np.sqrt(np.mean(window ** 2))),
        "peak": float(np.max(np.abs(window))),
    }


def main():
    event_loop_group = io.EventLoopGroup(1)
    host_resolver = io.DefaultHostResolver(event_loop_group)
    client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint=ENDPOINT,
        cert_filepath=CERT_PATH,
        pri_key_filepath=KEY_PATH,
        ca_filepath=ROOT_CA_PATH,
        client_bootstrap=client_bootstrap,
        client_id=CLIENT_ID,
        clean_session=False,
        keep_alive_secs=30,
    )

    print(f"Connecting to {ENDPOINT} as '{CLIENT_ID}'...")
    connect_future = mqtt_connection.connect()
    connect_future.result()
    print("Connected.\n")

    data = np.load(DATA_FILE)
    signal = data["DE"].flatten()
    n_windows = len(signal) // SAMPLE_RATE_HZ
    print(f"Publishing {n_windows} windows from {DATA_FILE} to topic '{TOPIC}'\n")

    for i in [w for _ in range(int(os.environ.get("REPEATS", "1"))) for w in range(n_windows)]:
        window = signal[i * SAMPLE_RATE_HZ: (i + 1) * SAMPLE_RATE_HZ]
        message = {
            "device_id": CLIENT_ID,
            "label": LABEL,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "window_index": i,
            **compute_window_stats(window),
        }
        payload = json.dumps(message)
        mqtt_connection.publish(
            topic=TOPIC,
            payload=payload,
            qos=mqtt.QoS.AT_LEAST_ONCE,
        )
        print(f"Published: {payload}")
        time.sleep(1.0 / SPEED_MULTIPLIER)

    print("\nDone. Disconnecting...")
    mqtt_connection.disconnect().result()


if __name__ == "__main__":
    main()
