#!/usr/bin/env python3
"""C2 de laboratorio para iniciar una prueba de carga HTTP acotada."""

import argparse
import json
import socket
import sys

from common import (
    CAMPAIGN_TOKEN,
    CONTROL_PORT,
    MAX_DURATION,
    MAX_RPS,
    MAX_SIZE,
    clamp,
    is_lab_target,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="C2 del laboratorio HTTP.")
    parser.add_argument("-t", "--target", required=True, help="IPv4 privada o loopback del servidor")
    parser.add_argument("-p", "--port", type=int, required=True, help="Puerto HTTP del servidor")
    parser.add_argument("-d", "--duration", type=int, default=10, help="Duracion en segundos")
    parser.add_argument("--rps", type=int, default=20, help="Solicitudes/seg por cliente (max. 100)")
    parser.add_argument("--size", type=int, default=512, help="Bytes del cuerpo de cada POST")
    parser.add_argument(
        "--broadcast",
        default="255.255.255.255",
        help="Direccion broadcast de la subred",
    )
    parser.add_argument(
        "--control-port",
        type=int,
        default=CONTROL_PORT,
        help=f"Puerto UDP donde escuchan los clientes (def. {CONTROL_PORT})",
    )
    return parser


def build_order(args: argparse.Namespace) -> dict:
    return {
        "cmd": "http_load_test",
        "target_ip": args.target,
        "target_port": args.port,
        "duration": clamp(args.duration, 1, MAX_DURATION),
        "rps": clamp(args.rps, 1, MAX_RPS),
        "size": clamp(args.size, 1, MAX_SIZE),
        "token": CAMPAIGN_TOKEN,
    }


def main() -> int:
    args = build_parser().parse_args()
    if not is_lab_target(args.target):
        print(f"[!] Objetivo rechazado: {args.target} no es una IPv4 privada/loopback.")
        print("    Esta prueba solo opera dentro de la red del laboratorio.")
        return 1
    if not (0 < args.port < 65536):
        print(f"[!] Puerto invalido: {args.port}")
        return 1

    order = build_order(args)
    payload = json.dumps(order).encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.sendto(payload, (args.broadcast, args.control_port))
    finally:
        sock.close()

    print("[*] Orden de prueba HTTP enviada por broadcast:")
    print(f"      broadcast  -> {args.broadcast}:{args.control_port}")
    print(f"      servidor   -> http://{args.target}:{args.port}/load-test")
    print(
        f"      duracion   -> {order['duration']}s   "
        f"rps/cliente -> {order['rps']}   cuerpo -> {order['size']}B"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
