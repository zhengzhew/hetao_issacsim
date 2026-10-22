import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy/cloud"))
import manage
import host_runtime as runtime
import install_host as installer
import host_storage as storage
import host_dependencies as dependencies
import argparse
import subprocess


class CloudHostTests(unittest.TestCase):
    def init(self, root):
        target = root / "data"
        manage.initialize(target, "10.0.0.1", accept_eula=True)
        return target

    def test_saved_public_ip_does_not_require_cloud_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder)
            (d / "host.json").write_text(json.dumps({"publicIp": "47.103.10.20"}))
            machine = d / "machine-id"
            machine.write_text("a" * 32)
            identity = runtime.configured_identity(d, machine)
            self.assertEqual(identity["publicIp"], "47.103.10.20")
            self.assertTrue(identity["instanceId"].startswith("host-"))
            machine.write_text("b" * 32)
            self.assertNotEqual(runtime.configured_identity(d, machine)["instanceId"], identity["instanceId"])
            (d / "host.json").write_text(json.dumps({"publicIp": "10.0.0.1"}))
            with self.assertRaises(ValueError):
                runtime.configured_identity(d, machine)

    def test_same_instance_preserves_auth_and_ip_refresh_updates_all_routes(self):
        with tempfile.TemporaryDirectory() as folder:
            d = self.init(Path(folder))
            runtime.initialize_teacher(d, "example-password")
            first = {"instanceId": "i-one", "publicIp": "47.103.10.20"}
            runtime.update_identity(d, first)
            key = (d / "worker-key").read_bytes()
            access = (d / "state/platform/access.json").read_bytes()
            self.assertFalse(runtime.update_identity(d, {**first, "publicIp": "47.103.10.21"}))
            self.assertEqual((d / "worker-key").read_bytes(), key)
            self.assertEqual((d / "state/platform/access.json").read_bytes(), access)
            config = json.loads((d / "platform.json").read_text(encoding="utf-8"))
            self.assertEqual(config["publicOrigin"], "https://47.103.10.21")
            self.assertEqual(config["stations"][0]["publicIp"], "47.103.10.21")
            self.assertIn("47.103.10.21", (d / "Caddyfile").read_text())

    def test_clone_rotates_tokens_once_and_keeps_teacher_profiles_and_uploads(self):
        with tempfile.TemporaryDirectory() as folder:
            d = self.init(Path(folder))
            runtime.initialize_teacher(d, "example-password")
            runtime.update_identity(d, {"instanceId": "i-old", "publicIp": "47.103.10.20"})
            access_path = d / "state/platform/access.json"
            access = json.loads(access_path.read_text())
            access.update(credentials={"token": {"role": "device"}}, codes={"code": {}},
                          arms={"arm": {"driver": "desheng-se-v401", "calibrationHash": "123"}})
            runtime.save_json(access_path, access)
            upload = d / "state/stations/preserved.json"
            upload.write_text("keep")
            key = (d / "worker-key").read_bytes()
            identity = {"instanceId": "i-new", "publicIp": "47.103.10.21"}
            self.assertTrue(runtime.update_identity(d, identity))
            changed = json.loads(access_path.read_text())
            self.assertEqual(changed["credentials"], {})
            self.assertEqual(changed["codes"], {})
            self.assertEqual(changed["passwordHash"], access["passwordHash"])
            self.assertEqual(changed["arms"], access["arms"])
            self.assertNotEqual((d / "worker-key").read_bytes(), key)
            new_key = (d / "worker-key").read_bytes()
            self.assertFalse(runtime.update_identity(d, identity))
            self.assertEqual((d / "worker-key").read_bytes(), new_key)
            self.assertEqual(upload.read_text(), "keep")

    def test_teacher_initialization_never_overwrites_existing_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            d = self.init(Path(folder))
            self.assertTrue(runtime.initialize_teacher(d, "example-password"))
            path = d / "state/platform/access.json"
            original = path.read_bytes()
            self.assertFalse(runtime.initialize_teacher(d, "replacement"))
            self.assertEqual(path.read_bytes(), original)

    def test_boot_uses_cached_images_and_marks_only_scene_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            d = self.init(Path(folder))
            manage.configure_public(d, "47.103.10.20")
            (d / "boot-managed").touch()
            with patch.object(runtime, "configured_identity", return_value={"instanceId": "i-one", "publicIp": "47.103.10.21"}), \
                    patch.object(runtime.subprocess, "run") as run, patch.object(manage, "wait_ready", return_value=0):
                runtime.start(d)
            commands = [c.args[0] for c in run.call_args_list]
            self.assertIn("down", commands[0])
            self.assertEqual(commands[-1][-5:], ["up", "-d", "--no-build", "--pull", "never"])
            self.assertTrue(any(p.endswith("compose.boot.yaml") for p in commands[-1]))
            status = json.loads((d / "startup-status.json").read_text())
            self.assertEqual(status["phase"], "scene-ready")
            self.assertFalse(status["browserVideoVerified"])

    def test_saved_config_failure_stops_stale_config_and_does_not_start(self):
        with tempfile.TemporaryDirectory() as folder:
            d = self.init(Path(folder))
            with patch.object(runtime, "configured_identity", side_effect=OSError("metadata unavailable")), \
                    patch.object(runtime.subprocess, "run") as run:
                with self.assertRaises(OSError):
                    runtime.start(d)
            self.assertEqual(len(run.call_args_list), 1)
            self.assertIn("down", run.call_args.args[0])
            self.assertEqual(json.loads((d / "startup-status.json").read_text())["phase"], "failed")

    def test_ready_failure_is_not_success(self):
        with tempfile.TemporaryDirectory() as folder:
            d = self.init(Path(folder))
            with patch.object(runtime, "configured_identity", return_value={"instanceId": "i-one", "publicIp": "47.103.10.20"}), \
                    patch.object(runtime.subprocess, "run"), patch.object(manage, "wait_ready", return_value=1):
                with self.assertRaisesRegex(RuntimeError, "Scene not ready"):
                    runtime.start(d)
            self.assertEqual(json.loads((d / "startup-status.json").read_text())["phase"], "failed")

    def test_env_update_preserves_other_options(self):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / ".env"
            env.write_text("GPU_DEVICE=1\nRELEASE_TAG=old\n# keep\n")
            installer.update_env(env, {"RELEASE_TAG": "new", "ASSET_CACHE_DIR": "/srv/assets"})
            self.assertEqual(env.read_text(), "GPU_DEVICE=1\nRELEASE_TAG=new\n# keep\nASSET_CACHE_DIR=/srv/assets\n")


