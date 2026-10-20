import ast
try:
    import http.client as http_client
except ImportError:
    import httplib as http_client
import importlib
import os
import sys
import tempfile
import threading
import unittest

import common
import victim


def start_server(server):
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return thread


class Python27CompatibilityTests(unittest.TestCase):
    def test_production_sources_avoid_python3_only_language_and_apis(self):
        production_files = [
            "common.py",
            "commander.py",
            "zombie.py",
            "victim.py",
            "run_demo.py",
        ]
        forbidden_imports = {
            "dataclasses",
            "ipaddress",
        }
        forbidden_calls = {
            ("subprocess", "run"),
            ("time", "monotonic"),
        }
        violations = []

        for filename in production_files:
            with open(filename, "rb") as source_file:
                source = source_file.read()
            if sys.version_info[0] >= 3:
                source = source.decode("utf-8")
            tree = ast.parse(source, filename)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in forbidden_imports:
                            violations.append("{}:{} import {}".format(filename, node.lineno, alias.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.module in forbidden_imports:
                        violations.append("{}:{} from {}".format(filename, node.lineno, node.module))
                    if node.module == "__future__" and any(
                        alias.name == "annotations" for alias in node.names
                    ):
                        violations.append("{}:{} future annotations".format(filename, node.lineno))
                elif isinstance(node, ast.FunctionDef):
                    annotations = [getattr(arg, "annotation", None) for arg in node.args.args]
                    if getattr(node, "returns", None) is not None or any(
                        annotation is not None for annotation in annotations
                    ):
                        violations.append("{}:{} function annotations".format(filename, node.lineno))
                elif hasattr(ast, "AnnAssign") and isinstance(node, ast.AnnAssign):
                    violations.append("{}:{} annotated assignment".format(filename, node.lineno))
                elif hasattr(ast, "JoinedStr") and isinstance(node, ast.JoinedStr):
                    violations.append("{}:{} f-string".format(filename, node.lineno))
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                        call = (node.func.value.id, node.func.attr)
                        if call in forbidden_calls:
                            violations.append("{}:{} {}.{}".format(filename, node.lineno, *call))
                    if isinstance(node.func, ast.Name) and node.func.id == "super" and not node.args:
                        violations.append("{}:{} zero-argument super".format(filename, node.lineno))
                    if any(keyword.arg == "exist_ok" for keyword in node.keywords):
                        violations.append("{}:{} exist_ok".format(filename, node.lineno))
                elif isinstance(node, ast.Name) and node.id == "FileNotFoundError":
                    violations.append("{}:{} FileNotFoundError".format(filename, node.lineno))

        self.assertEqual([], violations, "\n".join(violations))


class HTTPConfigurationTests(unittest.TestCase):
    def test_http_load_test_has_safe_fixed_parameters(self):
        self.assertEqual(getattr(common, "HTTP_PATH", None), "/load-test")
        self.assertEqual(getattr(common, "MAX_RPS", None), 100)

    def test_lab_target_accepts_only_unambiguous_private_ipv4(self):
        for address in ("127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.1.1"):
            self.assertTrue(common.is_lab_target(address), address)
        for address in ("8.8.8.8", "172.32.0.1", "192.168.001.001", "256.1.1.1", "::1"):
            self.assertFalse(common.is_lab_target(address), address)


class HTTPVictimTests(unittest.TestCase):
    def test_authorized_post_is_counted(self):
        create_server = getattr(victim, "create_server", None)
        self.assertIsNotNone(create_server)

        server = create_server("127.0.0.1", 0)
        thread = start_server(server)
        connection = http_client.HTTPConnection(
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
        thread = start_server(server)
        connection = http_client.HTTPConnection(
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
        thread = start_server(server)
        connection = http_client.HTTPConnection(
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
        with tempfile.NamedTemporaryFile("w", delete=False) as csv_file:
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
