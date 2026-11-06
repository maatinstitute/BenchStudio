import sys
import tarfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from benchstudio import ReplayLimits, ReplayPipeline, ReplayWorkerError
from benchstudio.replay_worker import _supervise, execute_in_worker


@unittest.skipUnless(sys.platform == "linux", "Linux worker limits required")
class ReplayWorkerTests(unittest.TestCase):
    def test_worker_reports_invalid_archive_without_loading_libero(self):
        with TemporaryDirectory() as temporary:
            archive = Path(temporary) / "empty.tar.gz"
            with tarfile.open(archive, "w:gz"):
                pass
            with self.assertRaisesRegex(ValueError, "one RoboPAD campaign manifest"):
                ReplayPipeline.from_archive(archive, limits=ReplayLimits()).check()

    def test_supervisor_enforces_wall_limit(self):
        with TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ReplayWorkerError, "wall-clock limit"):
                _supervise(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    Path(temporary),
                    0.1,
                )

    def test_worker_rejects_file_limit_overrun(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_bytes(b" " * 2048)
            archive = root / "oversize.tar.gz"
            with tarfile.open(archive, "w:gz") as stream:
                stream.add(root / "manifest.json", arcname="manifest.json")
            limits = ReplayLimits(max_file_bytes=1024)
            request = {
                "archive": str(archive), "episode": None, "trusted_manifest_sha256": None,
                "check_only": True, "verify_environment": True,
            }
            payload = execute_in_worker(request, limits)
            self.assertEqual(payload["status"], "invalid_input")
            self.assertIn("File too large", payload["message"])
