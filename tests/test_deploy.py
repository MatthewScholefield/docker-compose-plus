import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "docker-compose-plus"


@unittest.skipUnless(shutil.which("jsonnet"), "jsonnet is required")
class DeployTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "app"
        self.project.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.capture = self.root / "capture.json"
        docker = self.bin / "docker"
        docker.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "with open(os.environ['CAPTURE'], 'w') as f:\n"
            "    json.dump({'args': sys.argv[1:], 'config': json.load(sys.stdin)}, f)\n"
            "sys.exit(int(os.environ.get('DOCKER_STATUS', '0')))\n"
        )
        docker.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", CAPTURE=str(self.capture))
        self.config = {
            "version": "3.8",
            "services": {
                "api": {
                    "image": "api:latest",
                    "depends_on": ["database"],
                    "volumes": ["data:/data", "./local:/local", {"type": "volume", "source": "cache", "target": "/cache"}],
                    "secrets": ["password", {"source": "token", "target": "token"}],
                    "configs": [{"source": "settings", "target": "/settings"}],
                },
                "worker": {"image": "worker:latest", "networks": {"backend": {}}},
                "database": {"image": "postgres:latest", "networks": ["backend"]},
            },
            "networks": {"default": {}, "backend": {}, "unused": {}},
            "volumes": {"data": {}, "cache": {}, "unused": {}},
            "secrets": {"password": {"external": True}, "token": {"external": True}, "unused": {"file": "missing"}},
            "configs": {"settings": {"external": True}, "unused": {"file": "missing"}},
        }
        self.source = self.project / ".env.prod.jsonnet"
        self.source.write_text(json.dumps(self.config))

    def run_deploy(self, *services):
        return subprocess.run(
            ["bash", str(SCRIPT), "prod", "deploy", *services],
            cwd=self.project, env=self.env, text=True, capture_output=True,
        )

    def captured(self):
        return json.loads(self.capture.read_text())

    def test_full_stack(self):
        result = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.captured()["config"], self.config)
        self.assertEqual(self.captured()["args"], ["stack", "deploy", "--compose-file", "-", "app"])

    def test_targeted_resources_and_dependencies(self):
        result = self.run_deploy("api")
        self.assertEqual(result.returncode, 0, result.stderr)
        config = self.captured()["config"]
        self.assertEqual(set(config["services"]), {"api"})
        self.assertNotIn("depends_on", config["services"]["api"])
        for kind, names in {"networks": {"default"}, "volumes": {"data", "cache"}, "secrets": {"password", "token"}, "configs": {"settings"}}.items():
            self.assertEqual(set(config[kind]), names)

    def test_multiple_and_duplicate_services(self):
        result = self.run_deploy("api", "worker", "api")
        self.assertEqual(result.returncode, 0, result.stderr)
        config = self.captured()["config"]
        self.assertEqual(set(config["services"]), {"api", "worker"})
        self.assertEqual(set(config["networks"]), {"default", "backend"})

    def test_network_list(self):
        result = self.run_deploy("database")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(self.captured()["config"]["networks"]), {"backend"})

    def test_unknown_service(self):
        result = self.run_deploy("api", "missing")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown service(s): missing", result.stderr)
        self.assertFalse(self.capture.exists())

    def test_invalid_jsonnet(self):
        self.source.write_text("error 'render failed'")
        for services in [(), ("api",)]:
            result = self.run_deploy(*services)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.capture.exists())

    def test_docker_failure(self):
        self.env["DOCKER_STATUS"] = "7"
        self.assertEqual(self.run_deploy("api").returncode, 7)

    def test_special_service_name(self):
        name = 'api"quoted'
        self.config["services"][name] = {"image": "api:latest"}
        self.source.write_text(json.dumps(self.config))
        result = self.run_deploy(name)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(self.captured()["config"]["services"]), {name})


@unittest.skipUnless(shutil.which("git"), "git is required")
class SelfUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "installation with spaces"
        self.bin = self.repo / "bin"
        self.bin.mkdir(parents=True)
        self.script = self.bin / "docker-compose-plus"
        shutil.copy2(SCRIPT, self.script)
        self.git("init", "-q")
        self.git("add", "bin/docker-compose-plus")
        self.mock_bin = self.root / "mock-bin"
        self.mock_bin.mkdir()
        self.capture = self.root / "pull.json"
        mock_git = self.mock_bin / "git"
        mock_git.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "if 'pull' in sys.argv[1:]:\n"
            "    with open(os.environ['CAPTURE'], 'w') as f:\n"
            "        json.dump(sys.argv[1:], f)\n"
            "    sys.exit(int(os.environ.get('PULL_STATUS', '0')))\n"
            "os.execv(os.environ['REAL_GIT'], ['git', *sys.argv[1:]])\n"
        )
        mock_git.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{self.mock_bin}:{os.environ['PATH']}",
                        CAPTURE=str(self.capture), REAL_GIT=shutil.which("git"))

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)

    def run_update(self, script=None, *args):
        return subprocess.run(
            ["bash", str(script or self.script), "self-update", *args],
            cwd=self.root, env=self.env, text=True, capture_output=True,
        )

    def test_git_installation(self):
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.capture.read_text()), ["-C", str(self.repo), "pull", "--ff-only"])

    def test_symlink_chain(self):
        (self.bin / "dcp").symlink_to("docker-compose-plus")
        link = self.root / "dcp"
        link.symlink_to("installation with spaces/bin/dcp")
        result = self.run_update(link)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.capture.read_text())[1], str(self.repo))

    def test_standalone(self):
        script = self.root / "standalone"
        shutil.copy2(self.script, script)
        result = self.run_update(script)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("standalone or nonstandard installation", result.stderr)
        self.assertFalse(self.capture.exists())

    def test_copy_inside_unrelated_repo(self):
        script = self.repo / "copy"
        shutil.copy2(self.script, script)
        result = self.run_update(script)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.capture.exists())

    def test_untracked_installation(self):
        self.git("rm", "--cached", "bin/docker-compose-plus")
        result = self.run_update()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.capture.exists())

    def test_pull_failure(self):
        self.env["PULL_STATUS"] = "9"
        self.assertEqual(self.run_update().returncode, 9)

    def test_extra_arguments(self):
        result = self.run_update(self.script, "extra")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Usage:", result.stderr)
        self.assertFalse(self.capture.exists())


if __name__ == "__main__":
    unittest.main()
