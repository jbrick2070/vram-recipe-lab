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


if __name__ == "__main__":
    unittest.main()
