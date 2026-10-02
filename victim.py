#!/usr/bin/env python3
"""
victim.py - Victima del PoC: receptor UDP que mide el trafico entrante.

Se ejecuta en la maquina objetivo del laboratorio. Cuenta paquetes y bytes por
segundo, de modo que puedas cotejar en consola lo mismo que observas en Wireshark
(IO Graphs). Con 1 zombi veras X pps; con 2, ~2X; con 3, ~3X.

Uso:
    python victim.py --port 9999
    python victim.py --port 9999 --csv medidas.csv --run-seconds 15 --label ronda-1
"""

import argparse
import csv
import socket
import time


def main():
    p = argparse.ArgumentParser(description="Victima/medidor UDP (PoC educativo).")
    p.add_argument("-p", "--port", type=int, required=True, help="Puerto UDP en el que escuchar")
    p.add_argument("--bind", default="0.0.0.0", help="Interfaz en la que escuchar (def. 0.0.0.0)")
    p.add_argument("--csv", default=None, help="Ruta de un CSV donde volcar una fila por segundo")
    p.add_argument("--label", default="", help="Etiqueta que se escribe en cada fila del CSV (p.ej. ronda-1)")
    p.add_argument("--run-seconds", type=int, default=0,
                   help="Si > 0, termina automaticamente tras esos segundos (para orquestacion)")
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

    csv_file = None
    csv_writer = None
    if args.csv:
        csv_file = open(args.csv, "w", newline="", encoding="utf-8")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["label", "epoch", "segundo", "pps", "kbps", "ips", "zombis"])

    print(f"[victima] Escuchando UDP en {args.bind}:{args.port}. Ctrl+C para salir.")
    # "zombis" = nº de endpoints (IP, puerto) distintos: asi se distinguen varios
    # zombis en la MISMA maquina (comparten IP pero usan puertos de origen distintos).
    print(f"[victima] {'tiempo':>8} | {'paquetes/s':>12} | {'KB/s':>10} | {'IPs':>5} | {'zombis':>6}")

    window_pkts = 0
    window_bytes = 0
    source_ips = set()
    source_endpoints = set()
    t0 = time.time()
    last_report = t0

    try:
        while True:
            try:
                data, addr = sock.recvfrom(65535)
                window_pkts += 1
                window_bytes += len(data)
                source_ips.add(addr[0])
                source_endpoints.add(addr)  # (ip, puerto_origen)
            except socket.timeout:
                pass

            now = time.time()
            if now - last_report >= 1.0:
                dt = now - last_report
                pps = window_pkts / dt
                kbps = window_bytes / 1024 / dt
                segundo = now - t0
                print(f"[victima] {segundo:>7.0f}s | {pps:>12,.0f} | {kbps:>10,.1f} | "
                      f"{len(source_ips):>5} | {len(source_endpoints):>6}")
                if csv_writer:
                    csv_writer.writerow([
                        args.label, f"{now:.3f}", f"{segundo:.0f}", f"{pps:.0f}",
                        f"{kbps:.1f}", len(source_ips), len(source_endpoints),
                    ])
                    csv_file.flush()  # fila a disco ya, para no perder datos si se corta
                window_pkts = 0
                window_bytes = 0
                source_ips.clear()
                source_endpoints.clear()
                last_report = now

            if args.run_seconds and (now - t0) >= args.run_seconds:
                print(f"[victima] Fin automatico tras {args.run_seconds}s.")
                break
    except KeyboardInterrupt:
        print("\n[victima] Saliendo.")
    finally:
        sock.close()
        if csv_file:
            csv_file.close()


if __name__ == "__main__":
    main()
