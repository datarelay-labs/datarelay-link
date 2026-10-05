#!/usr/bin/env python3
from __future__ import annotations
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_product_update as update

HEAD = "0123456789abcdef0123456789abcdef01234567"


class V30ProductUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-product-update-")
        root = Path(self.tmp)
        (root / "etc/drlink").mkdir(parents=True, exist_ok=True)
        (root / "etc/systemd/system").mkdir(parents=True, exist_ok=True)
        (root / "etc/systemd/system/drlink-web.service").write_text("web\n", encoding="utf-8")
        (root / "etc/drlink/version").write_text(
            "PROJECT_VERSION=3.0.0\nRELEASE_CHANNEL=development\n"
            f"SOURCE_REF={HEAD}\nSOURCE_HEAD={HEAD}\n",
            encoding="utf-8",
        )
        self.identity = {
            "project_version": "3.0.0",
            "channel": "development",
            "source_ref": HEAD,
            "source_head": HEAD,
        }

    def test_request_is_0600_bounded_and_status_readable(self):
        result = update.create_request(self.tmp, actor_id="web:admin", identity=self.identity)
        req = update.request_path(self.tmp, result["job_id"])
        status = update.status_path(self.tmp, result["job_id"])
        self.assertEqual(req.stat().st_mode & 0o777, 0o600)
        self.assertEqual(status.stat().st_mode & 0o777, 0o600)
        self.assertEqual(update.read_status(self.tmp, result["job_id"])["status"], "QUEUED")

    def test_request_fails_closed_without_web_or_immutable_identity(self):
        web = Path(self.tmp) / "etc/systemd/system/drlink-web.service"
        web.unlink()
        with self.assertRaisesRegex(update.ProductUpdateError, "not installed"):
            update.create_request(self.tmp, actor_id="web:admin", identity=self.identity)
        web.write_text("web\n", encoding="utf-8")
        bad = dict(self.identity, source_ref="main")
        with self.assertRaisesRegex(update.ProductUpdateError, "immutable"):
            update.create_request(self.tmp, actor_id="web:admin", identity=bad)

    def test_stale_request_fails_before_download(self):
        result = update.create_request(self.tmp, actor_id="web:admin", identity=self.identity)
        other = "f" * 40
        (Path(self.tmp) / "etc/drlink/version").write_text(
            "PROJECT_VERSION=3.0.0\nRELEASE_CHANNEL=development\n"
            f"SOURCE_REF={other}\nSOURCE_HEAD={other}\n",
            encoding="utf-8",
        )
        with mock.patch.object(update, "_download_exact_package") as download:
            with self.assertRaisesRegex(update.ProductUpdateError, "stale"):
                update.run_job(result["job_id"], self.tmp)
        download.assert_not_called()
        status = update.read_status(self.tmp, result["job_id"])
        self.assertEqual(status["status"], "FAILED")
        self.assertFalse(status["recovery_required"])

    def test_safe_extract_rejects_traversal(self):
        import tarfile
        bundle = Path(self.tmp) / "bad.tar.gz"
        with tarfile.open(bundle, "w:gz") as tf:
            info = tarfile.TarInfo("data-relay-link-web/../../escape")
            payload = b"bad"
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
        dest = Path(self.tmp) / "extract"
        dest.mkdir()
        with self.assertRaisesRegex(update.ProductUpdateError, "unsafe path"):
            update._safe_extract(bundle, dest)

    def test_web_package_identity_must_match_exact_core_ref_and_channel(self):
        package = Path(self.tmp) / "package"
        package.mkdir()
        manifest = {
            "project_version": "3.0.0",
            "channel": "development",
            "git_ref": HEAD,
            "source_head": HEAD,
        }
        (package / "release-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        identity = update._package_identity(package, HEAD, "development")
        self.assertEqual(identity["source_head"], HEAD)
        with self.assertRaisesRegex(update.ProductUpdateError, "source ref"):
            update._package_identity(package, "f" * 40, "development")
        with self.assertRaisesRegex(update.ProductUpdateError, "channel"):
            update._package_identity(package, HEAD, "stable")

    def test_core_web_identity_mismatch_after_core_update_fails_recovery_required(self):
        queued = update.create_request(
            self.tmp, actor_id="web:admin", identity=self.identity
        )
        target = "f" * 40
        with mock.patch.dict(
            os.environ,
            {"DRLINK_PRODUCT_UPDATE_SOURCE": str(ROOT)},
            clear=False,
        ), mock.patch.object(
            update,
            "_local_package",
            return_value=(
                ROOT,
                {
                    "project_version": "3.0.0",
                    "source_ref": target,
                    "source_head": target,
                    "release_channel": "development",
                },
                "local-source:" + target,
            ),
        ), mock.patch.object(
            update,
            "_run_checked",
            return_value=mock.Mock(returncode=0, stdout="", stderr=""),
        ):
            with self.assertRaisesRegex(
                update.ProductUpdateError, "does not match the verified Web package"
            ):
                update.run_job(queued["job_id"], self.tmp)
        status = update.read_status(self.tmp, queued["job_id"])
        self.assertEqual(status["status"], "FAILED")
        self.assertTrue(status["recovery_required"])


if __name__ == "__main__":
    unittest.main()
