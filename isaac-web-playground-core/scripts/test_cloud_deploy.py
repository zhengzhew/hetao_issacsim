import copy
import hashlib
import io
from unittest.mock import patch
import importlib.util
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "deploy/cloud" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


manage = load("manage")
sim = load("sim_entry")
health = load("health_sim")
spec = importlib.util.spec_from_file_location("fetch_assets", ROOT / "scripts/fetch_challenge_assets.py")
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


class CloudTests(unittest.TestCase):
    def test_initialization_keeps_auth_private_and_never_overwrites_an_existing_deployment(self):
        with tempfile.TemporaryDirectory(prefix="isaac-cloud-test-") as folder:
            target = Path(folder) / "deployment"
            config = manage.initialize(target, "10.8.0.1", "1")
            key = (target / "worker-key").read_text()
            self.assertFalse(config["localConnector"]["enabled"])
            self.assertEqual(config["host"], "10.8.0.1")
            self.assertNotIn(key.strip(), (target / "platform.json").read_text(encoding="utf-8"))
            self.assertIn("GPU_DEVICE=1", (target / ".env").read_text())
            with self.assertRaises(ValueError):
                manage.initialize(target, "10.8.0.2")
            self.assertEqual(key, (target / "worker-key").read_text())

    def test_private_pilot_rejects_public_or_nonroutable_bind_addresses(self):
        for host in ("0.0.0.0", "127.0.0.1", "8.8.8.8", "example.com", "::1", "169.254.0.1"):
            with self.assertRaises(ValueError):
                manage.private_ip(host)
        self.assertEqual(manage.private_ip("100.64.1.2"), "100.64.1.2")

    def test_init_refuses_existing_unrelated_data(self):
        with tempfile.TemporaryDirectory(prefix="isaac-cloud-test-") as folder:
            target = Path(folder)
            (target / "unrelated.txt").write_text("keep", encoding="utf-8")
            with self.assertRaises(ValueError):
                manage.initialize(target, "10.8.0.1")
            self.assertEqual(list(target.iterdir()), [target / "unrelated.txt"])

    def test_ready_does_not_confuse_web_health_or_a_mock_with_simulation(self):
        healthy = {"nativeBundleAvailable": True, "signaling": {"connected": True},
                   "bridge": {"result": {"mock": False, "session": {"status": "ready"},
                                         "stream": {"livestream": True}}}}
        self.assertTrue(manage.ready_status(healthy))
        self.assertFalse(manage.ready_status({"ok": True}))
        bad = copy.deepcopy(healthy)
        bad["bridge"]["result"]["mock"] = True
        self.assertFalse(manage.ready_status(bad))
        bad = copy.deepcopy(healthy)
        bad["signaling"]["connected"] = False
        self.assertFalse(manage.ready_status(bad))

    def test_sim_health_requires_real_ready_response_from_the_loop(self):
        good = {"id": "health", "ok": True, "result": {"mock": False,
                "session": {"status": "ready"}, "stream": {"livestream": True}}}
        bad_mock = copy.deepcopy(good)
        bad_mock["result"]["mock"] = True
        bad_scene = copy.deepcopy(good)
        bad_scene["result"]["session"]["status"] = "loading"
        bad_id = {**good, "id": "other"}
        config = {"stations": [{"id": "cloud-1", "bridgePort": 8765}]}
        for reply, succeeds in [(good, True), (bad_mock, False), (bad_scene, False),
                                (bad_id, False), ({"id": "health", "ok": False}, False)]:
            with self.subTest(reply=reply), patch.object(health.socket, "create_connection") as connect:
                sock = connect.return_value.__enter__.return_value
                sock.makefile.return_value = io.BytesIO((json.dumps(reply) + "\n").encode())
                if succeeds:
                    health.probe(config, "cloud-1")
                else:
                    with self.assertRaises(ValueError):
                        health.probe(config, "cloud-1")
                request = json.loads(sock.sendall.call_args.args[0])
                self.assertEqual(request["op"], "ping")
                self.assertEqual(request["args"], {})
        with patch.object(health.socket, "create_connection", side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                health.probe(config, "cloud-1")

    def test_sim_uses_persistent_uploads_and_container_gpu_zero(self):
        with tempfile.TemporaryDirectory(prefix="isaac-cloud-test-") as folder:
            target = Path(folder)
            config = manage.initialize(target / "deployment", "10.8.0.1")
            data = target / "data"
            (data / "cloud-1/uploads/challenges").mkdir(parents=True)
            env = {"ISAAC_PLATFORM_DATA_DIR": str(data), "ISAAC_DIR": "/isaac-sim"}
            cmd = sim.command(config, "cloud-1", ROOT, env)
            self.assertEqual(cmd[-2:], ["--gpu", "0"])
            self.assertEqual(env["ISAAC_PUBLIC_IP"], "10.8.0.1")
            self.assertEqual(env["ISAAC_UPLOAD_DIR"], str(data / "cloud-1/uploads"))
            with self.assertRaises(ValueError):
                sim.command(config, "missing", ROOT, env)

    def test_asset_cache_rejects_corruption_and_exports_only_locked_files(self):
        with tempfile.TemporaryDirectory(prefix="isaac-cloud-test-") as folder:
            base = Path(folder)
            source = base / "source"
            source.mkdir()
            (source / "model.usd").write_bytes(b"known-model")
            (source / "private.txt").write_text("keep out")
            checks = {"model.usd": hashlib.sha256(b"known-model").hexdigest()}
            cache = base / "cache"
            with patch.object(assets, "OUT", source), patch.object(assets, "CHECKS", checks):
                assets.export_cache(cache)
                self.assertEqual([p.name for p in cache.iterdir()], ["model.usd"])
            with patch.object(assets, "OUT", base / "destination"), patch.object(assets, "CHECKS", checks), patch.object(assets.urllib.request, "urlopen", side_effect=AssertionError("No network expected")):
                assets.fetch(cache)
                self.assertEqual(json.loads((base / "destination/sha256.json").read_text()), checks)
            (cache / "model.usd").write_bytes(b"corrupted")
            with patch.object(assets, "OUT", base / "bad"), patch.object(assets, "CHECKS", checks):
                with self.assertRaises(ValueError):
                    assets.fetch(cache)
            with self.assertRaises(ValueError):
                assets.checked_file(source, "../outside", "0" * 64)

    def test_export_contains_deployment_and_excludes_local_credentials_and_calibration(self):
        with tempfile.TemporaryDirectory(prefix="isaac-cloud-test-") as folder:
            dest = Path(folder) / "source.tar.gz"
            manage.bundle(dest)
            with tarfile.open(dest) as archive:
                names = archive.getnames()
            self.assertIn("isaac-web-playground-core/deploy/cloud/compose.yaml", names)
            self.assertIn("isaac-web-playground-core/server/station-main.js", names)
            for name in names:
                self.assertNotIn("/run/", name)
                self.assertNotIn("/.env", name)
                self.assertNotIn("/uploads/", name)
                self.assertNotIn("leader_arm_calibration.json", name)
                self.assertNotIn("leader_arm_isaac_calibration.json", name)
                self.assertNotIn("/node_modules/", name)
            with self.assertRaises(ValueError):
                manage.bundle(dest)


if __name__ == "__main__":
    unittest.main()
