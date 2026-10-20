#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Servidor HTTP y medidor para la prueba de carga del laboratorio."""

from __future__ import print_function

import argparse
import csv
try:
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from socketserver import ThreadingMixIn
except ImportError:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
    from SocketServer import ThreadingMixIn
import sys
import threading
import time

from common import CAMPAIGN_TOKEN, HTTP_PATH


class MetricsSnapshot(object):
    def __init__(self, requests, body_bytes, source_ips, zombie_ids):
        self.requests = requests
        self.body_bytes = body_bytes
        self.source_ips = source_ips
        self.zombie_ids = zombie_ids


class MetricWindow(object):
    def __init__(self):
        self._lock = threading.Lock()
        self._requests = 0
        self._body_bytes = 0
        self._source_ips = set()
        self._zombie_ids = set()

    def record(self, source_ip, zombie_id, body_bytes):
        with self._lock:
            self._requests += 1
            self._body_bytes += body_bytes
            self._source_ips.add(source_ip)
            self._zombie_ids.add(zombie_id)

    def snapshot(self):
        with self._lock:
            result = MetricsSnapshot(
                self._requests,
                self._body_bytes,
                set(self._source_ips),
                set(self._zombie_ids),
            )
            self._requests = 0
            self._body_bytes = 0
            self._source_ips.clear()
            self._zombie_ids.clear()
            return result


class LabHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

    def __init__(self, server_address, handler_class):
        HTTPServer.__init__(self, server_address, handler_class)
        self.metrics = MetricWindow()


class LoadTestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        if self.path != HTTP_PATH:
            self._respond(404)
            return
        if self.headers.get("X-Lab-Token") != CAMPAIGN_TOKEN:
            self._respond(403)
            return
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        zombie_id = self.headers.get("X-Lab-Zombie", "unknown")
        self.server.metrics.record(self.client_address[0], zombie_id, len(body))
        self._respond(204)

    def _respond(self, status):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, _format, *_args):
        pass


def create_server(bind, port):
    return LabHTTPServer((bind, port), LoadTestHandler)


def open_csv_writer(path):
    if sys.version_info[0] == 2:
        return open(path, "wb")
    return open(path, "w", newline="", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Servidor/medidor HTTP del laboratorio.")
    parser.add_argument("-p", "--port", type=int, required=True, help="Puerto HTTP en el que escuchar")
    parser.add_argument("--bind", default="0.0.0.0", help="Interfaz en la que escuchar (def. 0.0.0.0)")
    parser.add_argument("--csv", default=None, help="Ruta del CSV de medidas")
    parser.add_argument("--label", default="", help="Etiqueta para cada fila del CSV")
    parser.add_argument(
        "--run-seconds",
        type=int,
        default=0,
        help="Si es mayor que 0, termina tras esos segundos",
    )
    args = parser.parse_args()

    server = create_server(args.bind, args.port)
    server.timeout = 0.2
    csv_file = None
    csv_writer = None
    if args.csv:
        csv_file = open_csv_writer(args.csv)
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["label", "epoch", "segundo", "rps", "kbps", "ips", "zombis"])

    print("[victima] Escuchando HTTP en {}:{}{}. Ctrl+C para salir.".format(args.bind, args.port, HTTP_PATH))
    print("[victima] {:>8} | {:>12} | {:>10} | {:>5} | {:>6}".format(
        "tiempo", "requests/s", "KB/s", "IPs", "zombis"
    ))
    started_at = time.time()
    last_report = started_at

    try:
        while True:
            server.handle_request()
            now = time.time()
            if now - last_report >= 1.0:
                elapsed = now - last_report
                snapshot = server.metrics.snapshot()
                rps = snapshot.requests / elapsed
                kbps = snapshot.body_bytes / 1024.0 / elapsed
                second = now - started_at
                print(
                    "[victima] {:>7.0f}s | {:>12,.0f} | {:>10,.1f} | {:>5} | {:>6}".format(
                        second,
                        rps,
                        kbps,
                        len(snapshot.source_ips),
                        len(snapshot.zombie_ids),
                    )
                )
                if csv_writer:
                    csv_writer.writerow([
                        args.label,
                        "{:.3f}".format(now),
                        "{:.0f}".format(second),
                        "{:.0f}".format(rps),
                        "{:.1f}".format(kbps),
                        len(snapshot.source_ips),
                        len(snapshot.zombie_ids),
                    ])
                    csv_file.flush()
                last_report = now

            if args.run_seconds and now - started_at >= args.run_seconds:
                print("[victima] Fin automatico tras {}s.".format(args.run_seconds))
                break
    except KeyboardInterrupt:
        print("\n[victima] Saliendo.")
    finally:
        server.server_close()
        if csv_file:
            csv_file.close()


if __name__ == "__main__":
    main()
