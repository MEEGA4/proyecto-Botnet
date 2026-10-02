#!/usr/bin/env python3
"""
victim.py - Victima del PoC: receptor UDP que mide el trafico entrante.

Se ejecuta en la maquina objetivo del laboratorio. Cuenta paquetes y bytes por
segundo, de modo que puedas cotejar en consola lo mismo que observas en Wireshark
(IO Graphs). Con 1 zombi veras X pps; con 2, ~2X; con 3, ~3X.

Uso:
    python victim.py --port 9999
"""

import argparse
import socket
import time


def main():
    p = argparse.ArgumentParser(description="Victima/medidor UDP (PoC educativo).")
    p.add_argument("-p", "--port", type=int, required=True, help="Puerto UDP en el que escuchar")
    p.add_argument("--bind", default="0.0.0.0", help="Interfaz en la que escuchar (def. 0.0.0.0)")
    args = p.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Buffer de recepcion grande para no perder cuenta bajo rafagas.
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    except OSError:
        pass
    sock.bind((args.bind, args.port))
    sock.settimeout(1.0)

    print(f"[victima] Escuchando UDP en {args.bind}:{args.port}. Ctrl+C para salir.")
    print(f"[victima] {'tiempo':>8} | {'paquetes/s':>12} | {'KB/s':>10} | {'orígenes':>8}")

    window_pkts = 0
    window_bytes = 0
    sources = set()
    t0 = time.time()
    last_report = t0

    try:
        while True:
            try:
                data, addr = sock.recvfrom(65535)
                window_pkts += 1
                window_bytes += len(data)
                sources.add(addr[0])
            except socket.timeout:
                pass

            now = time.time()
            if now - last_report >= 1.0:
                dt = now - last_report
                print(f"[victima] {now - t0:>7.0f}s | {window_pkts / dt:>12,.0f} | "
                      f"{window_bytes / 1024 / dt:>10,.1f} | {len(sources):>8}")
                window_pkts = 0
                window_bytes = 0
                sources.clear()
                last_report = now
    except KeyboardInterrupt:
        print("\n[victima] Saliendo.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
