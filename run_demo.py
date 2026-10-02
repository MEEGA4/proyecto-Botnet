#!/usr/bin/env python3
"""
run_demo.py - Orquestador de la demo: ejecuta la secuencia 1 -> 2 -> 3 zombis y
vuelca los conteos de la victima a CSV (evidencias reproducibles).

Para cada ronda n:
  1. Asegura que hay n zombis en marcha (anade uno nuevo por ronda).
  2. Arranca la victima midiendo y volcando a results/ronda_n.csv.
  3. Envia la orden de ataque desde el comandante.
  4. Al terminar, calcula el pico de pps/KB/s y lo anota en results/resumen.csv.

Pensado para la OPCION B (todo en un PC) o como arranque local. En red real con
varias maquinas, lanza los zombis en cada maquina y usa commander.py directamente;
este script sirve igual si ejecutas la victima y el comandante en una de ellas.

Uso:
    python run_demo.py
    python run_demo.py --rounds 3 --duration 6 --pps 1000 --size 500 \
                       --target 127.0.0.1 --port 9999 --broadcast 255.255.255.255
"""

import argparse
import csv
import os
import subprocess
import sys
import time

from common import CONTROL_PORT, is_lab_target

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable  # mismo interprete que ejecuta este script


def read_round_csv(path):
    """Devuelve (pico_pps, pico_kbps, max_ips, max_zombis) de un CSV de ronda."""
    peak_pps = peak_kbps = 0.0
    max_ips = max_zombis = 0
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                peak_pps = max(peak_pps, float(row["pps"]))
                peak_kbps = max(peak_kbps, float(row["kbps"]))
                max_ips = max(max_ips, int(row["ips"]))
                max_zombis = max(max_zombis, int(row["zombis"]))
    except FileNotFoundError:
        pass
    return peak_pps, peak_kbps, max_ips, max_zombis


def main():
    p = argparse.ArgumentParser(description="Orquesta la demo 1->2->3 zombis y vuelca CSV.")
    p.add_argument("-t", "--target", default="127.0.0.1", help="IP victima (privada/loopback)")
    p.add_argument("-p", "--port", type=int, default=9999, help="Puerto UDP de la victima")
    p.add_argument("--rounds", type=int, default=3, help="Numero de rondas / zombis maximos (def. 3)")
    p.add_argument("-d", "--duration", type=int, default=6, help="Duracion de cada ataque en seg (def. 6)")
    p.add_argument("--pps", type=int, default=1000, help="pps por zombi (def. 1000)")
    p.add_argument("--size", type=int, default=500, help="Tamano del payload en bytes (def. 500)")
    p.add_argument("--broadcast", default="255.255.255.255", help="Direccion de broadcast")
    p.add_argument("--control-port", type=int, default=CONTROL_PORT, help="Puerto de control C2")
    p.add_argument("--out", default=os.path.join(HERE, "results"), help="Carpeta de salida")
    args = p.parse_args()

    if not is_lab_target(args.target):
        print(f"[!] Objetivo {args.target} no es privado/loopback. Abortando.")
        return 1

    os.makedirs(args.out, exist_ok=True)
    logs_dir = os.path.join(args.out, "zombie_logs")
    os.makedirs(logs_dir, exist_ok=True)

    zombies = []          # procesos zombi activos (acumulativos)
    zombie_logs = []      # ficheros de log abiertos, para cerrarlos al final
    summary_rows = []

    def spawn_zombie(idx):
        log = open(os.path.join(logs_dir, f"zombie-{idx}.log"), "w", encoding="utf-8")
        proc = subprocess.Popen(
            [PY, "-u", os.path.join(HERE, "zombie.py"),
             "--id", f"zombie-{idx}", "--control-port", str(args.control_port)],
            stdout=log, stderr=subprocess.STDOUT,
        )
        zombies.append(proc)
        zombie_logs.append(log)
        print(f"[demo] Zombi zombie-{idx} en marcha (PID {proc.pid}).")

    try:
        for n in range(1, args.rounds + 1):
            print(f"\n======== RONDA {n}: {n} zombi(s) ========")
            while len(zombies) < n:
                spawn_zombie(len(zombies) + 1)
            time.sleep(1.5)  # margen para que el nuevo zombi haga bind al puerto de control

            round_csv = os.path.join(args.out, f"ronda_{n}.csv")
            run_seconds = args.duration + 3
            victim = subprocess.Popen(
                [PY, "-u", os.path.join(HERE, "victim.py"),
                 "--port", str(args.port), "--csv", round_csv,
                 "--label", f"ronda-{n}", "--run-seconds", str(run_seconds)],
            )
            time.sleep(1.2)  # que la victima este escuchando antes de atacar

            print(f"[demo] Lanzando ataque ({n} zombis, {args.duration}s)...")
            subprocess.run(
                [PY, os.path.join(HERE, "commander.py"),
                 "--target", args.target, "--port", str(args.port),
                 "--duration", str(args.duration), "--pps", str(args.pps),
                 "--size", str(args.size), "--broadcast", args.broadcast,
                 "--control-port", str(args.control_port)],
                check=False,
            )

            victim.wait(timeout=run_seconds + 10)

            peak_pps, peak_kbps, max_ips, max_zombis = read_round_csv(round_csv)
            summary_rows.append({
                "ronda": n, "zombis_lanzados": n,
                "pico_pps": round(peak_pps), "pico_kbps": round(peak_kbps, 1),
                "ips_detectadas": max_ips, "endpoints_detectados": max_zombis,
                "csv": os.path.basename(round_csv),
            })
            print(f"[demo] Ronda {n}: pico {peak_pps:,.0f} pps, {peak_kbps:,.1f} KB/s, "
                  f"{max_ips} IP(s), {max_zombis} endpoint(s). -> {os.path.basename(round_csv)}")
            time.sleep(2)  # separacion entre rondas (mesetas claras en el IO Graph)
    finally:
        for proc in zombies:
            proc.terminate()
        for proc in zombies:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        for log in zombie_logs:
            log.close()

    # Resumen agregado
    summary_path = os.path.join(args.out, "resumen.csv")
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "ronda", "zombis_lanzados", "pico_pps", "pico_kbps",
            "ips_detectadas", "endpoints_detectados", "csv",
        ])
        writer.writeheader()
        writer.writerows(summary_rows)

    print("\n======== RESUMEN ========")
    print(f"{'ronda':>5} | {'zombis':>6} | {'pico pps':>10} | {'pico KB/s':>10} | {'IPs':>4} | {'endpoints':>9}")
    for r in summary_rows:
        print(f"{r['ronda']:>5} | {r['zombis_lanzados']:>6} | {r['pico_pps']:>10,} | "
              f"{r['pico_kbps']:>10,.1f} | {r['ips_detectadas']:>4} | {r['endpoints_detectados']:>9}")
    print(f"\n[demo] CSV por ronda y resumen.csv en: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
