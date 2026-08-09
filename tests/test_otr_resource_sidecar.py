from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scratch" / "otr_resource_sidecar.py"
SPEC = importlib.util.spec_from_file_location("otr_resource_sidecar", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
sidecar = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sidecar)


class FakeProcess:
    def __init__(self, argv):
        self._argv = list(argv)

    def cmdline(self):
        return list(self._argv)

    def create_time(self):
        return 123.5

    def exe(self):
        return r"C:\Python312\python.exe"

    def ppid(self):
        return 77


class OtrResourceSidecarTests(unittest.TestCase):
    def test_parse_gpu_csv_requires_one_numeric_row(self):
        parsed = sidecar.parse_gpu_csv("2048, 16303, 7\n", 0)
        self.assertEqual(parsed["gpu_index"], 0)
        self.assertEqual(parsed["vram_used_mib"], 2048.0)
        self.assertEqual(parsed["vram_total_mib"], 16303.0)
        self.assertEqual(parsed["gpu_utilization_percent"], 7.0)
        with self.assertRaises(sidecar.SidecarError):
            sidecar.parse_gpu_csv("2048, 16303, N/A\n", 0)
        with self.assertRaises(sidecar.SidecarError):
            sidecar.parse_gpu_csv("1,2,3\n4,5,6\n", 0)

    def test_expected_server_requires_positive_otr_ownership(self):
        model_paths = Path(r"C:\repo\scripts\_otr_headless_model_paths.yaml")
        output = Path(r"C:\ComfyUI\output")
        argv = [
            r"C:\Python312\python.exe",
            r"C:\ComfyUI\main.py",
            "--port",
            "8000",
            "--output-directory",
            str(output),
            "--extra-model-paths-config",
            str(model_paths),
        ]
        with (
            mock.patch.object(
                sidecar,
                "_listener_rows",
                return_value=[{"address": "127.0.0.1", "port": 8000, "pid": 55}],
            ),
            mock.patch.object(sidecar.psutil, "Process", return_value=FakeProcess(argv)),
        ):
            identity = sidecar.identify_expected_otr_server(8000, model_paths, output)
        self.assertEqual(identity["serving_pid"], 55)
        self.assertEqual(identity["argv"], argv)

    def test_expected_server_rejects_wrong_model_path_config(self):
        expected = Path(r"C:\repo\scripts\_otr_headless_model_paths.yaml")
        output = Path(r"C:\ComfyUI\output")
        argv = [
            "python.exe",
            r"C:\ComfyUI\main.py",
            "--port",
            "8000",
            "--output-directory",
            str(output),
            "--extra-model-paths-config",
            r"C:\other\interactive.yaml",
        ]
        with (
            mock.patch.object(
                sidecar,
                "_listener_rows",
                return_value=[{"address": "127.0.0.1", "port": 8000, "pid": 55}],
            ),
            mock.patch.object(sidecar.psutil, "Process", return_value=FakeProcess(argv)),
            self.assertRaises(sidecar.SidecarError),
        ):
            sidecar.identify_expected_otr_server(8000, expected, output)

    def test_validate_smoke_command_binds_fixtures_seed_and_cache_buster(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            portrait = root / "portrait.png"
            audio = root / "dialogue.wav"
            portrait.write_bytes(b"portrait")
            audio.write_bytes(b"audio")
            command = [
                "python.exe",
                r"C:\repo\scripts\_otr_single_engine_smoke.py",
                "--engine",
                "humo_1.7B",
                "--frames",
                "129",
                "--portrait",
                str(portrait.resolve()),
                "--audio",
                str(audio.resolve()),
                "--cache-buster",
                "41",
            ]
            contract = sidecar.validate_smoke_command(command)
        self.assertEqual(contract["engine"], "humo_1.7B")
        self.assertEqual(contract["frames"], 129)
        self.assertEqual(contract["request_seed"], 7)
        self.assertEqual(contract["cache_buster"], 41)
        self.assertEqual(len(contract["portrait_sha256"]), 64)
        self.assertEqual(len(contract["audio_sha256"]), 64)

    def test_validate_smoke_command_rejects_cached_or_illegal_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            portrait = root / "portrait.png"
            audio = root / "dialogue.wav"
            portrait.write_bytes(b"p")
            audio.write_bytes(b"a")
            base = [
                "python.exe",
                r"C:\repo\scripts\_otr_single_engine_smoke.py",
                "--engine",
                "humo_1.7B",
                "--portrait",
                str(portrait.resolve()),
                "--audio",
                str(audio.resolve()),
            ]
            with self.assertRaisesRegex(sidecar.SidecarError, "cache-buster"):
                sidecar.validate_smoke_command([*base, "--frames", "129"])
            with self.assertRaisesRegex(sidecar.SidecarError, "4n.1"):
                sidecar.validate_smoke_command(
                    [*base, "--frames", "128", "--cache-buster", "1"]
                )
            with self.assertRaisesRegex(sidecar.SidecarError, "1..399"):
                sidecar.validate_smoke_command(
                    [*base, "--frames", "129", "--cache-buster", "4201"]
                )

    def test_report_artifact_must_advance_after_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "clip.mp4"
            report = root / "node_single.json"
            artifact.write_bytes(b"old")
            report.write_text(json.dumps({"clip": {"path": str(artifact.resolve())}}))
            before = sidecar.file_snapshot(report)
            started_ns = time.time_ns()
            time.sleep(0.002)
            artifact.write_bytes(b"new clip")
            report.write_text(json.dumps({"clip": {"path": str(artifact.resolve())}, "ok": True}))

            resolved, artifact_after, report_after = sidecar.wait_for_artifact(
                started_ns=started_ns,
                timeout_s=0.2,
                artifact=None,
                artifact_before=None,
                report=report,
                report_before=before,
                report_key="clip.path",
            )
        self.assertEqual(resolved, artifact.resolve())
        self.assertEqual(artifact_after["bytes"], 8)
        self.assertTrue(sidecar.snapshot_changed(before, report_after))

    def test_stale_report_cannot_prove_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "clip.mp4"
            report = root / "node_single.json"
            artifact.write_bytes(b"stale")
            report.write_text(json.dumps({"clip": {"path": str(artifact.resolve())}}))
            before = sidecar.file_snapshot(report)
            with self.assertRaisesRegex(sidecar.SidecarError, "report did not advance"):
                sidecar.wait_for_artifact(
                    started_ns=time.time_ns(),
                    timeout_s=0.01,
                    artifact=None,
                    artifact_before=None,
                    report=report,
                    report_before=before,
                    report_key="clip.path",
                )

    def test_atomic_json_is_complete_utf8_and_append_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "receipt.json"
            sidecar.atomic_create_json(path, {"label": "HuMo", "value": "café"})
            raw = path.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(json.loads(raw), {"label": "HuMo", "value": "café"})
            with self.assertRaises(FileExistsError):
                sidecar.atomic_create_json(path, {"label": "replacement"})


if __name__ == "__main__":
    unittest.main()
