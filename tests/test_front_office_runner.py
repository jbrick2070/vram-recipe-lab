import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import front_office
import run_recipe


class _FakeProcess:
    def __init__(
        self,
        pid,
        *,
        children=(),
        parent_pid=1,
        create_time=1.0,
        executable="C:/test/python.exe",
        command_line=(),
        poll_result=None,
    ):
        self.pid = pid
        self._children = list(children)
        self._parent_pid = parent_pid
        self._create_time = create_time
        self._executable = executable
        self._command_line = list(command_line)
        self._poll_result = poll_result

    def children(self, recursive=False):
        del recursive
        return list(self._children)

    def ppid(self):
        return self._parent_pid

    def create_time(self):
        return self._create_time

    def exe(self):
        return self._executable

    def cmdline(self):
        return list(self._command_line)

    def name(self):
        return Path(self._executable).name

    def poll(self):
        return self._poll_result


class FrontOfficeRunnerTests(unittest.TestCase):
    def setUp(self):
        self._previous_context = run_recipe.ACTIVE_FRONT_OFFICE_CONTEXT
        run_recipe.ACTIVE_FRONT_OFFICE_CONTEXT = None

    def tearDown(self):
        run_recipe.ACTIVE_FRONT_OFFICE_CONTEXT = self._previous_context

    def make_context(self, root: Path, *, profile_id="dispatchable-profile"):
        comfy_root = root / "comfy"
        comfy_root.mkdir(parents=True, exist_ok=True)
        (comfy_root / "main.py").write_text("# test\n", encoding="utf-8")
        recipe_path = root / "recipes" / "sealed.json"
        recipe_path.parent.mkdir(parents=True, exist_ok=True)
        recipe_path.write_text("{}\n", encoding="utf-8")
        spec_path = root / ".runtime" / "front-office-execution-test.json"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text("{}\n", encoding="utf-8")
        output = root / "outputs" / "ready-campaign" / "control-cell" / profile_id
        results = root / "results" / "runs" / "ready-campaign" / "control-cell" / profile_id
        logs = root / "logs" / "ready-campaign" / "control-cell" / profile_id
        user = root / ".front_office_state" / "ready-campaign" / "control-cell" / profile_id / "user"
        temp = root / ".front_office_state" / "ready-campaign" / "control-cell" / profile_id / "temp"
        for path in (output, results, logs, user, temp):
            path.mkdir(parents=True, exist_ok=True)
        server_argv = (
            str(root / "python.exe"),
            str(comfy_root / "main.py"),
            "--port",
            "8199",
            "--cuda-malloc",
            "--user-directory",
            str(user),
            "--output-directory",
            str(output),
            "--temp-directory",
            str(temp),
            "--extra-model-paths-config",
            str(root / "models.yaml"),
            "--disable-metadata",
            "--disable-all-custom-nodes",
            "--whitelist-custom-nodes",
            "OnlyNode",
        )
        return run_recipe.FrontOfficeRunContext(
            campaign_id="ready-campaign",
            cell_id="control-cell",
            profile_id=profile_id,
            profile_sha256="a" * 64,
            launch_spec_sha256="b" * 64,
            execution_spec_sha256="c" * 64,
            execution_spec_path=spec_path,
            lease_nonce="d" * 32,
            runner_bundle_sha256="e" * 64,
            front_office_bundle_sha256="f" * 64,
            comfyui_root=comfy_root,
            recipe_path=recipe_path,
            recipe_sha256=run_recipe.sha256_file(recipe_path),
            output_directory=output,
            result_directory=results,
            log_directory=logs,
            user_directory=user,
            temp_directory=temp,
            server_argv=server_argv,
            server_environment={"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            profile_whitelist=("OnlyNode",),
        )

    @staticmethod
    def claim_context(context):
        """Create the runner's real exclusive claim before receipt assertions."""

        run_recipe._claim_front_office_execution_spec(context)

    def test_front_office_argv_rejects_legacy_or_extra_runner_flags(self):
        with mock.patch.object(run_recipe, "_front_office_context_from_spec") as hydrate:
            for argv in (
                ["--front-office-spec"],
                ["--front-office-spec", "sealed.json", "--shutdown"],
                ["recipe.json", "--front-office-spec", "sealed.json"],
                ["--front-office-spec", "sealed.json", "--clamp", "8"],
                ["--front-office-spec", "a.json", "--front-office-spec", "b.json"],
            ):
                with self.assertRaises(ValueError):
                    run_recipe.activate_front_office_context_from_argv(argv)
        hydrate.assert_not_called()

    def test_sealed_spec_activation_preserves_profile_derived_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in (
                root / "outputs",
                root / "results" / "runs",
                root / "logs",
                root / ".front_office_state",
            ):
                path.mkdir(parents=True, exist_ok=True)
            context = self.make_context(root)
            profile = {
                "id": context.profile_id,
                "status": front_office.PROFILE_STATUS_DISPATCHABLE,
                "python": {"path": context.server_argv[0]},
                "comfyui": {"root": str(context.comfyui_root)},
                "model_paths_config": {"path": str(root / "models.yaml")},
                "environment": {
                    "PYTHONUTF8": "1",
                    "PYTHONIOENCODING": "utf-8",
                    "HF_HOME": str(root / "hf"),
                },
                "custom_nodes": [{"id": "OnlyNode"}],
                "boot": {
                    "fixed_argv": list(context.server_argv[2:]),
                },
            }
            namespaces = {
                "output_directory": str(context.output_directory),
                "result_directory": str(context.result_directory),
                "log_directory": str(context.log_directory),
                "user_directory": str(context.user_directory),
                "temp_directory": str(context.temp_directory),
            }
            server_argv = front_office.canonical_server_argv(profile, namespaces)
            environment = front_office.sanitized_child_environment(profile)
            spec = {
                "launch_spec_sha256": context.launch_spec_sha256,
                "lease_nonce": context.lease_nonce,
                "semantic": {
                    "campaign": {"id": context.campaign_id},
                    "cell": {"id": context.cell_id},
                    "profile": {
                        "id": context.profile_id,
                        "sha256": front_office.canonical_sha256(profile),
                    },
                    "recipe": {
                        "path": "recipes/sealed.json",
                        "sha256": context.recipe_sha256,
                    },
                    "namespaces": namespaces,
                    "server": {
                        "argv": server_argv,
                        "argv_sha256": front_office.canonical_sha256(server_argv),
                        "environment": environment,
                        "environment_sha256": front_office.canonical_sha256(environment),
                    },
                    "front_office": {"bundle_sha256": context.front_office_bundle_sha256},
                    "floor_runner": {"runner_bundle_sha256": context.runner_bundle_sha256},
                },
            }
            with mock.patch.object(run_recipe, "REPO_ROOT", root), mock.patch.object(
                front_office, "load_execution_spec", return_value=spec
            ), mock.patch.object(front_office, "validate_execution_spec"), mock.patch.object(
                front_office, "load_enrolled_profile", return_value=profile
            ):
                activated = run_recipe._front_office_context_from_spec(
                    str(context.execution_spec_path)
                )

            self.assertEqual(activated.comfyui_root, context.comfyui_root)
            self.assertEqual(activated.output_directory, context.output_directory)
            self.assertEqual(activated.result_directory, context.result_directory)
            self.assertEqual(activated.log_directory, context.log_directory)
            self.assertEqual(activated.user_directory, context.user_directory)
            self.assertEqual(activated.temp_directory, context.temp_directory)
            self.assertEqual(tuple(server_argv), activated.server_argv)
            self.assertEqual(activated.server_environment["HF_HOME"], str(root / "hf"))
            self.assertEqual(activated.server_environment["TEMP"], str(context.temp_directory))

    def test_prepare_namespace_creates_a_missing_fixed_root_under_the_repo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "results" / "runs" / "campaign" / "cell" / "profile"
            with mock.patch.object(run_recipe, "REPO_ROOT", root):
                prepared = run_recipe._front_office_prepare_namespace(
                    target, root / "results" / "runs", "result_directory"
                )

            self.assertEqual(prepared, target)
            self.assertTrue((root / "results" / "runs").is_dir())
            self.assertTrue(target.is_dir())

    def test_runtime_environment_retains_only_required_windows_programfiles(self):
        with mock.patch.dict(
            os.environ,
            {
                "ProgramFiles": "C:\\Program Files",
                "ProgramW6432": "C:\\Program Files",
                "CUDA_VISIBLE_DEVICES": "7",
            },
            clear=True,
        ):
            environment = run_recipe._front_office_runtime_environment(
                {
                    "PYTHONUTF8": "1",
                    "PYTHONIOENCODING": "utf-8",
                    "HF_HOME": "C:\\models\\huggingface",
                },
                Path("C:/trusted/temp"),
            )

        self.assertEqual(environment["ProgramFiles"], "C:\\Program Files")
        self.assertEqual(environment["ProgramW6432"], "C:\\Program Files")
        self.assertNotIn("CUDA_VISIBLE_DEVICES", environment)

    def test_activation_replaces_spec_token_with_only_the_pinned_recipe_and_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            context = self.make_context(Path(directory))
            with mock.patch.object(
                run_recipe, "_front_office_context_from_spec", return_value=context
            ) as hydrate:
                resolved = run_recipe.activate_front_office_context_from_argv(
                    ["--front-office-spec", "sealed.json"]
                )
        self.assertEqual(resolved, [str(context.recipe_path), "--shutdown"])
        self.assertIs(run_recipe.ACTIVE_FRONT_OFFICE_CONTEXT, context)
        hydrate.assert_called_once_with("sealed.json")

    def test_front_office_boot_uses_pinned_direct_argv_not_cmd(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = self.make_context(root)
            server_pid = root / ".server.pid"
            idle_sidecar = root / ".server.idle-gate.json"
            session_sidecar = root / ".front-office-server.json"
            process = _FakeProcess(4242)
            with mock.patch.object(run_recipe, "ACTIVE_FRONT_OFFICE_CONTEXT", context), mock.patch.object(
                run_recipe, "SERVER_PID_FILE", server_pid
            ), mock.patch.object(run_recipe, "SERVER_IDLE_GATE_FILE", idle_sidecar), mock.patch.object(
                run_recipe, "FRONT_OFFICE_SERVER_SESSION_FILE", session_sidecar
            ), mock.patch.object(run_recipe, "manager_probe_requested", return_value=False), mock.patch.object(
                run_recipe, "cleanup_stale_pid_receipt", return_value=False
            ), mock.patch.object(run_recipe.subprocess, "Popen", return_value=process) as popen, mock.patch.object(
                run_recipe, "query_server_stats", return_value={"system": {"argv": list(context.server_argv)}}
            ), mock.patch.object(run_recipe.psutil, "Process", return_value=process), mock.patch.object(
                run_recipe, "listener_pid", return_value=4242
            ), mock.patch.object(run_recipe, "is_expected_lab_server_pid", return_value=True), mock.patch.object(
                run_recipe, "verified_server_instance", return_value={"serving_pid": 4242, "process_create_time": 1.0}
            ), mock.patch.object(
                run_recipe, "_front_office_pinned_launcher_identity", return_value=None
            ), mock.patch.object(run_recipe, "_write_front_office_server_session") as write_session:
                stats = run_recipe.boot_lab_server()

            self.assertEqual(stats["system"]["argv"], list(context.server_argv))
            self.assertEqual(popen.call_args.args[0], list(context.server_argv))
            self.assertEqual(popen.call_args.kwargs["cwd"], str(context.comfyui_root))
            self.assertEqual(popen.call_args.kwargs["env"], dict(context.server_environment))
            self.assertFalse(popen.call_args.kwargs["shell"])
            self.assertNotIn("cmd.exe", [item.lower() for item in popen.call_args.args[0]])
            write_session.assert_called_once_with({"serving_pid": 4242, "process_create_time": 1.0})

    @staticmethod
    def launcher_child_identities(context, root, *, listener_created=100.1):
        """Return a uv-style launcher and real-CPython child identity pair."""

        launcher_pid = 10252
        listener_pid = 33908
        launcher_executable = context.server_argv[0]
        listener_executable = str(root / "uv-runtime" / "python.exe")
        launcher = {
            "pid": launcher_pid,
            "exists": True,
            "name": "python.exe",
            "executable": launcher_executable,
            "command_line": list(context.server_argv),
            "process_create_time": 100.0,
            "identity_errors": [],
        }
        listener = {
            "pid": listener_pid,
            "exists": True,
            "name": "python.exe",
            "executable": listener_executable,
            "command_line": [listener_executable, *context.server_argv[1:]],
            "process_create_time": listener_created,
            "identity_errors": [],
        }
        return launcher, listener

    @unittest.skipUnless(os.name == "nt", "Windows launcher substitution only")
    def test_windows_launcher_child_proof_is_exact_and_revalidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = self.make_context(root)
            launcher, listener = self.launcher_child_identities(context, root)
            launcher_process = _FakeProcess(
                launcher["pid"],
                create_time=launcher["process_create_time"],
                executable=launcher["executable"],
                command_line=launcher["command_line"],
            )
            listener_process = _FakeProcess(
                listener["pid"],
                parent_pid=launcher["pid"],
                create_time=listener["process_create_time"],
                executable=listener["executable"],
                command_line=listener["command_line"],
            )
            identities = {
                launcher["pid"]: launcher,
                listener["pid"]: listener,
            }
            processes = {
                launcher["pid"]: launcher_process,
                listener["pid"]: listener_process,
            }
            with mock.patch.object(run_recipe, "ACTIVE_FRONT_OFFICE_CONTEXT", context), mock.patch.object(
                run_recipe, "_idle_process_identity", side_effect=lambda pid: copy.deepcopy(identities[pid])
            ), mock.patch.object(
                run_recipe.psutil, "Process", side_effect=lambda pid: processes[pid]
            ), mock.patch.object(
                run_recipe.lab_locks, "process_identity_is_live", return_value=True
            ):
                proof = run_recipe._front_office_windows_launcher_child_proof(
                    launcher, listener["pid"]
                )
                self.assertIsNotNone(proof)
                self.assertEqual(proof["mode"], "windows-venv-launcher-child")
                self.assertTrue(
                    run_recipe._front_office_windows_launcher_child_proof_is_live(
                        proof, listener["pid"]
                    )
                )
                self.assertTrue(
                    run_recipe._front_office_retained_launcher_is_live(
                        proof,
                        expected_listener_pid=listener["pid"],
                        server_instance={
                            "serving_pid": listener["pid"],
                            "process_create_time": listener["process_create_time"],
                        },
                    )
                )
                self.assertFalse(
                    run_recipe._front_office_retained_launcher_is_live(
                        proof,
                        expected_listener_pid=listener["pid"],
                        server_instance={
                            "serving_pid": listener["pid"] + 1,
                            "process_create_time": listener["process_create_time"],
                        },
                    )
                )

                for label, mutate_process, mutate_identity in (
                    (
                        "wrong-parent",
                        lambda: setattr(listener_process, "_parent_pid", 7),
                        lambda: None,
                    ),
                    (
                        "wrong-argv-tail",
                        lambda: None,
                        lambda: identities[listener["pid"]].update(
                            command_line=[listener["executable"], "tampered.py"]
                        ),
                    ),
                    (
                        "same-executable",
                        lambda: None,
                        lambda: identities[listener["pid"]].update(
                            executable=launcher["executable"]
                        ),
                    ),
                    (
                        "non-python-child",
                        lambda: None,
                        lambda: identities[listener["pid"]].update(
                            executable=str(root / "uv-runtime" / "not-python.exe")
                        ),
                    ),
                    (
                        "late-child",
                        lambda: None,
                        lambda: identities[listener["pid"]].update(
                            process_create_time=106.0
                        ),
                    ),
                ):
                    with self.subTest(label=label):
                        identities[listener["pid"]] = copy.deepcopy(listener)
                        listener_process._parent_pid = launcher["pid"]
                        mutate_process()
                        mutate_identity()
                        self.assertIsNone(
                            run_recipe._front_office_windows_launcher_child_proof(
                                launcher, listener["pid"]
                            )
                        )

    @unittest.skipUnless(os.name == "nt", "Windows launcher substitution only")
    def test_boot_accepts_only_the_proven_windows_launcher_child(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = self.make_context(root)
            self.claim_context(context)
            server_pid = root / ".server.pid"
            idle_sidecar = root / ".server.idle-gate.json"
            session_sidecar = root / ".front-office-server.json"
            launcher, listener = self.launcher_child_identities(context, root)
            listener_process = _FakeProcess(
                listener["pid"],
                parent_pid=launcher["pid"],
                create_time=listener["process_create_time"],
                executable=listener["executable"],
                command_line=listener["command_line"],
            )
            launcher_process = _FakeProcess(
                launcher["pid"],
                children=(),  # force the proof, rather than tree enumeration, to decide
                create_time=launcher["process_create_time"],
                executable=launcher["executable"],
                command_line=launcher["command_line"],
            )
            identities = {
                launcher["pid"]: launcher,
                listener["pid"]: listener,
            }
            processes = {
                launcher["pid"]: launcher_process,
                listener["pid"]: listener_process,
            }
            instance = {
                "serving_pid": listener["pid"],
                "process_create_time": listener["process_create_time"],
            }
            with mock.patch.object(run_recipe, "ACTIVE_FRONT_OFFICE_CONTEXT", context), mock.patch.object(
                run_recipe, "SERVER_PID_FILE", server_pid
            ), mock.patch.object(run_recipe, "SERVER_IDLE_GATE_FILE", idle_sidecar), mock.patch.object(
                run_recipe, "FRONT_OFFICE_SERVER_SESSION_FILE", session_sidecar
            ), mock.patch.object(run_recipe, "manager_probe_requested", return_value=False), mock.patch.object(
                run_recipe, "cleanup_stale_pid_receipt", return_value=False
            ), mock.patch.object(
                run_recipe.subprocess, "Popen", return_value=launcher_process
            ) as popen, mock.patch.object(
                run_recipe, "query_server_stats", return_value={"system": {"argv": list(context.server_argv)}}
            ), mock.patch.object(
                run_recipe, "listener_pid", return_value=listener["pid"]
            ), mock.patch.object(
                run_recipe, "_idle_process_identity", side_effect=lambda pid: copy.deepcopy(identities[pid])
            ), mock.patch.object(
                run_recipe.psutil, "Process", side_effect=lambda pid: processes[pid]
            ), mock.patch.object(
                run_recipe.psutil, "pid_exists", side_effect=lambda pid: pid in processes
            ), mock.patch.object(
                run_recipe.lab_locks, "process_identity_is_live", return_value=True
            ):
                stats = run_recipe.boot_lab_server()
                self.assertEqual(stats["system"]["argv"], list(context.server_argv))
                self.assertEqual(popen.call_args.args[0], list(context.server_argv))
                self.assertFalse(popen.call_args.kwargs["shell"])
                self.assertEqual(run_recipe.verified_server_instance(), instance)

            payload = json.loads(session_sidecar.read_text(encoding="utf-8"))
            self.assertEqual(
                payload[run_recipe.FRONT_OFFICE_WINDOWS_LAUNCHER_CHILD_KEY]["launcher"]["pid"],
                launcher["pid"],
            )
            self.assertEqual(
                payload[run_recipe.FRONT_OFFICE_WINDOWS_LAUNCHER_CHILD_KEY]["listener"]["pid"],
                listener["pid"],
            )

    @unittest.skipUnless(os.name == "nt", "Windows launcher substitution only")
    def test_stale_front_office_listener_terminates_the_proven_launcher_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = self.make_context(root)
            self.claim_context(context)
            server_pid = root / ".server.pid"
            server_pid.write_text("33908\n", encoding="utf-8")
            session_sidecar = root / ".front-office-server.json"
            launcher, listener = self.launcher_child_identities(context, root)
            launcher_process = _FakeProcess(
                launcher["pid"],
                create_time=launcher["process_create_time"],
                executable=launcher["executable"],
                command_line=launcher["command_line"],
            )
            listener_process = _FakeProcess(
                listener["pid"],
                parent_pid=launcher["pid"],
                create_time=listener["process_create_time"],
                executable=listener["executable"],
                command_line=listener["command_line"],
            )
            identities = {
                launcher["pid"]: launcher,
                listener["pid"]: listener,
            }
            processes = {
                launcher["pid"]: launcher_process,
                listener["pid"]: listener_process,
            }
            instance = {
                "serving_pid": listener["pid"],
                "process_create_time": listener["process_create_time"],
            }
            state = {"launcher_live": True, "listener_live": False}

            def pid_exists(pid):
                if pid == launcher["pid"]:
                    return state["launcher_live"]
                if pid == listener["pid"]:
                    return state["listener_live"]
                return False

            def terminate_root(pid):
                self.assertEqual(pid, launcher["pid"])
                state["launcher_live"] = False
                return True

            with mock.patch.object(run_recipe, "ACTIVE_FRONT_OFFICE_CONTEXT", context), mock.patch.object(
                run_recipe, "SERVER_PID_FILE", server_pid
            ), mock.patch.object(
                run_recipe, "FRONT_OFFICE_SERVER_SESSION_FILE", session_sidecar
            ), mock.patch.object(
                run_recipe, "_idle_process_identity", side_effect=lambda pid: copy.deepcopy(identities[pid])
            ), mock.patch.object(
                run_recipe.psutil, "Process", side_effect=lambda pid: processes[pid]
            ), mock.patch.object(
                run_recipe.psutil, "pid_exists", side_effect=pid_exists
            ), mock.patch.object(
                run_recipe.lab_locks, "process_identity_is_live", return_value=True
            ), mock.patch.object(
                run_recipe, "_snapshot_server_pid_receipt", return_value={"pid": listener["pid"]}
            ), mock.patch.object(
                run_recipe, "_snapshot_server_idle_gate_sidecar_for_cleanup", return_value={"idle": "proof"}
            ), mock.patch.object(
                run_recipe, "_remove_server_idle_gate_sidecar_after_proved_exit", return_value=(True, "")
            ), mock.patch.object(
                run_recipe, "_remove_server_pid_receipt_after_proved_exit", return_value=(True, "")
            ), mock.patch.object(
                run_recipe, "query_server_stats", return_value=None
            ), mock.patch.object(
                run_recipe, "listener_pid", return_value=None
            ), mock.patch.object(
                run_recipe, "terminate_owned_process_tree", side_effect=terminate_root
            ) as terminate:
                proof = run_recipe._front_office_windows_launcher_child_proof(
                    launcher, listener["pid"]
                )
                session_sidecar.write_bytes(
                    run_recipe.canonical_json_bytes(
                        run_recipe._front_office_server_session_payload(
                            instance,
                            windows_venv_launcher_child=proof,
                        )
                    )
                )
                result = run_recipe.shutdown_lab_server()

            terminate.assert_called_once_with(launcher["pid"])
            self.assertTrue(result["success"])
            self.assertEqual(result["termination_root_pid"], launcher["pid"])
            self.assertTrue(result["termination_root_exited"])
            self.assertTrue(result["front_office_server_session_removed"])
            self.assertFalse(session_sidecar.exists())

    def test_stale_dead_launcher_preserves_misbinding_proof_receipts(self):
        """A dead launcher cannot excuse a sidecar proof for another listener."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = self.make_context(root)
            self.claim_context(context)
            server_pid = root / ".server.pid"
            server_pid.write_text("33908\n", encoding="utf-8")
            idle_sidecar = root / ".server.idle-gate.json"
            session_sidecar = root / ".front-office-server.json"
            launcher, listener = self.launcher_child_identities(context, root)
            instance = {
                "serving_pid": listener["pid"],
                "process_create_time": listener["process_create_time"],
            }
            proof = {
                "mode": "windows-venv-launcher-child",
                "launcher": copy.deepcopy(launcher),
                "listener": copy.deepcopy(listener),
                "direct_parent_verified": True,
                "argv_tail_matches": True,
                "listener_executable_differs": True,
                "creation_delta_s": 0.1,
            }
            proof["listener"]["pid"] += 1

            with mock.patch.object(run_recipe, "ACTIVE_FRONT_OFFICE_CONTEXT", context), mock.patch.object(
                run_recipe, "SERVER_PID_FILE", server_pid
            ), mock.patch.object(run_recipe, "SERVER_IDLE_GATE_FILE", idle_sidecar), mock.patch.object(
                run_recipe, "FRONT_OFFICE_SERVER_SESSION_FILE", session_sidecar
            ), mock.patch.object(
                run_recipe.psutil, "pid_exists", return_value=False
            ), mock.patch.object(
                run_recipe, "_snapshot_server_pid_receipt", return_value={"pid": listener["pid"]}
            ), mock.patch.object(
                run_recipe, "_snapshot_server_idle_gate_sidecar_for_cleanup", return_value={"idle": "proof"}
            ), mock.patch.object(
                run_recipe, "_remove_server_idle_gate_sidecar_after_proved_exit", return_value=(True, "")
            ) as remove_idle, mock.patch.object(
                run_recipe, "_remove_server_pid_receipt_after_proved_exit", return_value=(True, "")
            ) as remove_pid, mock.patch.object(
                run_recipe, "query_server_stats", return_value=None
            ), mock.patch.object(
                run_recipe, "listener_pid", return_value=None
            ), mock.patch.object(run_recipe, "terminate_owned_process_tree") as terminate:
                session_sidecar.write_bytes(
                    run_recipe.canonical_json_bytes(
                        run_recipe._front_office_server_session_payload(
                            instance,
                            windows_venv_launcher_child=proof,
                        )
                    )
                )
                result = run_recipe.shutdown_lab_server()

            self.assertFalse(result["success"])
            self.assertIn("does not bind the recorded listener", result["reason"])
            terminate.assert_not_called()
            remove_idle.assert_not_called()
            remove_pid.assert_not_called()
            self.assertTrue(server_pid.exists())
            self.assertTrue(session_sidecar.exists())

    def test_stale_direct_front_office_listener_records_dead_listener_as_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = self.make_context(root)
            self.claim_context(context)
            server_pid = root / ".server.pid"
            server_pid.write_text("4242\n", encoding="utf-8")
            idle_sidecar = root / ".server.idle-gate.json"
            session_sidecar = root / ".front-office-server.json"
            instance = {"serving_pid": 4242, "process_create_time": 12.0}
            with mock.patch.object(run_recipe, "ACTIVE_FRONT_OFFICE_CONTEXT", context):
                session_sidecar.write_bytes(
                    run_recipe.canonical_json_bytes(
                        run_recipe._front_office_server_session_payload(instance)
                    )
                )
            with mock.patch.object(run_recipe, "ACTIVE_FRONT_OFFICE_CONTEXT", context), mock.patch.object(
                run_recipe, "SERVER_PID_FILE", server_pid
            ), mock.patch.object(run_recipe, "SERVER_IDLE_GATE_FILE", idle_sidecar), mock.patch.object(
                run_recipe, "FRONT_OFFICE_SERVER_SESSION_FILE", session_sidecar
            ), mock.patch.object(
                run_recipe.psutil, "pid_exists", return_value=False
            ), mock.patch.object(
                run_recipe, "_snapshot_server_pid_receipt", return_value={"pid": 4242}
            ), mock.patch.object(
                run_recipe, "_snapshot_server_idle_gate_sidecar_for_cleanup", return_value={"idle": "proof"}
            ), mock.patch.object(
                run_recipe, "_remove_server_idle_gate_sidecar_after_proved_exit", return_value=(True, "")
            ), mock.patch.object(
                run_recipe, "_remove_server_pid_receipt_after_proved_exit", return_value=(True, "")
            ), mock.patch.object(
                run_recipe, "query_server_stats", return_value=None
            ), mock.patch.object(
                run_recipe, "listener_pid", return_value=None
            ), mock.patch.object(
                run_recipe, "terminate_owned_process_tree"
            ) as terminate:
                result = run_recipe.shutdown_lab_server()

            terminate.assert_not_called()
            self.assertTrue(result["success"])
            self.assertEqual(result["termination_root_pid"], 4242)
            self.assertTrue(result["termination_root_exited"])
            self.assertTrue(result["front_office_server_session_removed"])
            self.assertFalse(session_sidecar.exists())

    def test_boot_lane_uses_exact_profile_whitelist(self):
        with tempfile.TemporaryDirectory() as directory:
            context = self.make_context(Path(directory))
            system_stats = {"system": {"argv": list(context.server_argv)}}
            with mock.patch.object(run_recipe, "ACTIVE_FRONT_OFFICE_CONTEXT", context), mock.patch.object(
                run_recipe, "manager_probe_requested", return_value=False
            ), mock.patch.object(run_recipe, "manager_probe_evidence", return_value={"enabled": False}), mock.patch.dict(
                os.environ, {}, clear=True
            ):
                self.assertEqual(run_recipe.check_boot_lane("sealed", system_stats), {"enabled": False})
                wrong = copy.deepcopy(system_stats)
                wrong["system"]["argv"].append("UnexpectedNode")
                with self.assertRaisesRegex(run_recipe.PreflightError, "exactly.*OnlyNode"):
                    run_recipe.check_boot_lane("sealed", wrong)

    def test_mismatched_session_sidecar_refuses_server_reuse_and_is_not_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.make_context(root, profile_id="profile-a")
            second = self.make_context(root, profile_id="profile-b")
            self.claim_context(first)
            sidecar = root / ".front-office-server.json"
            instance = {"serving_pid": 4242, "process_create_time": 1.0}
            with mock.patch.object(run_recipe, "FRONT_OFFICE_SERVER_SESSION_FILE", sidecar), mock.patch.object(
                run_recipe, "ACTIVE_FRONT_OFFICE_CONTEXT", first
            ):
                sidecar.write_bytes(run_recipe.canonical_json_bytes(
                    run_recipe._front_office_server_session_payload(instance)
                ))
            with mock.patch.object(run_recipe, "FRONT_OFFICE_SERVER_SESSION_FILE", sidecar), mock.patch.object(
                run_recipe, "ACTIVE_FRONT_OFFICE_CONTEXT", second
            ):
                self.assertFalse(run_recipe._front_office_server_session_matches(instance))
                self.assertFalse(run_recipe._remove_front_office_server_session_after_shutdown())
                with mock.patch.object(run_recipe, "cleanup_stale_pid_receipt", return_value=False), mock.patch.object(
                    run_recipe, "query_server_stats", return_value={"alive": True}
                ), mock.patch.object(run_recipe, "get_recorded_pid", return_value=4242), mock.patch.object(
                    run_recipe, "listener_pid", return_value=4242
                ), mock.patch.object(run_recipe, "is_expected_lab_server_pid", return_value=True), mock.patch.object(
                    run_recipe, "ensure_queue_idle"
                ), mock.patch.object(run_recipe, "verified_server_instance", return_value=instance):
                    with self.assertRaisesRegex(run_recipe.PreflightError, "does not match the active Front Office"):
                        run_recipe.check_server_up_and_ownership()
            self.assertTrue(sidecar.exists())

    def test_shutdown_refuses_mismatched_front_office_session_without_termination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.make_context(root, profile_id="profile-a")
            second = self.make_context(root, profile_id="profile-b")
            self.claim_context(first)
            server_pid = root / ".server.pid"
            server_pid.write_text("4242\n", encoding="utf-8")
            sidecar = root / ".front-office-server.json"
            instance = {"serving_pid": 4242, "process_create_time": 1.0}
            with mock.patch.object(run_recipe, "FRONT_OFFICE_SERVER_SESSION_FILE", sidecar), mock.patch.object(
                run_recipe, "ACTIVE_FRONT_OFFICE_CONTEXT", first
            ):
                sidecar.write_bytes(
                    run_recipe.canonical_json_bytes(
                        run_recipe._front_office_server_session_payload(instance)
                    )
                )
            with mock.patch.object(run_recipe, "SERVER_PID_FILE", server_pid), mock.patch.object(
                run_recipe, "FRONT_OFFICE_SERVER_SESSION_FILE", sidecar
            ), mock.patch.object(run_recipe, "ACTIVE_FRONT_OFFICE_CONTEXT", second), mock.patch.object(
                run_recipe, "_snapshot_server_pid_receipt", return_value={"pid": 4242}
            ), mock.patch.object(run_recipe.psutil, "pid_exists", return_value=True), mock.patch.object(
                run_recipe, "verified_server_instance", return_value=instance
            ), mock.patch.object(run_recipe, "terminate_owned_process_tree") as terminate:
                result = run_recipe.shutdown_lab_server()

            self.assertFalse(result["success"])
            self.assertFalse(result["termination_attempted"])
            self.assertIn("does not match", result["reason"])
            terminate.assert_not_called()
            self.assertTrue(server_pid.exists())
            self.assertTrue(sidecar.exists())

    def test_receipt_binding_excludes_one_shot_nonce_from_warm_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            context = self.make_context(Path(directory))
            self.claim_context(context)
            receipt_binding = run_recipe.front_office_receipt_binding(context)
            identity_binding = run_recipe.front_office_identity_binding(context)
            self.assertEqual(receipt_binding["profile_id"], context.profile_id)
            self.assertEqual(receipt_binding["launch_spec_sha256"], context.launch_spec_sha256)
            self.assertEqual(receipt_binding["lease_nonce"], context.lease_nonce)
            self.assertEqual(
                receipt_binding["execution_spec_instance_sha256"], context.execution_spec_sha256
            )
            self.assertEqual(
                receipt_binding["execution_claim"]["path"],
                str(run_recipe._front_office_execution_claim_path(context)),
            )
            self.assertNotIn("lease_nonce", identity_binding)
            self.assertNotIn("execution_spec_instance_sha256", identity_binding)
            self.assertNotIn("execution_claim", identity_binding)
            self.assertEqual(identity_binding["profile_id"], context.profile_id)

    def test_one_shot_front_office_run_never_inherits_warmth_from_prior_history(self):
        with tempfile.TemporaryDirectory() as directory:
            context = self.make_context(Path(directory))
            prior_same_identity = {
                "run_count": 7,
                "config_run_count": 7,
                "previous_gate_pass": True,
            }
            with mock.patch.object(run_recipe, "ACTIVE_FRONT_OFFICE_CONTEXT", context):
                run_count, config_run_count, is_warm = run_recipe.effective_run_cache_state(
                    prior_same_identity
                )
            self.assertEqual(run_count, 7)
            self.assertEqual(config_run_count, 1)
            self.assertFalse(is_warm)
            self.assertFalse(
                run_recipe.promotion_ready_for_run(
                    is_warm, False, requires_human_eyeball=False
                )
            )
