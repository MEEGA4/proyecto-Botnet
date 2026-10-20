import http.client
import importlib
import os
import tempfile
import threading
import unittest

import common
import victim


class HTTPConfigurationTests(unittest.TestCase):
    def test_http_load_test_has_safe_fixed_parameters(self):
        self.assertEqual(getattr(common, "HTTP_PATH", None), "/load-test")
        self.assertEqual(getattr(common, "MAX_RPS", None), 100)


class HTTPVictimTests(unittest.TestCase):
    def test_authorized_post_is_counted(self):
        create_server = getattr(victim, "create_server", None)
        self.assertIsNotNone(create_server)

        server = create_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_address[1], timeout=2
        )
        try:
            connection.request(
                "POST",
                common.HTTP_PATH,
                body=b"X" * 32,
                headers={
                    "Content-Length": "32",
                    "X-Lab-Token": common.CAMPAIGN_TOKEN,
                    "X-Lab-Zombie": "zombie-test",
                },
            )
            response = connection.getresponse()
            status = response.status
            response.read()
            snapshot = server.metrics.snapshot()
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(status, 204)
        self.assertEqual(snapshot.requests, 1)
        self.assertEqual(snapshot.body_bytes, 32)
        self.assertEqual(snapshot.source_ips, {"127.0.0.1"})
        self.assertEqual(snapshot.zombie_ids, {"zombie-test"})

    def test_invalid_lab_token_is_rejected(self):
        server = victim.create_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_address[1], timeout=2
        )
        try:
            connection.request(
                "POST",
                common.HTTP_PATH,
                body=b"X",
                headers={"X-Lab-Token": "invalid"},
            )
            response = connection.getresponse()
            status = response.status
            response.read()
            snapshot = server.metrics.snapshot()
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(status, 403)
        self.assertEqual(snapshot.requests, 0)


class HTTPZombieTests(unittest.TestCase):
    def test_send_http_post_identifies_the_zombie(self):
        try:
            zombie = importlib.import_module("zombie")
        except ImportError as exc:
            self.fail(str(exc))
        send_http_post = getattr(zombie, "send_http_post", None)
        self.assertIsNotNone(send_http_post)

        server = victim.create_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_address[1], timeout=2
        )
        try:
            status = send_http_post(connection, b"X" * 16, "zombie-client")
            snapshot = server.metrics.snapshot()
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(status, 204)
        self.assertEqual(snapshot.requests, 1)
        self.assertEqual(snapshot.zombie_ids, {"zombie-client"})


class HTTPCommanderTests(unittest.TestCase):
    def test_commander_builds_a_bounded_http_order(self):
        try:
            commander = importlib.import_module("commander")
        except ImportError as exc:
            self.fail(str(exc))

        args = commander.build_parser().parse_args([
            "--target",
            "127.0.0.1",
            "--port",
            "8080",
            "--rps",
            "999",
        ])
        build_order = getattr(commander, "build_order", None)
        self.assertIsNotNone(build_order)
        order = build_order(args)

        self.assertEqual(order["cmd"], "http_load_test")
        self.assertEqual(order["rps"], common.MAX_RPS)
        self.assertNotIn("pps", order)


class HTTPDemoTests(unittest.TestCase):
    def test_round_reader_uses_http_request_rate(self):
        run_demo = importlib.import_module("run_demo")
        with tempfile.NamedTemporaryFile("w", newline="", delete=False, encoding="utf-8") as csv_file:
            csv_file.write("label,epoch,segundo,rps,kbps,ips,zombis\n")
            csv_file.write("ronda-1,1,1,42,8.5,1,2\n")
            path = csv_file.name
        try:
            try:
                result = run_demo.read_round_csv(path)
            except KeyError as exc:
                self.fail(str(exc))
        finally:
            os.unlink(path)

        self.assertEqual(result, (42.0, 8.5, 1, 2))


if __name__ == "__main__":
    unittest.main()
