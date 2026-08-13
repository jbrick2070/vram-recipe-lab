import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import lab_locks
import run_recipe


class TestLabLocks(unittest.TestCase):
    def paths(self, root: Path):
        return (
            root / ".gpu.lock",
            root / ".suite.lock",
            root / ".coordinator.mutex",
        )

    def test_os_coordinator_contends_across_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            coordinator = Path(tmp) / ".coordinator.mutex"
            script = (
                "import sys; from pathlib import Path; import lab_locks; "
                "m=lab_locks.CoordinatorMutex(Path(sys.argv[1])); m.acquire(); "
                "print('READY', flush=True); sys.stdin.readline(); m.release()"
            )
            child = subprocess.Popen(
                [sys.executable, "-c", script, str(coordinator)],
                cwd=Path(__file__).resolve().parents[1],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                self.assertEqual(child.stdout.readline().strip(), "READY")
                contender = lab_locks.CoordinatorMutex(coordinator)
                with self.assertRaises(lab_locks.LeaseError):
                    contender.acquire()
            finally:
                _, stderr = child.communicate("\n", timeout=5)
            self.assertEqual(child.returncode, 0, stderr)

    def test_stale_receipts_are_a_hard_stop_and_remain_for_manual_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gpu, suite, coordinator = self.paths(root)
            dead_owner = {
                "lock_schema_version": 1,
                "pid": 99999999,
                "process_create_time": 1.0,
                "nonce": "a" * 64,
                "role": "suite",
                "created_at_unix": 1.0,
            }
            lab_locks.create_receipt_exclusive(suite, dead_owner)
            lab_locks.create_receipt_exclusive(gpu, dead_owner)
            suite_bytes = suite.read_bytes()
            gpu_bytes = gpu.read_bytes()

            owner = lab_locks.GpuLease(gpu, suite, coordinator)
            with self.assertRaisesRegex(lab_locks.LeaseError, "manual inspection"):
                owner.acquire()
            self.assertEqual(suite.read_bytes(), suite_bytes)
            self.assertEqual(gpu.read_bytes(), gpu_bytes)

            # The failed acquisition still releases the OS coordinator.
            probe = lab_locks.CoordinatorMutex(coordinator)
            probe.acquire()
            probe.release()

    def test_two_stale_receipt_contenders_are_both_refused_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gpu, suite, coordinator = self.paths(root)
            dead_owner = {
                "lock_schema_version": 1,
                "pid": 99999999,
                "process_create_time": 1.0,
                "nonce": "c" * 64,
                "role": "standalone",
                "created_at_unix": 1.0,
            }
            lab_locks.create_receipt_exclusive(gpu, dead_owner)
            original = gpu.read_bytes()
            start = threading.Barrier(3)
            attempts_done = threading.Event()
            result_lock = threading.Lock()
            results = []

            def contend():
                lease = lab_locks.GpuLease(gpu, suite, coordinator)
                start.wait()
                try:
                    lease.acquire()
                    outcome = "owner"
                except lab_locks.LeaseError:
                    outcome = "refused"
                with result_lock:
                    results.append(outcome)
                    if len(results) == 2:
                        attempts_done.set()

            threads = [threading.Thread(target=contend) for _ in range(2)]
            for thread in threads:
                thread.start()
            start.wait()
            self.assertTrue(attempts_done.wait(2))
            self.assertEqual(results.count("owner"), 0)
            self.assertEqual(results.count("refused"), 2)
            for thread in threads:
                thread.join(2)
                self.assertFalse(thread.is_alive())
            self.assertEqual(gpu.read_bytes(), original)

    def test_standalone_refuses_live_suite_receipt_even_without_os_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gpu, suite, coordinator = self.paths(root)
            receipt = lab_locks.new_lock_receipt("suite")
            lab_locks.create_receipt_exclusive(suite, receipt)
            lease = lab_locks.GpuLease(gpu, suite, coordinator)
            with self.assertRaises(lab_locks.LeaseError):
                lease.acquire()
            self.assertTrue(suite.exists())
            self.assertFalse(gpu.exists())

    def test_unverifiable_live_receipt_is_never_reaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gpu, suite, coordinator = self.paths(root)
            receipt = {
                "lock_schema_version": 1,
                "pid": os.getpid(),
                "process_create_time": 1.0,
                "nonce": "b" * 64,
                "role": "suite",
                "created_at_unix": 1.0,
            }
            lab_locks.create_receipt_exclusive(suite, receipt)
            lease = lab_locks.GpuLease(gpu, suite, coordinator)
            with (
                mock.patch.object(lab_locks.psutil, "pid_exists", return_value=True),
                mock.patch.object(
                    lab_locks,
                    "process_create_time",
                    side_effect=lab_locks.LeaseError("access denied"),
                ),
            ):
                with self.assertRaises(lab_locks.LeaseError):
                    lease.acquire()
            self.assertTrue(suite.exists())
            self.assertFalse(gpu.exists())

    def test_suite_refuses_foreign_live_gpu_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gpu, suite, coordinator = self.paths(root)
            foreign = lab_locks.new_lock_receipt("standalone")
            lab_locks.create_receipt_exclusive(gpu, foreign)
            lease = lab_locks.SuiteLease(suite, gpu, coordinator)
            with self.assertRaises(lab_locks.LeaseError):
                lease.acquire()
            self.assertTrue(gpu.exists())
            self.assertFalse(suite.exists())

    def test_replaced_gpu_receipt_is_not_unlinked_on_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gpu, suite, coordinator = self.paths(root)
            lease = lab_locks.GpuLease(gpu, suite, coordinator)
            lease.acquire()
            replacement = lab_locks.new_lock_receipt("standalone")
            gpu.write_bytes(
                (json.dumps(replacement, sort_keys=True, separators=(",", ":")) + "\n").encode(
                    "utf-8"
                )
            )
            with self.assertRaises(lab_locks.LeaseError):
                lease.release()
            self.assertTrue(gpu.exists())
            self.assertEqual(lab_locks.read_lock_receipt(gpu)["nonce"], replacement["nonce"])

            # A failed nonce check must still release the OS coordinator.
            probe = lab_locks.CoordinatorMutex(coordinator)
            probe.acquire()
            probe.release()

    def test_preacquired_runner_context_defers_release_to_outer_finalizer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gpu, suite, coordinator = self.paths(root)
            manager = run_recipe.LockManager(
                gpu, suite_lock_path=suite, coordinator_path=coordinator
            )
            manager.acquire()
            with manager:
                self.assertTrue(manager.acquired)
            self.assertTrue(manager.acquired)
            self.assertTrue(gpu.exists())
            manager.release()
            self.assertFalse(gpu.exists())

    def test_suite_flag_without_complete_verified_token_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gpu, suite, coordinator = self.paths(root)
            lease = lab_locks.GpuLease(
                gpu, suite, coordinator, suite_child=True, environment={}
            )
            with self.assertRaises(lab_locks.LeaseError):
                lease.acquire()

    def test_suite_child_rejects_spoofed_or_dead_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gpu, suite, coordinator = self.paths(root)
            owner = lab_locks.SuiteLease(suite, gpu, coordinator)
            owner.acquire()
            env = owner.child_environment({})
            child = lab_locks.GpuLease(
                gpu, suite, coordinator, suite_child=True, environment=env
            )
            with mock.patch.object(lab_locks.os, "getppid", return_value=os.getpid() + 1):
                with self.assertRaises(lab_locks.LeaseError):
                    child.acquire()

            with (
                mock.patch.object(lab_locks.os, "getppid", return_value=os.getpid()),
                mock.patch.object(lab_locks, "process_identity_is_live", return_value=False),
            ):
                with self.assertRaises(lab_locks.LeaseError):
                    child.acquire()
            owner.release()

    @unittest.skipUnless(os.name == "nt", "Windows venv launcher behavior")
    def test_suite_child_accepts_exact_windows_venv_launcher_chain(self):
        if sys.prefix == sys.base_prefix or not (Path(sys.prefix) / "pyvenv.cfg").is_file():
            self.skipTest("test interpreter is not running from a virtual environment")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gpu, suite, coordinator = self.paths(root)
            owner = lab_locks.SuiteLease(suite, gpu, coordinator)
            owner.acquire()
            script = (
                "import json, os, psutil, sys; from pathlib import Path; import lab_locks; "
                "lease=lab_locks.GpuLease(Path(sys.argv[1]),Path(sys.argv[2]),"
                "Path(sys.argv[3]),suite_child=True,environment=os.environ); "
                "lease.acquire(); parent=psutil.Process(os.getppid()); "
                "print(json.dumps({'launcher_pid':parent.pid,'launcher_ppid':parent.ppid(),"
                "'launcher_exe':parent.exe()}),flush=True); lease.release()"
            )
            try:
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        script,
                        str(gpu),
                        str(suite),
                        str(coordinator),
                    ],
                    cwd=Path(__file__).resolve().parents[1],
                    env=owner.child_environment(os.environ.copy()),
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
            finally:
                owner.release()

            self.assertEqual(completed.returncode, 0, completed.stderr)
            ancestry = json.loads(completed.stdout)
            self.assertEqual(ancestry["launcher_ppid"], os.getpid())
            self.assertEqual(
                os.path.normcase(str(Path(ancestry["launcher_exe"]).resolve())),
                os.path.normcase(str(Path(sys.executable).resolve())),
            )

    def test_authorized_suite_child_never_removes_parent_gpu_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gpu, suite, coordinator = self.paths(root)
            owner = lab_locks.SuiteLease(suite, gpu, coordinator)
            owner.acquire()
            child = lab_locks.GpuLease(
                gpu,
                suite,
                coordinator,
                suite_child=True,
                environment=owner.child_environment({}),
            )
            with mock.patch.object(lab_locks.os, "getppid", return_value=os.getpid()):
                child.acquire()
            child.release()
            self.assertTrue(gpu.exists())
            self.assertTrue(suite.exists())
            owner.release()
            self.assertFalse(gpu.exists())
            self.assertFalse(suite.exists())

    def test_suite_release_checkpoints_receipt_failure_while_coordinator_held(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gpu, suite, coordinator = self.paths(root)
            lease = lab_locks.SuiteLease(suite, gpu, coordinator)
            lease.acquire()
            replacement = lab_locks.new_lock_receipt("standalone")
            gpu.write_bytes(
                (json.dumps(replacement, sort_keys=True, separators=(",", ":")) + "\n").encode(
                    "utf-8"
                )
            )
            checkpoints = []

            def checkpoint(errors):
                self.assertTrue(lease.coordinator.acquired)
                checkpoints.append(tuple(errors))

            with self.assertRaises(lab_locks.LeaseError):
                lease.release(checkpoint=checkpoint)

            self.assertEqual(len(checkpoints), 1)
            self.assertTrue(any("owner nonce or identity changed" in error for error in checkpoints[0]))
            self.assertFalse(lease.coordinator.acquired)
            self.assertTrue(gpu.exists())
            self.assertEqual(lab_locks.read_lock_receipt(gpu)["nonce"], replacement["nonce"])


class TestShutdownProof(unittest.TestCase):
    def setUp(self):
        # These legacy tests isolate PID-receipt/termination behavior.  The
        # hardened runner now also requires a valid immutable idle-gate
        # sidecar for every owned server, so provide that independent proof
        # without adding a second filesystem unlink to the retry assertions.
        process = mock.Mock()
        process.create_time.return_value = 50.0
        self._process_patch = mock.patch.object(
            run_recipe.psutil, "Process", return_value=process
        )
        self._sidecar_snapshot_patch = mock.patch.object(
            run_recipe,
            "_snapshot_server_idle_gate_sidecar_for_cleanup",
            return_value={"metadata": {"server_instance": {}}, "raw": b"sealed"},
        )
        self._sidecar_remove_patch = mock.patch.object(
            run_recipe,
            "_remove_server_idle_gate_sidecar_after_proved_exit",
            return_value=(True, ""),
        )
        self._process_patch.start()
        self._sidecar_snapshot_patch.start()
        self._sidecar_remove_patch.start()
        self.addCleanup(self._sidecar_remove_patch.stop)
        self.addCleanup(self._sidecar_snapshot_patch.stop)
        self.addCleanup(self._process_patch.stop)

    def test_stale_pid_cleanup_retains_unverifiable_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("not-a-pid", encoding="utf-8")
            with mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt):
                removed = run_recipe.cleanup_stale_pid_receipt()
            self.assertFalse(removed)
            self.assertTrue(receipt.exists())

    def test_stale_pid_cleanup_requires_port_to_be_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=False),
                mock.patch.object(run_recipe, "query_server_stats", return_value={"live": True}),
                mock.patch.object(run_recipe, "listener_pid", return_value=456),
            ):
                removed = run_recipe.cleanup_stale_pid_receipt()
            self.assertFalse(removed)
            self.assertTrue(receipt.exists())

    def test_termination_failure_returns_failure_and_retains_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=True),
                mock.patch.object(run_recipe, "is_expected_lab_server_pid", return_value=True),
                mock.patch.object(run_recipe, "listener_pid", return_value=123),
                mock.patch.object(run_recipe, "query_server_stats", return_value={}),
                mock.patch.object(
                    run_recipe, "terminate_owned_process_tree", return_value=False
                ),
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertFalse(result["success"])
            self.assertTrue(result["termination_attempted"])
            self.assertFalse(result["receipt_removed"])
            self.assertTrue(receipt.exists())

    def test_foreign_listener_prevents_termination_and_retains_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=True),
                mock.patch.object(run_recipe, "is_expected_lab_server_pid", return_value=True),
                mock.patch.object(run_recipe, "listener_pid", return_value=456),
                mock.patch.object(run_recipe, "query_server_stats", return_value={"live": True}),
                mock.patch.object(run_recipe, "terminate_owned_process_tree") as terminate,
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertFalse(result["success"])
            self.assertTrue(receipt.exists())
            terminate.assert_not_called()

    def test_stale_shutdown_retries_transient_receipt_unlink_after_clear_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            path_type = type(receipt)
            real_unlink = path_type.unlink
            unlink_attempts = 0

            def flaky_unlink(path, *args, **kwargs):
                nonlocal unlink_attempts
                unlink_attempts += 1
                if unlink_attempts < 3:
                    raise PermissionError(13, "transient sharing violation", str(path))
                return real_unlink(path, *args, **kwargs)

            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=False),
                mock.patch.object(run_recipe, "query_server_stats", return_value=None),
                mock.patch.object(run_recipe, "listener_pid", return_value=None),
                mock.patch.object(path_type, "unlink", autospec=True, side_effect=flaky_unlink),
                mock.patch.object(run_recipe.time, "sleep") as sleep,
                mock.patch.object(run_recipe, "terminate_owned_process_tree") as terminate,
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertTrue(result["success"])
            self.assertTrue(result["process_exited"])
            self.assertTrue(result["listener_exited"])
            self.assertTrue(result["receipt_removed"])
            self.assertFalse(receipt.exists())
            self.assertEqual(unlink_attempts, 3)
            self.assertEqual(sleep.call_count, 2)
            terminate.assert_not_called()

    def test_stale_shutdown_bounds_persistent_receipt_unlink_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            path_type = type(receipt)

            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=False),
                mock.patch.object(run_recipe, "query_server_stats", return_value=None),
                mock.patch.object(run_recipe, "listener_pid", return_value=None),
                mock.patch.object(
                    path_type,
                    "unlink",
                    autospec=True,
                    side_effect=PermissionError(13, "persistent sharing violation"),
                ) as unlink,
                mock.patch.object(run_recipe.time, "sleep") as sleep,
                mock.patch.object(run_recipe, "terminate_owned_process_tree") as terminate,
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertFalse(result["success"])
            self.assertTrue(result["process_exited"])
            self.assertTrue(result["listener_exited"])
            self.assertFalse(result["receipt_removed"])
            self.assertTrue(receipt.exists())
            self.assertIn(
                f"after {run_recipe.SERVER_PID_UNLINK_ATTEMPTS} attempts",
                result["reason"],
            )
            self.assertEqual(unlink.call_count, run_recipe.SERVER_PID_UNLINK_ATTEMPTS)
            self.assertEqual(
                sleep.call_count,
                run_recipe.SERVER_PID_UNLINK_ATTEMPTS - 1,
            )
            self.assertLessEqual(
                sum(call.args[0] for call in sleep.call_args_list),
                2.0,
            )
            terminate.assert_not_called()

    def test_live_shutdown_retries_only_unlink_and_never_termination(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            path_type = type(receipt)
            real_unlink = path_type.unlink
            alive = {"value": True}
            unlink_attempts = 0

            def terminate(_pid):
                alive["value"] = False
                return True

            def flaky_unlink(path, *args, **kwargs):
                nonlocal unlink_attempts
                unlink_attempts += 1
                if unlink_attempts < 3:
                    raise PermissionError(13, "transient sharing violation", str(path))
                return real_unlink(path, *args, **kwargs)

            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(
                    run_recipe.psutil,
                    "pid_exists",
                    side_effect=lambda _pid: alive["value"],
                ),
                mock.patch.object(run_recipe, "is_expected_lab_server_pid", return_value=True),
                mock.patch.object(
                    run_recipe,
                    "listener_pid",
                    side_effect=lambda _port, **_kwargs: 123 if alive["value"] else None,
                ),
                mock.patch.object(run_recipe, "query_server_stats", return_value=None),
                mock.patch.object(
                    run_recipe, "terminate_owned_process_tree", side_effect=terminate
                ) as terminate_mock,
                mock.patch.object(path_type, "unlink", autospec=True, side_effect=flaky_unlink),
                mock.patch.object(run_recipe.time, "sleep"),
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertTrue(result["success"])
            self.assertTrue(result["termination_attempted"])
            self.assertTrue(result["receipt_removed"])
            self.assertEqual(unlink_attempts, 3)
            terminate_mock.assert_called_once_with(123)

    def test_unlink_retry_fails_closed_on_receipt_content_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            path_type = type(receipt)
            unlink_attempts = 0

            def drift_then_fail(path, *args, **kwargs):
                nonlocal unlink_attempts
                unlink_attempts += 1
                path.write_text("456", encoding="utf-8")
                raise PermissionError(13, "sharing violation after drift", str(path))

            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=False),
                mock.patch.object(run_recipe, "query_server_stats", return_value=None),
                mock.patch.object(run_recipe, "listener_pid", return_value=None),
                mock.patch.object(path_type, "unlink", autospec=True, side_effect=drift_then_fail),
                mock.patch.object(run_recipe.time, "sleep") as sleep,
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertFalse(result["success"])
            self.assertFalse(result["receipt_removed"])
            self.assertEqual(receipt.read_text(encoding="utf-8"), "456")
            self.assertEqual(unlink_attempts, 1)
            self.assertEqual(sleep.call_count, 1)
            self.assertIn("identity/content drifted", result["reason"])

    def test_unlink_retry_fails_closed_on_receipt_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            path_type = type(receipt)
            real_unlink = path_type.unlink
            initial = receipt.stat()
            unlink_attempts = 0

            def replace_then_fail(path, *args, **kwargs):
                nonlocal unlink_attempts
                unlink_attempts += 1
                real_unlink(path)
                path.write_text("123", encoding="utf-8")
                os.utime(
                    path,
                    ns=(initial.st_atime_ns, initial.st_mtime_ns + 1_000_000_000),
                )
                raise PermissionError(13, "sharing violation after replacement", str(path))

            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=False),
                mock.patch.object(run_recipe, "query_server_stats", return_value=None),
                mock.patch.object(run_recipe, "listener_pid", return_value=None),
                mock.patch.object(path_type, "unlink", autospec=True, side_effect=replace_then_fail),
                mock.patch.object(run_recipe.time, "sleep"),
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertFalse(result["success"])
            self.assertTrue(receipt.exists())
            self.assertEqual(unlink_attempts, 1)
            self.assertIn("identity/content drifted", result["reason"])

    def test_unlink_retry_fails_closed_if_hardlink_appears(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            external = Path(tmp) / "external.pid"
            receipt.write_text("123", encoding="utf-8")
            path_type = type(receipt)
            unlink_attempts = 0

            def link_then_fail(path, *args, **kwargs):
                nonlocal unlink_attempts
                unlink_attempts += 1
                os.link(path, external)
                raise PermissionError(13, "sharing violation after hardlink", str(path))

            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=False),
                mock.patch.object(run_recipe, "query_server_stats", return_value=None),
                mock.patch.object(run_recipe, "listener_pid", return_value=None),
                mock.patch.object(path_type, "unlink", autospec=True, side_effect=link_then_fail),
                mock.patch.object(run_recipe.time, "sleep"),
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertFalse(result["success"])
            self.assertTrue(receipt.exists())
            self.assertTrue(external.exists())
            self.assertEqual(unlink_attempts, 1)
            self.assertIn("exactly one hardlink", result["reason"])

    def test_unlink_retry_fails_closed_if_pid_becomes_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            path_type = type(receipt)

            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(
                    run_recipe.psutil, "pid_exists", side_effect=[False, False, True]
                ),
                mock.patch.object(run_recipe, "query_server_stats", return_value=None),
                mock.patch.object(run_recipe, "listener_pid", return_value=None),
                mock.patch.object(
                    path_type,
                    "unlink",
                    autospec=True,
                    side_effect=PermissionError(13, "first unlink blocked"),
                ) as unlink,
                mock.patch.object(run_recipe.time, "sleep"),
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertFalse(result["success"])
            self.assertTrue(receipt.exists())
            self.assertEqual(unlink.call_count, 1)
            self.assertIn("became live", result["reason"])

    def test_unlink_retry_fails_closed_if_listener_appears(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            path_type = type(receipt)

            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=False),
                mock.patch.object(run_recipe, "query_server_stats", return_value=None),
                mock.patch.object(
                    run_recipe, "listener_pid", side_effect=[None, None, 456]
                ),
                mock.patch.object(
                    path_type,
                    "unlink",
                    autospec=True,
                    side_effect=PermissionError(13, "first unlink blocked"),
                ) as unlink,
                mock.patch.object(run_recipe.time, "sleep"),
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertFalse(result["success"])
            self.assertTrue(receipt.exists())
            self.assertEqual(unlink.call_count, 1)
            self.assertIn("port 8199 became live", result["reason"])

    def test_unlink_retry_fails_closed_if_server_stats_appear(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            path_type = type(receipt)

            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=False),
                mock.patch.object(
                    run_recipe,
                    "query_server_stats",
                    side_effect=[None, None, {"live": True}],
                ),
                mock.patch.object(run_recipe, "listener_pid", return_value=None),
                mock.patch.object(
                    path_type,
                    "unlink",
                    autospec=True,
                    side_effect=PermissionError(13, "first unlink blocked"),
                ) as unlink,
                mock.patch.object(run_recipe.time, "sleep"),
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertFalse(result["success"])
            self.assertTrue(receipt.exists())
            self.assertEqual(unlink.call_count, 1)
            self.assertIn("port 8199 became live", result["reason"])

    def test_unlink_retry_treats_empty_server_stats_response_as_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=False),
                mock.patch.object(run_recipe, "query_server_stats", return_value={}),
                mock.patch.object(run_recipe, "listener_pid", return_value=None),
                mock.patch.object(run_recipe.time, "sleep") as sleep,
                mock.patch.object(run_recipe, "terminate_owned_process_tree") as terminate,
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertFalse(result["success"])
            self.assertFalse(result["process_exited"])
            self.assertFalse(result["listener_exited"])
            self.assertFalse(result["receipt_removed"])
            self.assertTrue(receipt.exists())
            self.assertIn("unverified server", result["reason"])
            sleep.assert_not_called()
            terminate.assert_not_called()

    def test_unlink_retry_fails_closed_if_listener_enumeration_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            path_type = type(receipt)
            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=False),
                mock.patch.object(
                    run_recipe.psutil,
                    "net_connections",
                    side_effect=run_recipe.psutil.AccessDenied(pid=456),
                ),
                mock.patch.object(run_recipe, "query_server_stats", return_value=None),
                mock.patch.object(path_type, "unlink", autospec=True) as unlink,
                mock.patch.object(run_recipe.time, "sleep") as sleep,
                mock.patch.object(run_recipe, "terminate_owned_process_tree") as terminate,
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertFalse(result["success"])
            self.assertFalse(result["receipt_removed"])
            self.assertTrue(receipt.exists())
            self.assertIn("could not re-prove clear port 8199", result["reason"])
            unlink.assert_not_called()
            sleep.assert_not_called()
            terminate.assert_not_called()

    def test_unlink_retry_fails_closed_if_listener_owner_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            path_type = type(receipt)
            connection = mock.Mock(
                laddr=("127.0.0.1", int(run_recipe.LAB_PORT)),
                status=run_recipe.psutil.CONN_LISTEN,
                pid=None,
            )
            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(run_recipe.psutil, "pid_exists", return_value=False),
                mock.patch.object(
                    run_recipe.psutil, "net_connections", return_value=[connection]
                ),
                mock.patch.object(run_recipe, "query_server_stats", return_value=None),
                mock.patch.object(path_type, "unlink", autospec=True) as unlink,
                mock.patch.object(run_recipe.time, "sleep") as sleep,
                mock.patch.object(run_recipe, "terminate_owned_process_tree") as terminate,
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertFalse(result["success"])
            self.assertFalse(result["receipt_removed"])
            self.assertTrue(receipt.exists())
            self.assertIn("could not re-prove clear port 8199", result["reason"])
            unlink.assert_not_called()
            sleep.assert_not_called()
            terminate.assert_not_called()

    def test_shutdown_rejects_reparse_receipt_before_process_or_port_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / ".server.pid"
            receipt.write_text("123", encoding="utf-8")
            with (
                mock.patch.object(run_recipe, "SERVER_PID_FILE", receipt),
                mock.patch.object(
                    run_recipe, "_is_symlink_or_reparse_point", return_value=True
                ),
                mock.patch.object(run_recipe.psutil, "pid_exists") as pid_exists,
                mock.patch.object(run_recipe, "query_server_stats") as stats,
                mock.patch.object(run_recipe, "listener_pid") as listener,
                mock.patch.object(run_recipe, "terminate_owned_process_tree") as terminate,
            ):
                result = run_recipe.shutdown_lab_server()

            self.assertFalse(result["success"])
            self.assertTrue(receipt.exists())
            self.assertIn("regular non-reparse", result["reason"])
            pid_exists.assert_not_called()
            stats.assert_not_called()
            listener.assert_not_called()
            terminate.assert_not_called()

if __name__ == "__main__":
    unittest.main()
