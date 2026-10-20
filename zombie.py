#!/usr/bin/env python3
"""Cliente de carga HTTP controlada para el laboratorio."""

import argparse
import http.client
import json
import socket
import threading
import time

from common import (
    CAMPAIGN_TOKEN,
    CONTROL_PORT,
    HTTP_PATH,
    MAX_DURATION,
    MAX_RPS,
    MAX_SIZE,
    clamp,
    is_lab_target,
)


def send_http_post(
    connection: http.client.HTTPConnection,
    payload: bytes,
    zombie_id: str,
) -> int:
    connection.request(
        "POST",
        HTTP_PATH,
        body=payload,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Lab-Token": CAMPAIGN_TOKEN,
            "X-Lab-Zombie": zombie_id,
        },
    )
    response = connection.getresponse()
    response.read()
    return response.status


class Attacker:
    """Genera solicitudes HTTP con ritmo limitado; una prueba a la vez."""

    def __init__(self, zombie_id: str):
        self.zombie_id = zombie_id
        self._stop = threading.Event()
        self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, target_ip: str, target_port: int, duration: int, rps: int, size: int):
        if self.is_running():
            print(f"[{self.zombie_id}] Ya hay una prueba en curso; ignoro la nueva orden.")
            return
        duration = clamp(duration, 1, MAX_DURATION)
        rps = clamp(rps, 1, MAX_RPS)
        size = clamp(size, 1, MAX_SIZE)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(target_ip, target_port, duration, rps, size),
            daemon=True,
        )
        self._thread.start()

    def _run(self, target_ip: str, target_port: int, duration: int, rps: int, size: int):
        payload = b"X" * size
        interval = 1.0 / rps
        sent = 0
        started_at = time.monotonic()
        deadline = started_at + duration
        next_tick = started_at
        connection = http.client.HTTPConnection(target_ip, target_port, timeout=2)

        print(
            f"[{self.zombie_id}] >>> Prueba HTTP a http://{target_ip}:{target_port}{HTTP_PATH} "
            f"durante {duration}s (~{rps} rps, {size}B)"
        )
        try:
            while time.monotonic() < deadline and not self._stop.is_set():
                try:
                    status = send_http_post(connection, payload, self.zombie_id)
                    if status == 204:
                        sent += 1
                except (OSError, http.client.HTTPException):
                    connection.close()
                    connection = http.client.HTTPConnection(target_ip, target_port, timeout=2)

                next_tick += interval
                sleep_seconds = next_tick - time.monotonic()
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
        finally:
            connection.close()
            elapsed = max(time.monotonic() - started_at, 1e-6)
            print(
                f"[{self.zombie_id}] <<< Fin. Completadas {sent} solicitudes "
                f"({sent / elapsed:,.1f} rps reales)."
            )

    def stop(self):
        self._stop.set()


def listen(zombie_id: str, control_port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", control_port))
    attacker = Attacker(zombie_id)

    print(f"[{zombie_id}] Escuchando ordenes del C2 en UDP/{control_port}. Ctrl+C para salir.")
    try:
        while True:
            data, addr = sock.recvfrom(65535)
            try:
                order = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue

            if not isinstance(order, dict):
                continue
            if order.get("token") != CAMPAIGN_TOKEN:
                continue
            if order.get("cmd") != "http_load_test":
                continue

            target_ip = str(order.get("target_ip", ""))
            if not is_lab_target(target_ip):
                print(f"[{zombie_id}] Orden rechazada: {target_ip} no es objetivo de laboratorio.")
                continue

            try:
                target_port = int(order.get("target_port", 0))
                duration = int(order.get("duration", 10))
                rps = int(order.get("rps", 20))
                size = int(order.get("size", 512))
            except (TypeError, ValueError):
                print(f"[{zombie_id}] Orden descartada: parametros numericos invalidos.")
                continue

            if not (0 < target_port < 65536):
                print(f"[{zombie_id}] Orden descartada: puerto invalido ({target_port}).")
                continue

            print(f"[{zombie_id}] Orden HTTP recibida de {addr[0]}.")
            attacker.start(target_ip, target_port, duration, rps, size)
    except KeyboardInterrupt:
        print(f"\n[{zombie_id}] Saliendo.")
    finally:
        attacker.stop()
        sock.close()


def main():
    parser = argparse.ArgumentParser(description="Cliente HTTP de laboratorio.")
    parser.add_argument("--id", default="zombie", help="Identificador para las metricas")
    parser.add_argument(
        "--control-port",
        type=int,
        default=CONTROL_PORT,
        help=f"Puerto UDP de control (def. {CONTROL_PORT})",
    )
    args = parser.parse_args()
    listen(args.id, args.control_port)


if __name__ == "__main__":
    main()