class StorageTests(unittest.TestCase):
    def budget(self, root_free, data_free, same_disk=False, fresh=True):
        app, state, disk = Path("/opt/app"), Path("/srv/state"), Path("/data/docker")
        system = Mock(); system.stat.return_value.st_dev = 1
        data = system if same_disk else Mock()
        data.stat.return_value.st_dev = 1 if same_disk else 2
        def parent(p): return data if p == disk else system
        def usage(p): return Mock(free=(root_free if p is system else data_free) * storage.GIB)
        with patch.object(Path, "is_mount", return_value=True), patch.object(Path, "is_symlink", return_value=False), \
                patch.object(storage, "existing_parent", side_effect=parent), \
                patch.object(storage.shutil, "disk_usage", side_effect=usage):
            storage.check_space(app, state, disk, fresh=fresh)

    def test_actual_46_and_65_gib_disks_pass_without_expansion(self):
        self.budget(46, 65)

    def test_free_space_is_not_borrowed_from_another_disk(self):
        for root_free, data_free in [(11, 65), (46, 44)]:
            with self.assertRaises(RuntimeError): self.budget(root_free, data_free)
        with self.assertRaises(RuntimeError): self.budget(46, 65, same_disk=True)
        self.budget(6, 8, fresh=False)

    def test_unmounted_data_disk_is_rejected_before_disk_usage(self):
        with patch.object(Path, "is_mount", return_value=False), patch.object(storage.shutil, "disk_usage") as usage:
            with self.assertRaisesRegex(RuntimeError, "mounted data disk"):
                storage.check_space(Path("/opt/app"), Path("/srv/state"))
            usage.assert_not_called()

    def test_classic_storage_avoids_containerd_duplicate_image_store(self):
        original = {"registry-mirrors": ["https://example.test"], "runtimes": {"custom": {"path": "runtime"}}}
        result = storage.daemon_config(original)
        self.assertEqual(result["data-root"], str(Path("/data/docker")))
        self.assertEqual(result["storage-driver"], "overlay2")
        self.assertFalse(result["features"]["containerd-snapshotter"])
        self.assertEqual(result["builder"]["gc"]["defaultKeepStorage"], "4GB")
        self.assertEqual(result["runtimes"], original["runtimes"])
        self.assertNotIn("data-root", original)

    def test_existing_docker_images_are_never_hidden_by_reconfiguration(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "daemon.json"
            config.write_text('{"registry-mirrors": ["https://example.test"]}')
            before = config.read_bytes()
            with patch.object(storage.shutil, "which", return_value="docker"), \
                    patch.object(storage.subprocess, "run", return_value=Mock(returncode=0, stdout='{"Images":1,"Containers":0}')):
                with self.assertRaisesRegex(RuntimeError, "Existing Docker"):
                    storage.configure_docker(config, Path(folder) / "docker")
            self.assertEqual(config.read_bytes(), before)

    def test_repeated_configuration_does_not_restart_docker(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "daemon.json"
            disk = Path(folder) / "docker"
            config.write_text(json.dumps(storage.daemon_config({}, disk)))
            with patch.object(storage.subprocess, "run") as run:
                self.assertFalse(storage.configure_docker(config, disk))
            run.assert_not_called()

    def test_cleanup_is_limited_to_replaced_project_tags_and_never_forces(self):
        old = {"hetao-isaac-web:old": "sha256:old", "hetao-isaac-sim:new": "sha256:keep"}
        with patch.object(storage, "image_ids", return_value={"hetao-isaac-sim:new": "sha256:keep"}), \
                patch.object(storage.subprocess, "run", return_value=Mock(returncode=0, stdout="sha256:old")) as run:
            storage.remove_replaced_images(old, "new")
        self.assertEqual(run.call_args_list[-1].args[0], ["docker", "image", "rm", "hetao-isaac-web:old"])
        self.assertFalse(any("prune" in c.args[0] or "--force" in c.args[0] for c in run.call_args_list))


class InstallerTests(unittest.TestCase):
    def test_toolkit_checks_repository_signature_policy_exactly(self):
        dependencies.validate_toolkit_repo('[nvidia-container-toolkit]\nrepo_gpgcheck=1\ngpgcheck=0\n')
        with self.assertRaises(RuntimeError):
            dependencies.validate_toolkit_repo('[nvidia-container-toolkit]\nrepo_gpgcheck=0\ngpgcheck=1\n')

    def test_tencentos_four_supported_without_ubuntu_or_global_release_override(self):
        with tempfile.TemporaryDirectory() as folder:
            release = Path(folder) / "os-release"
            for identity, version, good in [("tencentos", "4", True), ("tlinux", "4.0", True), ("ubuntu", "22.04", False), ("tencentos", "3", False)]:
                release.write_text(f'ID={identity}\nVERSION_ID="{version}"\n')
                with patch.object(dependencies.platform, "machine", return_value="x86_64"):
                    if good: dependencies.check_os(release)
                    else:
                        with self.assertRaises(RuntimeError): dependencies.check_os(release)

    def test_existing_driver_is_checked_and_not_replaced(self):
        with patch.object(dependencies.shutil, "which", return_value="nvidia-smi"), \
                patch.object(dependencies, "check_gpu") as check, patch.object(dependencies, "run") as run:
            dependencies.install_driver()
        check.assert_called_once()
        run.assert_not_called()

    def test_driver_install_failure_requires_manual_reboot_and_does_not_install_cuda(self):
        with patch.object(dependencies.shutil, "which", return_value=None), \
                patch.object(dependencies.os, "uname", create=True, return_value=Mock(release="6.6.tl4")), \
                patch.object(dependencies, "check_gpu", side_effect=RuntimeError("not ready")), \
                patch.object(dependencies, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "reboot manually"):
                dependencies.install_driver()
        commands = [c.args for c in run.call_args_list]
        self.assertTrue(any("nvidia-driver-580" in c for c in commands))
        self.assertFalse(any("reboot" in c or "cuda" in c for c in commands))

    def test_public_ip_must_be_explicit_then_is_preserved_on_update(self):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder)
            with self.assertRaises(ValueError): installer.selected_ip(None, d)
            self.assertEqual(installer.selected_ip("47.103.10.20", d), "47.103.10.20")
            (d / "host.json").write_text('{"publicIp":"47.103.10.20"}')
            self.assertEqual(installer.selected_ip(None, d), "47.103.10.20")
            with self.assertRaises(ValueError): installer.selected_ip("10.0.0.1", d)

    def test_failed_build_keeps_running_service_and_existing_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); app = base / "app"; state = base / "state"
            manage.initialize(state, "10.0.0.1", accept_eula=True)
            runtime.initialize_teacher(state, "existing-password")
            before = (state / "state/platform/access.json").read_bytes()
            env = (state / ".env").read_bytes()
            commands = []
            def execute(*args, **kwargs):
                commands.append(args)
                if args[-2:] == ("build", "sim"):
                    raise subprocess.CalledProcessError(1, args)
                return Mock()
            with patch.dict(sys.modules, {"fcntl": Mock(LOCK_EX=2, LOCK_NB=4)}), \
                    patch.object(installer.os, "geteuid", create=True, return_value=0), \
                    patch.object(installer, "APP", app), patch.object(installer, "DATA", state), \
                    patch.object(dependencies, "check_os"), patch.object(dependencies, "check_gpu"), \
                    patch.object(dependencies, "prepare"), patch.object(storage, "check_space"), \
                    patch.object(storage, "image_ids", return_value={}), \
                    patch.object(installer, "source_tag", return_value="candidate"), \
                    patch.object(installer, "run", side_effect=execute):
                with self.assertRaises(subprocess.CalledProcessError):
                    installer.install(argparse.Namespace(public_ip="47.103.10.20", accept_eula=True, install_driver=False))
            self.assertEqual((state / "state/platform/access.json").read_bytes(), before)
            self.assertEqual((state / ".env").read_bytes(), env)
            self.assertFalse(any("systemctl" in c or "down" in c for c in commands))
            self.assertTrue(all(c[c.index("--parallel")+1] == "1" for c in commands if "compose" in c))

    def test_check_is_read_only(self):
        with patch.object(dependencies, "check_os"), patch.object(dependencies, "check_gpu"), \
                patch.object(storage, "check_space"), patch.object(storage, "verify_docker"), \
                patch.object(installer, "run"), patch.object(installer, "install") as install:
            self.assertEqual(installer.main(["--check", "--public-ip", "47.103.10.20"]), 0)
            install.assert_not_called()


if __name__ == "__main__":
    unittest.main()
