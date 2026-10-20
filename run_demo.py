#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Orquesta las rondas HTTP con uno, dos y tres clientes de laboratorio."""

from __future__ import print_function

import argparse
import csv
import errno
import os
import subprocess
import sys
import time

from common import CONTROL_PORT, is_lab_target


HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def open_csv(path, mode):
    if sys.version_info[0] == 2:
        return open(path, mode + "b")
    return open(path, mode, newline="", encoding="utf-8")


def ensure_directory(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno != errno.EEXIST or not os.path.isdir(path):
            raise


def wait_for_process(process, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            return True
        time.sleep(0.1)
    return process.poll() is not None


def read_round_csv(path):
    """Devuelve (pico_rps, pico_kbps, max_ips, max_zombis)."""
    peak_rps = peak_kbps = 0.0
    max_ips = max_zombis = 0
    try:
        with open_csv(path, "r") as csv_file:
            for row in csv.DictReader(csv_file):
                peak_rps = max(peak_rps, float(row["rps"]))
                peak_kbps = max(peak_kbps, float(row["kbps"]))
                max_ips = max(max_ips, int(row["ips"]))
                max_zombis = max(max_zombis, int(row["zombis"]))
    except IOError as exc:
        if exc.errno != errno.ENOENT:
            raise
    return peak_rps, peak_kbps, max_ips, max_zombis


def main():
    parser = argparse.ArgumentParser(description="Orquesta la demo 1->2->3 y vuelca CSV.")
    parser.add_argument("-t", "--target", default="127.0.0.1", help="IP privada/loopback del servidor")
    parser.add_argument("-p", "--port", type=int, default=9999, help="Puerto HTTP del servidor")
    parser.add_argument("--rounds", type=int, default=3, help="Numero de rondas / clientes maximos")
    parser.add_argument("-d", "--duration", type=int, default=6, help="Duracion de cada prueba en segundos")
    parser.add_argument("--rps", type=int, default=20, help="Solicitudes HTTP/s por cliente (max. 100)")
    parser.add_argument("--size", type=int, default=500, help="Tamano del cuerpo HTTP en bytes")
    parser.add_argument("--broadcast", default="255.255.255.255", help="Direccion de broadcast")
    parser.add_argument("--control-port", type=int, default=CONTROL_PORT, help="Puerto de control C2")
    parser.add_argument("--out", default=os.path.join(HERE, "results"), help="Carpeta de salida")
    args = parser.parse_args()

    if not is_lab_target(args.target):
        print("[!] Objetivo {} no es privado/loopback. Abortando.".format(args.target))
        return 1

    ensure_directory(args.out)
    logs_dir = os.path.join(args.out, "zombie_logs")
    ensure_directory(logs_dir)

    zombies = []
    zombie_logs = []
    summary_rows = []

    def spawn_zombie(idx):
        log = open(os.path.join(logs_dir, "zombie-{}.log".format(idx)), "w")
        process = subprocess.Popen(
            [
                PY,
                "-u",
                os.path.join(HERE, "zombie.py"),
                "--id",
                "zombie-{}".format(idx),
                "--control-port",
                str(args.control_port),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        zombies.append(process)
        zombie_logs.append(log)
        print("[demo] Zombi zombie-{} en marcha (PID {}).".format(idx, process.pid))

    try:
        for round_number in range(1, args.rounds + 1):
            print("\n======== RONDA {}: {} zombi(s) ========".format(round_number, round_number))
            while len(zombies) < round_number:
                spawn_zombie(len(zombies) + 1)
            time.sleep(1.5)

            round_csv = os.path.join(args.out, "ronda_{}.csv".format(round_number))
            run_seconds = args.duration + 3
            victim = subprocess.Popen(
                [
                    PY,
                    "-u",
                    os.path.join(HERE, "victim.py"),
                    "--port",
                    str(args.port),
                    "--csv",
                    round_csv,
                    "--label",
                    "ronda-{}".format(round_number),
                    "--run-seconds",
                    str(run_seconds),
                ]
            )
            time.sleep(1.2)

            print("[demo] Lanzando prueba HTTP ({} zombis, {}s)...".format(round_number, args.duration))
            subprocess.call([
                PY,
                os.path.join(HERE, "commander.py"),
                "--target",
                args.target,
                "--port",
                str(args.port),
                "--duration",
                str(args.duration),
                "--rps",
                str(args.rps),
                "--size",
                str(args.size),
                "--broadcast",
                args.broadcast,
                "--control-port",
                str(args.control_port),
            ])

            if not wait_for_process(victim, run_seconds + 10):
                victim.kill()
                victim.wait()
                raise RuntimeError("La victima HTTP no termino dentro del tiempo esperado")

            peak_rps, peak_kbps, max_ips, max_zombis = read_round_csv(round_csv)
            summary_rows.append({
                "ronda": round_number,
                "zombis_lanzados": round_number,
                "pico_rps": round(peak_rps),
                "pico_kbps": round(peak_kbps, 1),
                "ips_detectadas": max_ips,
                "clientes_detectados": max_zombis,
                "csv": os.path.basename(round_csv),
            })
            print(
                "[demo] Ronda {}: pico {:,.0f} rps, {:,.1f} KB/s, {} IP(s), "
                "{} cliente(s). -> {}".format(
                    round_number,
                    peak_rps,
                    peak_kbps,
                    max_ips,
                    max_zombis,
                    os.path.basename(round_csv),
                )
            )
            time.sleep(2)
    finally:
        for process in zombies:
            process.terminate()
        for process in zombies:
            if not wait_for_process(process, 3):
                process.kill()
                process.wait()
        for log in zombie_logs:
            log.close()

    summary_path = os.path.join(args.out, "resumen.csv")
    with open_csv(summary_path, "w") as summary_file:
        writer = csv.DictWriter(summary_file, fieldnames=[
            "ronda",
            "zombis_lanzados",
            "pico_rps",
            "pico_kbps",
            "ips_detectadas",
            "clientes_detectados",
            "csv",
        ])
        writer.writeheader()
        writer.writerows(summary_rows)

    print("\n======== RESUMEN ========")
    print("{:>5} | {:>6} | {:>10} | {:>10} | {:>4} | {:>9}".format(
        "ronda", "zombis", "pico rps", "pico KB/s", "IPs", "clientes"
    ))
    for row in summary_rows:
        print("{:>5} | {:>6} | {:>10,} | {:>10,.1f} | {:>4} | {:>9}".format(
            row["ronda"],
            row["zombis_lanzados"],
            row["pico_rps"],
            row["pico_kbps"],
            row["ips_detectadas"],
            row["clientes_detectados"],
        ))
    print("\n[demo] CSV por ronda y resumen.csv en: {}".format(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
