#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cliente de carga HTTP controlada para el laboratorio."""

from __future__ import print_function

import argparse
try:
    import http.client as http_client
except ImportError:
    import httplib as http_client
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


def send_http_post(connection, payload, zombie_id):
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


class Attacker(object):
    """Genera solicitudes HTTP con ritmo limitado; una prueba a la vez."""

    def __init__(self, zombie_id):
        self.zombie_id = zombie_id
        self._stop = threading.Event()
        self._thread = None

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, target_ip, target_port, duration, rps, size):
        if self.is_running():
            print("[{}] Ya hay una prueba en curso; ignoro la nueva orden.".format(self.zombie_id))
            return
        duration = clamp(duration, 1, MAX_DURATION)
        rps = clamp(rps, 1, MAX_RPS)
        size = clamp(size, 1, MAX_SIZE)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(target_ip, target_port, duration, rps, size),
        )
        self._thread.daemon = True
        self._thread.start()

    def _run(self, target_ip, target_port, duration, rps, size):
        payload = b"X" * size
        interval = 1.0 / rps
        sent = 0
        started_at = time.time()
        deadline = started_at + duration
        next_tick = started_at
        connection = http_client.HTTPConnection(target_ip, target_port, timeout=2)

        print(
            "[{}] >>> Prueba HTTP a http://{}:{}{} durante {}s (~{} rps, {}B)".format(
                self.zombie_id,
                target_ip,
                target_port,
                HTTP_PATH,
                duration,
                rps,
                size,
            )
        )
        try:
            while time.time() < deadline and not self._stop.is_set():
                try:
                    status = send_http_post(connection, payload, self.zombie_id)
                    if status == 204:
                        sent += 1
                except (OSError, http_client.HTTPException):
                    connection.close()
                    connection = http_client.HTTPConnection(target_ip, target_port, timeout=2)

                next_tick += interval
                sleep_seconds = next_tick - time.time()
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
        finally:
            connection.close()
            elapsed = max(time.time() - started_at, 1e-6)
            print(
                "[{}] <<< Fin. Completadas {} solicitudes ({:,.1f} rps reales).".format(
                    self.zombie_id, sent, sent / elapsed
                )
            )

    def stop(self):
        self._stop.set()


def listen(zombie_id, control_port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", control_port))
    attacker = Attacker(zombie_id)

    print("[{}] Escuchando ordenes del C2 en UDP/{}. Ctrl+C para salir.".format(zombie_id, control_port))
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
                print("[{}] Orden rechazada: {} no es objetivo de laboratorio.".format(zombie_id, target_ip))
                continue

            try:
                target_port = int(order.get("target_port", 0))
                duration = int(order.get("duration", 10))
                rps = int(order.get("rps", 20))
                size = int(order.get("size", 512))
            except (TypeError, ValueError):
                print("[{}] Orden descartada: parametros numericos invalidos.".format(zombie_id))
                continue

            if not (0 < target_port < 65536):
                print("[{}] Orden descartada: puerto invalido ({}).".format(zombie_id, target_port))
                continue

            print("[{}] Orden HTTP recibida de {}.".format(zombie_id, addr[0]))
            attacker.start(target_ip, target_port, duration, rps, size)
    except KeyboardInterrupt:
        print("\n[{}] Saliendo.".format(zombie_id))
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
        help="Puerto UDP de control (def. {})".format(CONTROL_PORT),
    )
    args = parser.parse_args()
    listen(args.id, args.control_port)


if __name__ == "__main__":
    main()
