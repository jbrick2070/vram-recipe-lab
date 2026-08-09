from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scratch" / "humo_diet_sidecar.py"
SPEC = importlib.util.spec_from_file_location("humo_diet_sidecar", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
sidecar = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sidecar)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def machine_sample(used_mib: float = 2048.0, host_bytes: int = 8 * 1024**3):
    now_ns = time.time_ns()
    return {
        "sampled_at_ns": now_ns,
        "sampled_at_utc": sidecar.utc_timestamp(now_ns),
        "sampled_monotonic_ns": time.monotonic_ns(),
        "gpu_index": 0,
        "vram_used_mib": used_mib,
        "vram_total_mib": 16303.0,
        "host_ram_used_bytes": host_bytes,
        "host_ram_total_bytes": 64 * 1024**3,
    }


class FakeProcess:
    def __init__(self, on_wait, returncode=0):
        self.stdout = io.BytesIO(b"preflight ok\nrender complete\n")
        self._on_wait = on_wait
        self._returncode = returncode

    def wait(self, timeout=None):
        self._on_wait()
        return self._returncode

    def poll(self):
        return self._returncode

    def terminate(self):
        self._returncode = -15


class TempLab:
    def __init__(self, root: Path):
        self.root = root
        self.results = root / "results"
        self.outputs = root / "outputs"
        self.recipes = root / "recipes"
        self.telemetry = self.results / "humo_diet" / "telemetry"
        self.results.mkdir()
        self.outputs.mkdir()
        self.recipes.mkdir()
        self.executable = root / "python.exe"
        self.executable.write_bytes(b"fake-python")
        (root / "run_recipe.py").write_text("# existing runner\n", encoding="utf-8")
        self.recipe = self.recipes / "diet.json"
        self.recipe.write_text(json.dumps({"name": "diet", "prompt": {}}), encoding="utf-8")
        self.server_log = root / "server.log"
        self.server_log.write_bytes(b"old log line\n")

    def command(self):
        return [
            str(self.executable),
            "-u",
            "run_recipe.py",
            "recipes/diet.json",
            "--shutdown",
        ]

    def publish_run(self, *, artifact_hash_override=None, run_number=1):
        with self.server_log.open("ab") as handle:
            handle.write(b"model loaded\nfirst sample\nartifact saved\n")
        artifact = self.outputs / "diet_out.mp4"
        artifact.write_bytes(b"video-artifact")
        payload = {
            "receipt_schema_version": 3,
            "recipe": "diet",
            "run_number": run_number,
            "run_identity_sha256": "a" * 64,
            "status": "PASS (cold)",
            "gate_pass": True,
            "warm_pass": False,
            "pass": False,
            "output_path": artifact.name,
            "artifact_sha256": artifact_hash_override or sha256(artifact.read_bytes()),
            "artifact_bytes": artifact.stat().st_size,
        }
        raw = sidecar.canonical_json_bytes(payload)
        archive = self.results / f"diet_run{run_number}.json"
        archive.write_bytes(raw)
        (self.results / "diet.json").write_bytes(raw)


