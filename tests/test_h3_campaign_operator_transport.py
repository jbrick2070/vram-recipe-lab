from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scratch" / "record_h3_campaign_operator_transport.py"
SPEC = importlib.util.spec_from_file_location("h3_operator_transport_test", SOURCE)
assert SPEC is not None and SPEC.loader is not None
transport = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = transport
SPEC.loader.exec_module(transport)


class OperatorTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.source_relatives = (
            ("campaign", Path("scratch/campaign.py")),
            ("runner", Path("run_recipe.py")),
            ("launcher", Path("scratch/launcher.ps1")),
            ("recorder", Path("scratch/recorder.py")),
        )
        for index, (_, relative) in enumerate(self.source_relatives, start=1):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"source-{index}\n".encode("utf-8"))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def profile(self, mission: str) -> object:
        return transport.Profile(
            mission=mission,
            campaign_rel=Path("scratch/campaign.py"),
            operator_root_rel=Path(f"results/{mission}/operator_logs"),
            source_relatives=self.source_relatives,
            frozen_hashes={},
        )

    def append_canonical(
        self, path: Path, campaign_id: str, event: str, status: str | None = None
    ) -> None:
        rows = []
        if path.exists():
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        previous = rows[-1]["event_sha256"] if rows else None
        body = {
            "schema_version": 1,
            "ledger_sequence": len(rows) + 1,
            "campaign_id": campaign_id,
            "campaign_sequence": len(
                [row for row in rows if row["campaign_id"] == campaign_id]
            )
            + 1,
            "event": event,
            "recorded_at_ns": 123456789 + len(rows),
            "previous_event_sha256": previous,
            "details": ({"status": status} if status else {}),
        }
        row = {**body, "event_sha256": transport.sha256_bytes(transport.canonical_bytes(body))}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as handle:
            handle.write(transport.canonical_bytes(row) + b"\n")

    def append_followup(
        self, path: Path, campaign_id: str, event: str, status: str | None = None
    ) -> None:
        rows = []
        if path.exists():
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        body = {
            "sequence": len(rows) + 1,
            "campaign_id": campaign_id,
            "timestamp": "2026-08-10T00:00:00Z",
            "event": event,
            "previous_event_sha256": rows[-1]["event_sha256"] if rows else None,
            "data": ({"status": status} if status else {}),
        }
        row = {
            **body,
            "event_sha256": transport.sha256_bytes(
                transport.followup_compact_bytes(body)
            ),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as handle:
            handle.write(transport.canonical_bytes(row) + b"\n")

    def test_plan_is_read_only_and_uses_absolute_comfy_python(self) -> None:
        profile = self.profile("canonical")
        plan = transport.build_plan(
            root=self.root,
            profile=profile,
            campaign_id="canonical-unit",
            operator_run_id="operator-unit",
        )
        self.assertEqual(plan["executable"], str(transport.PYTHON))
        self.assertEqual(plan["argv"][0], str(transport.PYTHON))
        self.assertEqual(plan["arguments"][:2], ["-B", "-u"])
        self.assertIn("--run", plan["arguments"])
        self.assertFalse(Path(plan["operator_directory"]).exists())
        self.assertFalse((self.root / "results").exists())

    def test_prepare_claims_logs_exclusively_and_refuses_reuse(self) -> None:
        profile = self.profile("canonical")
        value = transport.prepare(
            root=self.root,
            profile=profile,
            campaign_id="canonical-unit",
            operator_run_id="operator-unit",
        )
        paths = transport.operator_paths(self.root, profile, "operator-unit")
        self.assertEqual(
            sorted(path.name for path in paths["directory"].iterdir()),
            ["preflight.json", "stderr.log", "stdout.log"],
        )
        self.assertEqual(paths["stdout"].read_bytes(), b"")
        self.assertEqual(paths["stderr"].read_bytes(), b"")
        self.assertTrue(value["no_campaign_or_server_process_started_by_recorder"])
        with self.assertRaisesRegex(transport.TransportError, "refusing reuse"):
            transport.prepare(
                root=self.root,
                profile=profile,
                campaign_id="canonical-unit",
                operator_run_id="operator-unit",
            )

    def test_finalize_canonical_binds_terminal_chain_and_streams(self) -> None:
        profile = self.profile("canonical")
        transport.prepare(
            root=self.root,
            profile=profile,
            campaign_id="canonical-unit",
            operator_run_id="operator-unit",
        )
        paths = transport.operator_paths(self.root, profile, "operator-unit")
        with paths["stdout"].open("ab") as handle:
            handle.write(b"campaign output\n")
        lifecycle = self.root / profile.lifecycle_rel("canonical-unit")
        self.append_canonical(lifecycle, "canonical-unit", "campaign_started")
        self.append_canonical(
            lifecycle, "canonical-unit", "campaign_completed", "COMPLETE"
        )
        result = transport.finalize(
            root=self.root,
            profile=profile,
            campaign_id="canonical-unit",
            operator_run_id="operator-unit",
            pid=4321,
            started_at_utc="2099-08-10T00:00:00.0000000Z",
            ended_at_utc="2099-08-10T00:01:00.0000000Z",
            exit_code=0,
        )
        self.assertEqual(result["transport_status"], "COMPLETED")
        receipt = json.loads(paths["receipt"].read_text(encoding="utf-8"))
        self.assertEqual(receipt["lifecycle"]["terminal"]["event"], "campaign_completed")
        self.assertTrue(receipt["lifecycle"]["whole_file_hash_chain_verified"])
        self.assertEqual(
            receipt["operator_streams"]["stdout"]["sha256"],
            transport.sha256_bytes(b"campaign output\n"),
        )
        with self.assertRaisesRegex(transport.TransportError, "entries drifted"):
            transport.finalize(
                root=self.root,
                profile=profile,
                campaign_id="canonical-unit",
                operator_run_id="operator-unit",
                pid=4321,
                started_at_utc="2099-08-10T00:00:00Z",
                ended_at_utc="2099-08-10T00:01:00Z",
                exit_code=0,
            )

    def test_finalize_followup_failure_matches_nonzero_exit(self) -> None:
        profile = self.profile("followup")
        transport.prepare(
            root=self.root,
            profile=profile,
            campaign_id="followup-unit",
            operator_run_id="operator-unit",
        )
        lifecycle = self.root / profile.lifecycle_rel("followup-unit")
        self.append_followup(lifecycle, "followup-unit", "campaign_started")
        self.append_followup(lifecycle, "followup-unit", "campaign_failed", "FAILED")
        result = transport.finalize(
            root=self.root,
            profile=profile,
            campaign_id="followup-unit",
            operator_run_id="operator-unit",
            pid=9876,
            started_at_utc="2099-08-10T00:00:00Z",
            ended_at_utc="2099-08-10T00:00:01Z",
            exit_code=1,
        )
        self.assertEqual(result["transport_status"], "FAILED")

    def test_followup_event_hash_includes_coordinator_jsonl_newline(self) -> None:
        body = {
            "sequence": 1,
            "campaign_id": "followup-unit",
            "timestamp": "2026-08-10T00:00:00Z",
            "event": "campaign_started",
            "previous_event_sha256": None,
            "data": {},
        }
        coordinator_bytes = (
            json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        self.assertEqual(
            transport.followup_compact_bytes(body), coordinator_bytes
        )

    def test_followup_resume_binds_unchanged_initial_lifecycle_prefix(self) -> None:
        profile = self.profile("followup")
        lifecycle = self.root / profile.lifecycle_rel("followup-unit")
        self.append_followup(lifecycle, "followup-unit", "campaign_started")
        self.append_followup(lifecycle, "followup-unit", "campaign_failed", "FAILED")
        initial_raw = lifecycle.read_bytes()
        transport.prepare(
            root=self.root,
            profile=profile,
            campaign_id="followup-unit",
            operator_run_id="operator-resume-unit",
            resume=True,
        )
        self.append_followup(lifecycle, "followup-unit", "campaign_resumed")
        self.append_followup(lifecycle, "followup-unit", "campaign_completed", "COMPLETE")
        result = transport.finalize(
            root=self.root,
            profile=profile,
            campaign_id="followup-unit",
            operator_run_id="operator-resume-unit",
            resume=True,
            pid=9876,
            started_at_utc="2099-08-10T00:00:00Z",
            ended_at_utc="2099-08-10T00:01:00Z",
            exit_code=0,
        )
        receipt_path = transport.operator_paths(
            self.root, profile, "operator-resume-unit"
        )["receipt"]
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(result["transport_status"], "COMPLETED")
        self.assertEqual(receipt["lifecycle"]["initial_prefix"]["bytes"], len(initial_raw))
        self.assertEqual(
            receipt["lifecycle"]["initial_prefix"]["sha256"],
            transport.sha256_bytes(initial_raw),
        )

    def test_canonical_resume_source_must_be_terminal_failed(self) -> None:
        profile = self.profile("canonical")
        lifecycle = self.root / profile.lifecycle_rel("new-campaign")
        self.append_canonical(lifecycle, "old-campaign", "campaign_started")
        self.append_canonical(lifecycle, "old-campaign", "campaign_failed", "FAILED")
        prepared = transport.prepare(
            root=self.root,
            profile=profile,
            campaign_id="new-campaign",
            operator_run_id="operator-resume-unit",
            resume_from_campaign_id="old-campaign",
        )
        self.assertEqual(
            prepared["plan"]["arguments"][-2:],
            ["--resume-from-campaign-id", "old-campaign"],
        )

    def test_finalize_rejects_exit_terminal_disagreement(self) -> None:
        profile = self.profile("followup")
        transport.prepare(
            root=self.root,
            profile=profile,
            campaign_id="followup-unit",
            operator_run_id="operator-unit",
        )
        lifecycle = self.root / profile.lifecycle_rel("followup-unit")
        self.append_followup(lifecycle, "followup-unit", "campaign_started")
        self.append_followup(lifecycle, "followup-unit", "campaign_failed", "FAILED")
        with self.assertRaisesRegex(transport.TransportError, "disagree"):
            transport.finalize(
                root=self.root,
                profile=profile,
                campaign_id="followup-unit",
                operator_run_id="operator-unit",
                pid=9876,
                started_at_utc="2099-08-10T00:00:00Z",
                ended_at_utc="2099-08-10T00:00:01Z",
                exit_code=0,
            )
        self.assertFalse(
            transport.operator_paths(self.root, profile, "operator-unit")["receipt"].exists()
        )

    def test_finalize_rejects_source_drift_without_receipt(self) -> None:
        profile = self.profile("canonical")
        transport.prepare(
            root=self.root,
            profile=profile,
            campaign_id="canonical-unit",
            operator_run_id="operator-unit",
        )
        (self.root / "run_recipe.py").write_bytes(b"drifted\n")
        with self.assertRaisesRegex(transport.TransportError, "source hashes drifted"):
            transport.finalize(
                root=self.root,
                profile=profile,
                campaign_id="canonical-unit",
                operator_run_id="operator-unit",
                pid=4321,
                started_at_utc="2099-08-10T00:00:00Z",
                ended_at_utc="2099-08-10T00:01:00Z",
                exit_code=0,
            )
        self.assertFalse(
            transport.operator_paths(self.root, profile, "operator-unit")["receipt"].exists()
        )

    def test_finalize_rejects_corrupt_lifecycle_hash_chain(self) -> None:
        profile = self.profile("canonical")
        transport.prepare(
            root=self.root,
            profile=profile,
            campaign_id="canonical-unit",
            operator_run_id="operator-unit",
        )
        lifecycle = self.root / profile.lifecycle_rel("canonical-unit")
        self.append_canonical(lifecycle, "canonical-unit", "campaign_started")
        self.append_canonical(
            lifecycle, "canonical-unit", "campaign_completed", "COMPLETE"
        )
        rows = lifecycle.read_text(encoding="utf-8").splitlines()
        terminal = json.loads(rows[-1])
        terminal["event_sha256"] = "0" * 64
        lifecycle.write_text(
            rows[0] + "\n" + json.dumps(terminal, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(transport.TransportError, "hash chain or schema"):
            transport.finalize(
                root=self.root,
                profile=profile,
                campaign_id="canonical-unit",
                operator_run_id="operator-unit",
                pid=4321,
                started_at_utc="2099-08-10T00:00:00Z",
                ended_at_utc="2099-08-10T00:01:00Z",
                exit_code=0,
            )

    def test_canonical_finalize_rejects_foreign_appended_suffix_rows(self) -> None:
        profile = self.profile("canonical")
        transport.prepare(
            root=self.root,
            profile=profile,
            campaign_id="canonical-unit",
            operator_run_id="operator-unit",
        )
        lifecycle = self.root / profile.lifecycle_rel("canonical-unit")
        self.append_canonical(lifecycle, "foreign-unit", "campaign_started")
        self.append_canonical(lifecycle, "foreign-unit", "campaign_failed", "FAILED")
        self.append_canonical(lifecycle, "canonical-unit", "campaign_started")
        self.append_canonical(
            lifecycle, "canonical-unit", "campaign_completed", "COMPLETE"
        )
        with self.assertRaisesRegex(transport.TransportError, "foreign campaign id"):
            transport.finalize(
                root=self.root,
                profile=profile,
                campaign_id="canonical-unit",
                operator_run_id="operator-unit",
                pid=4321,
                started_at_utc="2099-08-10T00:00:00Z",
                ended_at_utc="2099-08-10T00:01:00Z",
                exit_code=0,
            )

    def test_launcher_has_hidden_wait_no_cleanup_or_force_surface(self) -> None:
        raw = (ROOT / "scratch" / "start_h3_campaign_operator.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("Start-Process", raw)
        self.assertIn("-WindowStyle Hidden", raw)
        self.assertIn("-Wait", raw)
        self.assertIn("-PassThru", raw)
        self.assertIn(
            r'C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe', raw
        )
        for forbidden in (
            "Stop-Process",
            "Remove-Item",
            "taskkill",
            "Invoke-WebRequest",
            "curl",
            "127.0.0.1:8188",
        ):
            self.assertNotIn(forbidden, raw)

    def test_windows_start_process_retains_exclusive_log_file_identities(self) -> None:
        stdout_path = self.root / "redirect.stdout.log"
        stderr_path = self.root / "redirect.stderr.log"
        echo_script = self.root / "argv_echo.py"
        echo_script.write_text(
            "import json, sys\nprint(json.dumps(sys.argv[1:]))\n",
            encoding="utf-8",
            newline="\n",
        )
        stdout_claim = transport.create_log_exclusive(stdout_path)
        stderr_claim = transport.create_log_exclusive(stderr_path)
        environment = {
            **os.environ,
            "H3_TRANSPORT_TEST_PYTHON": str(transport.PYTHON),
            "H3_TRANSPORT_TEST_SCRIPT": str(echo_script),
            "H3_TRANSPORT_TEST_CWD": str(self.root),
            "H3_TRANSPORT_TEST_STDOUT": str(stdout_path),
            "H3_TRANSPORT_TEST_STDERR": str(stderr_path),
        }
        script = (
            "$Process = Start-Process "
            "-FilePath $env:H3_TRANSPORT_TEST_PYTHON "
            "-ArgumentList @('-B', $env:H3_TRANSPORT_TEST_SCRIPT, "
            "'--mission', 'canonical', '--campaign-id', 'campaign-unit') "
            "-WorkingDirectory $env:H3_TRANSPORT_TEST_CWD "
            "-RedirectStandardOutput $env:H3_TRANSPORT_TEST_STDOUT "
            "-RedirectStandardError $env:H3_TRANSPORT_TEST_STDERR "
            "-WindowStyle Hidden -Wait -PassThru; "
            "$Process.Refresh(); exit $Process.ExitCode"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            cwd=self.root,
            capture_output=True,
            timeout=30,
            check=False,
            env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        stdout_raw, stdout_final = transport.stable_file(stdout_path, "redirect stdout")
        _, stderr_final = transport.stable_file(stderr_path, "redirect stderr")
        self.assertEqual(
            json.loads(stdout_raw.decode("utf-8")),
            ["--mission", "canonical", "--campaign-id", "campaign-unit"],
        )
        for claim, final in (
            (stdout_claim, stdout_final),
            (stderr_claim, stderr_final),
        ):
            for key in ("path", "device", "inode", "mode", "link_count"):
                self.assertEqual(claim[key], final[key])

    def test_real_powershell_followup_plan_refuses_runner_drift_read_only(self) -> None:
        launcher = ROOT / "scratch" / "start_h3_campaign_operator.ps1"
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(launcher),
                "-Mission",
                "Followup",
                "-CampaignId",
                "followup-transport-dry-test",
                "-OperatorRunId",
                "followup-transport-dry-operator",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("frozen followup runner SHA drifted", result.stderr)
        self.assertFalse(
            (
                ROOT
                / "results"
                / "h3_music_followup_campaign"
                / "operator_logs"
                / "followup-transport-dry-operator"
            ).exists()
        )

    def test_real_powershell_canonical_plan_refuses_runner_drift_read_only(self) -> None:
        launcher = ROOT / "scratch" / "start_h3_campaign_operator.ps1"
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(launcher),
                "-Mission",
                "Canonical",
                "-CampaignId",
                "canonical-transport-dry-test",
                "-OperatorRunId",
                "canonical-transport-dry-operator",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("frozen canonical runner SHA drifted", result.stderr)
        self.assertFalse(
            (
                ROOT
                / "results"
                / "h3_canonical_canvas_campaign"
                / "operator_logs"
                / "canonical-transport-dry-operator"
            ).exists()
        )


if __name__ == "__main__":
    unittest.main()