class HumoDietSidecarTests(unittest.TestCase):
    def test_parse_gpu_csv_is_strict(self):
        self.assertEqual(
            sidecar.parse_gpu_csv("2048, 16303\n", 0),
            {
                "gpu_index": 0,
                "vram_used_mib": 2048.0,
                "vram_total_mib": 16303.0,
            },
        )
        for invalid in ("", "1,2\n3,4\n", "N/A, 10\n", "11, 10\n"):
            with self.subTest(value=invalid), self.assertRaises(sidecar.SidecarError):
                sidecar.parse_gpu_csv(invalid, 0)

    def test_log_tail_excludes_old_bytes_and_preserves_exact_new_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "server.log"
            path.write_bytes(b"old\n")
            starting = sidecar.stable_file_snapshot(path)
            tail = sidecar.AppendOnlyLogTail(path, starting)
            with path.open("ab") as handle:
                handle.write(b"new one\npartial")
            tail.poll(100, 200)
            with path.open("ab") as handle:
                handle.write(b" line\n")
            summary = tail.finish()

        self.assertEqual(summary["starting"]["bytes"], 4)
        self.assertEqual(summary["ending"]["bytes"], 25)
        self.assertEqual(summary["new_byte_count"], 21)
        self.assertEqual([event["text"] for event in summary["events"]], ["new one", "partial line"])
        raw = b"".join(
            __import__("base64").b64decode(event["raw_base64"])
            for event in summary["events"]
        )
        self.assertEqual(raw, b"new one\npartial line\n")
        self.assertEqual(summary["new_bytes_sha256"], sha256(raw))
        self.assertEqual(summary["errors"], [])

    def test_sample_summary_fails_closed_on_errors_and_large_gaps(self):
        baseline = machine_sample()
        samples = [
            {**machine_sample(3000), "sampled_monotonic_ns": 1_000_000_000},
            {**machine_sample(4000), "sampled_monotonic_ns": 2_000_000_000},
        ]
        summary = sidecar.summarize_samples(
            samples,
            baseline=baseline,
            child_start_mono_ns=900_000_000,
            child_end_mono_ns=2_100_000_000,
            interval_s=0.2,
            max_gap_s=0.75,
            sample_errors=["nvidia timeout"],
        )
        self.assertEqual(summary["peak_vram_mib"], 4000)
        self.assertIn("nvidia timeout", summary["coverage_errors"])
        self.assertTrue(any("exceeds maximum" in error for error in summary["coverage_errors"]))

    def test_success_run_streams_and_binds_one_archive_alias_and_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            lab = TempLab(Path(temporary))
            output = lab.telemetry / "take1.json"
            popen_calls = []

            def fake_popen(argv, **kwargs):
                popen_calls.append((argv, kwargs))
                return FakeProcess(lab.publish_run)

            with (
                mock.patch.object(
                    sidecar.subprocess,
                    "run",
                    side_effect=AssertionError("unit test must not invoke nvidia-smi"),
                ),
                mock.patch.object(
                    sidecar.subprocess,
                    "Popen",
                    side_effect=AssertionError("injected fake process must be used"),
                ),
            ):
                code, receipt = sidecar.run(
                    [
                        "--output",
                        str(output),
                        "--label",
                        "take1",
                        "--interval-s",
                        "0.001",
                        "--max-sample-gap-s",
                        "0.25",
                        "--",
                        *lab.command(),
                    ],
                    repo_root=lab.root,
                    popen_factory=fake_popen,
                    sample_query=lambda _gpu: machine_sample(used_mib=4096),
                )

            self.assertEqual(code, 0, receipt["errors"])
            self.assertEqual(receipt["status"], "ok")
            self.assertFalse(receipt["phase_inference"]["performed"])
            self.assertGreaterEqual(receipt["sampler"]["sample_count"], 1)
            self.assertEqual(receipt["sampler"]["peak_vram_mib"], 4096)
            self.assertEqual(receipt["child_stdout"]["event_count"], 2)
            self.assertEqual(receipt["server_log"]["starting"]["bytes"], 13)
            self.assertEqual(receipt["server_log"]["new_byte_count"], 41)
            self.assertTrue(receipt["run_binding"]["alias_byte_matches_archive"])
            self.assertEqual(
                receipt["run_binding"]["artifact"]["sha256"],
                sha256(b"video-artifact"),
            )
            self.assertEqual(popen_calls[0][1]["cwd"], str(lab.root))
            self.assertNotIn("shell", popen_calls[0][1])
            raw = output.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(json.loads(raw), receipt)
            with self.assertRaises(FileExistsError):
                sidecar.run(
                    ["--output", str(output), "--label", "again", "--", *lab.command()],
                    repo_root=lab.root,
                    popen_factory=fake_popen,
                    sample_query=lambda _gpu: machine_sample(),
                )

    def test_nonzero_child_writes_failed_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            lab = TempLab(Path(temporary))
            output = lab.telemetry / "failed.json"
            with (
                mock.patch.object(
                    sidecar.subprocess,
                    "run",
                    side_effect=AssertionError("unit test must not invoke nvidia-smi"),
                ),
                mock.patch.object(
                    sidecar.subprocess,
                    "Popen",
                    side_effect=AssertionError("injected fake process must be used"),
                ),
            ):
                code, receipt = sidecar.run(
                    [
                        "--output",
                        str(output),
                        "--label",
                        "failed",
                        "--interval-s",
                        "0.001",
                        "--max-sample-gap-s",
                        "0.25",
                        "--",
                        *lab.command(),
                    ],
                    repo_root=lab.root,
                    popen_factory=lambda *_args, **_kwargs: FakeProcess(
                        lambda: None, returncode=7
                    ),
                    sample_query=lambda _gpu: machine_sample(),
                )
        self.assertEqual(code, 1)
        self.assertEqual(receipt["status"], "failed")
        self.assertTrue(any("nonzero exit code 7" in error for error in receipt["errors"]))
        self.assertIsNone(receipt["run_binding"])

    def test_binding_rejects_missing_unique_archive_and_artifact_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            lab = TempLab(Path(temporary))
            before = sidecar.snapshot_archives(lab.results, "diet")
            with self.assertRaisesRegex(sidecar.SidecarError, "exactly one"):
                sidecar.bind_new_run(
                    repo_root=lab.root,
                    recipe_name="diet",
                    before_archives=before,
                    child_started_ns=time.time_ns() - 1_000_000,
                )
            lab.publish_run(artifact_hash_override="0" * 64)
            with self.assertRaisesRegex(sidecar.SidecarError, "SHA-256 mismatch"):
                sidecar.bind_new_run(
                    repo_root=lab.root,
                    recipe_name="diet",
                    before_archives=before,
                    child_started_ns=time.time_ns() - 1_000_000_000,
                )

    def test_unsafe_output_and_non_lab_runner_are_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            lab = TempLab(Path(temporary))
            launch = mock.Mock(side_effect=AssertionError("must not launch"))
            with self.assertRaisesRegex(sidecar.SidecarError, "escapes"):
                sidecar.run(
                    [
                        "--output",
                        str(lab.root / "outside.json"),
                        "--label",
                        "unsafe",
                        "--",
                        *lab.command(),
                    ],
                    repo_root=lab.root,
                    popen_factory=launch,
                    sample_query=lambda _gpu: machine_sample(),
                )
            other = lab.root / "other" / "run_recipe.py"
            other.parent.mkdir()
            other.write_text("# wrong runner\n", encoding="utf-8")
            command = [str(lab.executable), "-u", str(other), "recipes/diet.json"]
            with self.assertRaisesRegex(sidecar.SidecarError, "lab's existing"):
                sidecar.run(
                    [
                        "--output",
                        str(lab.telemetry / "wrong.json"),
                        "--label",
                        "wrong",
                        "--",
                        *command,
                    ],
                    repo_root=lab.root,
                    popen_factory=launch,
                    sample_query=lambda _gpu: machine_sample(),
                )
            malicious = [
                str(lab.executable),
                "-c",
                "print('wrong entrypoint')",
                "run_recipe.py",
                "recipes/diet.json",
            ]
            with self.assertRaisesRegex(sidecar.SidecarError, "Python -u must"):
                sidecar.run(
                    [
                        "--output",
                        str(lab.telemetry / "malicious.json"),
                        "--label",
                        "malicious",
                        "--",
                        *malicious,
                    ],
                    repo_root=lab.root,
                    popen_factory=launch,
                    sample_query=lambda _gpu: machine_sample(),
                )
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
