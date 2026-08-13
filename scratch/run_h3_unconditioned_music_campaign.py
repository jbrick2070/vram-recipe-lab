#!/usr/bin/env python3
"""Fail-closed H3 unconditioned-music study campaign.

Default invocation only prints the immutable 11-cell runbook. ``--run`` is the
sole execution switch. Fresh cells are rendered cold then immediately warm on
one owned lab server through ``run_recipe.py``; the warm child performs the
verified shutdown. Attempt-004 carries the fully reverified pairs 1 and 2 from
attempts 002/003 and executes only pairs 3-11. Attempt-005 carries verified
pairs 1-9 from the corrected, sealed attempt-004 timeout recovery and executes
only pairs 10-11. The logical A control is reused four times by exact
recipe/receipt/artifact identity, so the study has 11 pairs rather than 14.

This is the one test-only H3 lane that loads ComfyUI-Manager. Its attempt-unique
server log must authoritatively announce exactly one ``network_mode: offline``
before any prompt. The ordinary lab boot remains Manager-disabled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time
from typing import Any, Callable, Mapping, Sequence

import psutil

import run_h3_canonical_campaign as canon
import h3_manager_offline_guard as manager_guard


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUTPUTS = ROOT / "outputs"
CAMPAIGN_RESULTS = RESULTS / "h3_unconditioned_music_campaign"
LIFECYCLE = CAMPAIGN_RESULTS / "lifecycle.jsonl"
LOG_ROOT = CAMPAIGN_RESULTS / "server_logs"
RUNNER = ROOT / "run_recipe.py"
LAB_LOCKS = ROOT / "lab_locks.py"
BOOT_CMD = ROOT / "boot_lab_server.cmd"
TEST_BOOT_CMD = ROOT / "boot_h3_manager_offline_test.cmd"
BUILDER = ROOT / "scratch" / "build_h3_unconditioned_music_study.py"
GUARD = ROOT / "scratch" / "h3_manager_offline_guard.py"
CAMPAIGN_SOURCE = Path(__file__).resolve()
CANONICAL_CAMPAIGN = ROOT / "scratch" / "run_h3_canonical_campaign.py"
RECOVERY_RECORDER = ROOT / "scratch" / "record_h3_music_recovery.py"
ATTEMPT2_RECOVERY_RECORDER = (
    ROOT / "scratch" / "record_h3_music_attempt2_recovery.py"
)
ATTEMPT3_RECOVERY_RECORDER = (
    ROOT / "scratch" / "record_h3_music_attempt3_recovery.py"
)
OPERATOR_LAUNCHER = ROOT / "scratch" / "start_h3_music_attempt3.ps1"
OPERATOR_RECORDER = (
    ROOT / "scratch" / "record_h3_music_operator_launch.py"
)
ATTEMPT4_OPERATOR_LAUNCHER = (
    ROOT / "scratch" / "start_h3_music_attempt4.ps1"
)
ATTEMPT4_OPERATOR_RECORDER = (
    ROOT / "scratch" / "record_h3_music_attempt4_operator_launch.py"
)
ATTEMPT4_RECOVERY_RECORDER = (
    ROOT / "scratch" / "record_h3_music_attempt4_recovery.py"
)
ATTEMPT5_OPERATOR_LAUNCHER = ROOT / "scratch" / "start_h3_music_attempt5.ps1"
ATTEMPT5_OPERATOR_RECORDER = (
    ROOT / "scratch" / "record_h3_music_attempt5_operator_launch.py"
)
PYTHON = Path(r"C:\Users\jeffr\Documents\ComfyUI\.venv\Scripts\python.exe")
EXPECTED_BOOT_LANE = (
    "lab-8199, sage-free, manager-offline-test, no-pinned, "
    "cache-classic, reserve-12gb"
)
PROVEN_RESERVE_VRAM_GIB = 12.0
EXPECTED_WHITELIST = ["ComfyUI-GGUF", "ComfyUI-KJNodes", "ComfyUI-Manager"]
PORTRAIT_SHA256 = "3ce7b7245abb9129510567f7ed24c08ff68619ef649fee6d6ae79b8a1d770bad"
CAMPAIGN_ID_RE = re.compile(r"[A-Za-z0-9_.-]{1,80}")
FAILED_CAMPAIGN_ID = "h3music-20260810T023023Z-97ca44b2"
RECOVERY_ID = f"{FAILED_CAMPAIGN_ID}-recovery-001"
RESUME_CAMPAIGN_ID = f"{FAILED_CAMPAIGN_ID}-attempt-002"
RESUME_ATTEMPT2_CAMPAIGN_ID = f"{FAILED_CAMPAIGN_ID}-attempt-003"
RESUME_ATTEMPT3_CAMPAIGN_ID = f"{FAILED_CAMPAIGN_ID}-attempt-004"
RESUME_ATTEMPT4_CAMPAIGN_ID = f"{FAILED_CAMPAIGN_ID}-attempt-005"
FAILED_LIFECYCLE_PREFIX_BYTES = 28_706
FAILED_LIFECYCLE_PREFIX_SHA256 = (
    "fed5a70a832ad4bc9a985e5c136d583ad7338146164eef89bf3bbe3fd917c2cf"
)
FAILED_LIFECYCLE_LAST_EVENT_SHA256 = (
    "20ec57fc403d782ee292c3bfbd75b70c3d5466fca620f255e8aefaeb5c0bea1b"
)
FAILED_RUN1_SHA256 = (
    "c1295c435e25419ed771aae044d33806b55e9237e594dcdd6716be519a602b8f"
)
FAILED_LOG_SHA256 = (
    "b1a99a7b496b5125897d41c44a5278c5b848f9afd6afc8c2e65271b57e6a443d"
)
FAILED_ARTIFACT_SHA256 = (
    "b58461545dc0b7ceee6bfa0eaac080446cc3148bc00783f04eaef48ee96617ed"
)
FAILED_LOG_NAME = (
    f"{FAILED_CAMPAIGN_ID}-p01-h3_unconditioned_music_scene_seed42_f124.log"
)
RECOVERY_RECEIPT = (
    CAMPAIGN_RESULTS
    / "recoveries"
    / f"{FAILED_CAMPAIGN_ID}-manual-cleanup.json"
)
ATTEMPT4_SUPERSEDED_RECOVERY_RECEIPT = (
    CAMPAIGN_RESULTS
    / "recoveries"
    / f"{RESUME_ATTEMPT3_CAMPAIGN_ID}-timeout-recovery.json"
)
ATTEMPT4_CORRECTED_RECOVERY_RECEIPT = (
    CAMPAIGN_RESULTS
    / "recoveries"
    / f"{RESUME_ATTEMPT3_CAMPAIGN_ID}-timeout-recovery-correction-001.json"
)
# Filled only after the O_EXCL recovery recorder publishes the final bytes.
# Keeping the main campaign out of the recovery receipt's source set avoids a
# self-referential hash; this literal is the external resume-authority pin.
RECOVERY_RECEIPT_SHA256: str | None = (
    "e153ba610110e1fb5a637d1ddfa4f0144f60982e88be018d08534f7ddf4371df"
)
ATTEMPT2_LIFECYCLE_PREFIX_BYTES = 110_592
ATTEMPT2_LIFECYCLE_PREFIX_SHA256 = (
    "f95b952e97507761d474f6f3701bdd46f69a569c612a864c1a53d5d1b71686f4"
)
ATTEMPT2_LIFECYCLE_LAST_EVENT_SHA256 = (
    "9ce05976ffa45551bb3bc1dbb34d1bdc1f50c81ace67d51fcea46126279ec857"
)
ATTEMPT2_RECOVERY_ID = f"{RESUME_CAMPAIGN_ID}-recovery-001"
ATTEMPT2_RECOVERY_RECEIPT_SHA256 = (
    "32a9e9403388d76e190082a04937fb83446b4b3617c0a2178cd4eb673de4911d"
)
ATTEMPT2_RECOVERY_RECEIPT_BYTES = 31_555
ATTEMPT2_RECOVERY_RECORDER_SHA256 = (
    "c873053051b9a7e295da89601c0ed92ba6a5d03aeaf1f2672b9b9d4d83ca7011"
)
ATTEMPT2_RECOVERY_RECORDER_BYTES = 48_060
ATTEMPT2_CAMPAIGN_SOURCE_SHA256 = (
    "8aec4108559618963b1210ad4a58cdb9d28b55853137746577c4db7da3703e97"
)
ATTEMPT2_CAMPAIGN_SOURCE_BYTES = 74_609
ATTEMPT2_RUN2_SHA256 = (
    "30d6dbc37b906a25909826e8ef68862af4952c7597b793a76982db1a9ebe25cd"
)
ATTEMPT2_RUN3_SHA256 = (
    "e12a76ebc4e14bb42d2d6f44466364894a6ce65a70b4cbda1057d55cb976829a"
)
ATTEMPT2_LOG_SHA256 = (
    "1ab05e73202b2e77a5dfb4f4cf350491e1e9a0d0d6c4083204d855be88122b7d"
)
ATTEMPT2_PAIR_RESULT_SHA256 = (
    "b47abc5895f9e0a6bbeb3d4da4a2490213dba168fa1aa4505257bfd5f4103f22"
)
ATTEMPT2_SERVER_IDENTITY = {
    "serving_pid": 6_824,
    "process_create_time": 1_786_332_252.100749,
}
ATTEMPT2_RUN_IDENTITY_SHA256 = (
    "aaeb2daca2cb317a03ac6437813f9cf958819c44f479927bd0d91934c13d7f01"
)
ATTEMPT2_COLD_QUEUED_SHA256 = (
    "7d49d4ebe51a3cf038e63b19801b3e2f80ec8f536bc955b9c99ddabf97fbb828"
)
ATTEMPT2_WARM_QUEUED_SHA256 = (
    "3f584a9ea76ad1d5b0b5c397ae335ed748c7e65a38d8fdc43124d0b9beb0cf4a"
)
ATTEMPT3_LIFECYCLE_PREFIX_BYTES = 297_646
ATTEMPT3_LIFECYCLE_PREFIX_SHA256 = (
    "8104b063130b8f6ddb907eaa972ff3a52f8879f970e60663d9df0ee607a83907"
)
ATTEMPT3_LIFECYCLE_LAST_EVENT_SHA256 = (
    "ad6ad066c8d64b7066c838541f583d4a10b8bc6f5ed30a77eff9ef632b3927ba"
)
ATTEMPT3_RECOVERY_RECEIPT_BYTES = 16_216
ATTEMPT3_RECOVERY_RECEIPT_SHA256 = (
    "306d44d4778b7a20921bc40df2594b6a11c0b11030e20e1629cd06f2dcd7442d"
)
ATTEMPT3_RECOVERY_RECORDER_BYTES = 39_301
ATTEMPT3_RECOVERY_RECORDER_SHA256 = (
    "6e22075eeb39e1cffdf2d311fc3950bafe2a227849bec376fb6c83e5eeb0ff0b"
)
ATTEMPT3_PAIR2_COLD_SHA256 = (
    "a3bd3aaf1cf60f578d6e472d7894c12041dd32bd14ccce475f5dd966b4f4cff0"
)
ATTEMPT3_PAIR2_WARM_SHA256 = (
    "737b3d4a4473569cbfa6615b01eb3a4143450d2a133cbf99b3990ea71e1c7aa8"
)
ATTEMPT3_PAIR2_LOG_SHA256 = (
    "68b53407712bc42a59167bf5e4fb55aa6fbc8008704a3c695c64e05c56f5f24c"
)
ATTEMPT3_PAIR2_RESULT_SHA256 = (
    "a3dd0a5966f6f738b56fbadfd53c95a54789e9481e5b0202bd60d650e8aa3be1"
)
ATTEMPT3_PAIR2_ARTIFACT_SHA256 = (
    "92d044cd5d6f2bffb9e53b5ff5b6917670ff52bbb363309ba0473123ac398541"
)
ATTEMPT3_PAIR2_SERVER_IDENTITY = {
    "serving_pid": 19_256,
    "process_create_time": 1_786_336_988.58777,
}
ATTEMPT3_PAIR2_RUN_IDENTITY_SHA256 = (
    "cb168f4c65fb0e90099200ab34bd09c7479f6b6ff3edf433074ba0d78bd02672"
)
ATTEMPT3_PAIR2_COLD_QUEUED_SHA256 = (
    "c2b680a4d03a96a2a2ff398ecdfb58d5d0ed2e3517a17f880a1dfc599d01dfd1"
)
ATTEMPT3_PAIR2_WARM_QUEUED_SHA256 = (
    "42592f5b73e3d2806a140a1bc85248045f85d494602625c71ab30ba78d9355b7"
)
OPERATOR_LAUNCHER_SHA256 = (
    "1a4dac75f14580d407cafc44c6b7503c6db3d7539432b28f4d79d9239fcb6601"
)
OPERATOR_LAUNCHER_BYTES = 5_788
OPERATOR_RECORDER_SHA256 = (
    "0057321608c679c4d0924421dfc8174c7a7e61227cfc257a31cf1cacdb9fd849"
)
OPERATOR_RECORDER_BYTES = 32_374
ATTEMPT4_OPERATOR_LAUNCHER_SHA256 = (
    "163650d79321cbda6ca8287fdf7551acca4ee54fbcee17b75e14bfb0cac6ae69"
)
ATTEMPT4_OPERATOR_LAUNCHER_BYTES = 5_708
ATTEMPT4_OPERATOR_RECORDER_SHA256 = (
    "053fd5fd22ba6c6132636a6946d2b4da6184d8f631a88970120afad77906059e"
)
ATTEMPT4_OPERATOR_RECORDER_BYTES = 24_435
ATTEMPT4_FROZEN_RUNNER_BYTES = 180_403
ATTEMPT4_FROZEN_RUNNER_SHA256 = (
    "0224d6ec6db4962f0332bf53e031cd71e2818ccca4a919479c829e64cbfc4bf8"
)
ATTEMPT5_RUNNER_BYTES = 182_105
ATTEMPT5_RUNNER_SHA256 = (
    "0c7c636e36d1573852a5ad2c71cb06a826dea97eb34b16ab605ecafb530b83c9"
)
# Backward-compatible names denote the current runner source used by campaign
# invocations; the frozen attempt-004 bytes remain separately pinned above.
ATTEMPT4_RUNNER_BYTES = ATTEMPT5_RUNNER_BYTES
ATTEMPT4_RUNNER_SHA256 = ATTEMPT5_RUNNER_SHA256
ATTEMPT4_LIFECYCLE_PREFIX_BYTES = 1_513_119
ATTEMPT4_LIFECYCLE_PREFIX_SHA256 = (
    "1fb0ea686f0acd30e83e2f294d717afebf471381b3eb9d2138a12f6a10734c69"
)
ATTEMPT4_LIFECYCLE_LAST_EVENT_SHA256 = (
    "b66526982583393059c25d6c67cad3b8fdae4a51239111dc19d15681c14df80f"
)
ATTEMPT4_LIFECYCLE_ROW_COUNT = 65
ATTEMPT4_RECOVERY_RECEIPT_BYTES = 60_939
ATTEMPT4_RECOVERY_RECEIPT_SHA256 = (
    "fef1ef0401b5e4f13dc11b7405224e6b792a1a18c3b607fce806468f598f7dcd"
)
ATTEMPT4_SUPERSEDED_RECOVERY_RECEIPT_BYTES = 59_642
ATTEMPT4_SUPERSEDED_RECOVERY_RECEIPT_SHA256 = (
    "a76d05fb4d0d01afa90b705ba654af6c8b56344bd93478e653fa9a3146e1f88f"
)
ATTEMPT4_RECOVERY_RECORDER_BYTES = 38_580
ATTEMPT4_RECOVERY_RECORDER_SHA256 = (
    "d35ec3c0ddc3ae495c4bc56d5166a716f0da57cfbcb32ac6876373ab61528335"
)
ATTEMPT4_PAIR10_RUN1_BYTES = 37_593
ATTEMPT4_PAIR10_RUN1_SHA256 = (
    "4ab72334bc80d8155d1b1d1466258922a7a9e1ad2e289f37b07a510115d164bf"
)
ATTEMPT4_PAIR10_LOG_BYTES = 22_893
ATTEMPT4_PAIR10_LOG_SHA256 = (
    "22d1e7264febfe962cbda12f9365fc633f28af2cb9c079fc253138f5698edfb1"
)
ATTEMPT4_OPERATOR_STDOUT_BYTES = 27_710
ATTEMPT4_OPERATOR_STDOUT_SHA256 = (
    "f5725b2bc6bbce93dcc682ae5716b8e8b056ca7f2cb8099f364c795acfed890e"
)
ATTEMPT4_OPERATOR_STDERR_BYTES = 127
ATTEMPT4_OPERATOR_STDERR_SHA256 = (
    "b06421405eaea1da951fc837038d4b255bfa8652571adcfbf4c92120aca0a130"
)
ATTEMPT5_OPERATOR_LAUNCHER_BYTES: int | None = 5_381
ATTEMPT5_OPERATOR_LAUNCHER_SHA256: str | None = (
    "909c609677601467b43ac4a275ae7fe118be49b478c55a42658f82274c4c31f2"
)
ATTEMPT5_OPERATOR_RECORDER_BYTES: int | None = 31_649
ATTEMPT5_OPERATOR_RECORDER_SHA256: str | None = (
    "5250cdb89f6834305179897a24063ebe8e377681199830e1a32e8fb482709aa5"
)
ATTEMPT2_EXPECTED_LIFECYCLE_ROWS: tuple[tuple[str, str, int, str], ...] = (
    (FAILED_CAMPAIGN_ID, "campaign_started", 1, "f01b06798f7529cf9e38f734a1481438bbada3d57faa3774c0cf14d6cdca9ef0"),
    (FAILED_CAMPAIGN_ID, "campaign_preflight_passed", 2, "006da69b6ad926742a2cd2d0a0c7abddb63a04d0bccb581dcc32a0db9efa717c"),
    (FAILED_CAMPAIGN_ID, "pair_started", 3, "63ee32714a4228ccde67ae66da6c8ebe997442bc9fbb26948bf918786965d715"),
    (FAILED_CAMPAIGN_ID, "cold_child_returned", 4, "32a61263ef36a5549512c4c020d696e520ac84d1c9760bb305b55d55e5ca4d4a"),
    (FAILED_CAMPAIGN_ID, "campaign_failed", 5, FAILED_LIFECYCLE_LAST_EVENT_SHA256),
    (RESUME_CAMPAIGN_ID, "recovery_started", 1, "478037f4dc52adff8b4814a1e424a2c64a04284f33867435f176d1a1244c0053"),
    (RESUME_CAMPAIGN_ID, "campaign_started", 2, "6e8e66fcf897d50a82232647870539d02b1bb847aa9d0de9b83da2d8f7d1683e"),
    (RESUME_CAMPAIGN_ID, "campaign_preflight_passed", 3, "f94cf3db25fb9c4fb0cf2439d966fcb1b588365171ec28fba7c8df5db1eb2fca"),
    (RESUME_CAMPAIGN_ID, "pair_started", 4, "4d25afdb53d1142775b6254ff55ed1b3e0a45cc741b9cd5878bbb65f3349f6a7"),
    (RESUME_CAMPAIGN_ID, "cold_child_returned", 5, "4f52b4f8665729ddce320d506911811327be07a0c06dc55ff82abfd585a643df"),
    (RESUME_CAMPAIGN_ID, "cold_verified", 6, "9b07cdf20a1022eeb0b807027713ff97bcd01f2b878ab441be4fddb9e86ba094"),
    (RESUME_CAMPAIGN_ID, "warm_shutdown_child_returned", 7, "8ad4116ad15e1faeb8fa1296a651fe601e14e99eb23e0ceaa06977e91cddd9cc"),
    (RESUME_CAMPAIGN_ID, "campaign_failed", 8, ATTEMPT2_LIFECYCLE_LAST_EVENT_SHA256),
)

# name, immutable recipe SHA, seed, frames, logical roles
CELL_PINS: tuple[tuple[str, str, int, int, tuple[str, ...]], ...] = (
    (
        "h3_unconditioned_music_scene_seed42_f124",
        "91efb98e40eab183b31b718c1d044f674c9db31a5e0c3336cc41605ea616d9cf",
        42,
        124,
        ("job0_A", "job1_seed42", "job2_A", "job3_f124"),
    ),
    (
        "h3_unconditioned_music_motion_small_seed42_f124",
        "60cc81156db12e1c677cee11e49c26959237c321e298658d47c78b6542f0238a",
        42,
        124,
        ("job0_B",),
    ),
    (
        "h3_unconditioned_music_motion_large_seed42_f124",
        "49045a2c2f11441b0ab74c9ce5c6fa97bbc768a55827a735acad8aa6872cc792",
        42,
        124,
        ("job0_C",),
    ),
    (
        "h3_unconditioned_music_scene_seed43_f124",
        "787c20179624211197d46a698a24d607a377b448ac44d12edf29d3980aa01244",
        43,
        124,
        ("job1_seed43",),
    ),
    (
        "h3_unconditioned_music_scene_seed44_f124",
        "14ed2a59fd570087597e1f9745133b72363c8ca78fa12c1a358ab229cdcf0f5f",
        44,
        124,
        ("job1_seed44",),
    ),
    (
        "h3_unconditioned_music_scene_seed45_f124",
        "1de25882ebdf07f7ac9261467c01ea8144cbfff5da8c12cb49c44ca50019df48",
        45,
        124,
        ("job1_seed45",),
    ),
    (
        "h3_unconditioned_music_scene_seed46_f124",
        "5aab5ddf286cb80d8a0cea201b69fd2de6169174783b1ec568f734262a276326",
        46,
        124,
        ("job1_seed46",),
    ),
    (
        "h3_unconditioned_music_score_seed42_f124",
        "52a4e231b3314d619bcf87b5d62a6bfedfd28e37a4c038638fc1bc896db199f8",
        42,
        124,
        ("job2_B",),
    ),
    (
        "h3_unconditioned_music_sfx_seed42_f124",
        "21cfe54f2b5acff5c3a7b3ad12014ceb007952ff39876fd0aa2ce0a23f899aae",
        42,
        124,
        ("job2_C",),
    ),
    (
        "h3_unconditioned_music_scene_seed42_f192",
        "5249ffd3e89c10c4a3bae8ba939da9ee2f26e9da2dcbc58e08448f2a393c04a3",
        42,
        192,
        ("job3_f192",),
    ),
    (
        "h3_unconditioned_music_scene_seed42_f277",
        "96621cd7c7ae5ae086c03fd43133f9d6eeecb177e06c05eff9ecbc791d561288",
        42,
        277,
        ("job3_f277",),
    ),
)


CampaignError = canon.CampaignError


def layout() -> canon.Layout:
    base = canon.DEFAULT_LAYOUT
    return canon.Layout(
        root=ROOT,
        results=RESULTS,
        outputs=OUTPUTS,
        lifecycle=LIFECYCLE,
        runner=RUNNER,
        lab_locks=LAB_LOCKS,
        boot_cmd=BOOT_CMD,
        actual_manager_config=base.actual_manager_config,
        lab_manager_config=base.lab_manager_config,
        actual_user_directory=base.actual_user_directory,
        comfyui_main=base.comfyui_main,
        python=PYTHON,
        gpu_lock=ROOT / ".gpu.lock",
        suite_lock=ROOT / ".suite.lock",
        server_pid=ROOT / ".server.pid",
        queue_quarantine=ROOT / ".queue.quarantine.json",
    )


DEFAULT_LAYOUT = layout()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_campaign_id(value: str) -> str:
    if CAMPAIGN_ID_RE.fullmatch(value) is None:
        raise CampaignError(
            "campaign id must be 1-80 characters from A-Z, a-z, 0-9, _, ., -"
        )
    return value


def campaign_id_now() -> str:
    return (
        time.strftime("h3music-%Y%m%dT%H%M%SZ-", time.gmtime())
        + secrets.token_hex(4)
    )


def load_specs(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> list[canon.RecipeSpec]:
    specs = []
    for name, digest, seed, frames, roles in CELL_PINS:
        path = campaign_layout.root / "recipes" / f"{name}.json"
        recipe, raw = canon.strict_json(path, f"immutable recipe {name}")
        if sha256_bytes(raw) != digest:
            raise CampaignError(f"immutable recipe hash drift: {name}")
        prompt = recipe.get("prompt") or {}
        contract = recipe.get("contract") or {}
        study = recipe.get("study") or {}
        expected = (
            name,
            False,
            "minimax_h3",
            "r2v_unconditioned_music_study",
            1344,
            768,
            frames,
            24.0,
            True,
            True,
            seed,
            frames,
            "portrait.png",
            list(roles),
        )
        actual = (
            recipe.get("name"),
            recipe.get("blocked"),
            contract.get("engine"),
            contract.get("mode"),
            contract.get("width"),
            contract.get("height"),
            contract.get("frames"),
            contract.get("fps"),
            contract.get("requires_audio"),
            contract.get("requires_manager_offline_probe"),
            (prompt.get("5") or {}).get("inputs", {}).get("noise_seed"),
            (prompt.get("7") or {}).get("inputs", {}).get("length"),
            (prompt.get("11") or {}).get("inputs", {}).get("image"),
            study.get("logical_roles"),
        )
        if actual != expected:
            raise CampaignError(f"recipe contract drift: {name}: {actual!r}")
        ref_inputs = (prompt.get("7") or {}).get("inputs", {})
        classes = [
            node.get("class_type") for node in prompt.values() if isinstance(node, dict)
        ]
        if (
            frames < 5
            or (frames - 5) % 17 != 0
            or ref_inputs.get("ref_images.ref_image_0") != ["11", 0]
            or "ref_images" in ref_inputs
            or any(key.startswith("ref_audio") for key in ref_inputs)
            or "LoadAudio" in classes
            or (prompt.get("15") or {}).get("inputs")
            != {"samples": ["8", 0], "vae": ["4", 0]}
            or (prompt.get("10") or {}).get("inputs", {}).get("audio") != ["15", 0]
        ):
            raise CampaignError(f"native-audio/flat-V3 topology drift: {name}")
        specs.append(
            canon.RecipeSpec(
                name=name,
                sha256=digest,
                mode="r2v_unconditioned_music_study",
                frames=frames,
                path=path,
                prefix=f"{name}_out",
                fixture_hashes={"portrait.png": PORTRAIT_SHA256},
            )
        )
    if len(specs) != 11 or len({spec.name for spec in specs}) != 11:
        raise CampaignError("study must contain exactly eleven unique physical cells")
    return specs


def source_evidence(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> dict[str, Any]:
    evidence = {}
    source_paths: list[tuple[str, Path]] = [
        ("runner", campaign_layout.runner),
        ("lab_locks", campaign_layout.lab_locks),
        ("boot_cmd", campaign_layout.boot_cmd),
        ("manager_test_boot_cmd", TEST_BOOT_CMD),
        ("builder", BUILDER),
        ("manager_guard", GUARD),
        ("campaign", CAMPAIGN_SOURCE),
        ("campaign_canonical", CANONICAL_CAMPAIGN),
        ("recovery_recorder", RECOVERY_RECORDER),
        ("attempt2_recovery_recorder", ATTEMPT2_RECOVERY_RECORDER),
        ("attempt3_recovery_recorder", ATTEMPT3_RECOVERY_RECORDER),
        ("operator_launcher", OPERATOR_LAUNCHER),
        ("operator_recorder", OPERATOR_RECORDER),
        ("attempt4_operator_launcher", ATTEMPT4_OPERATOR_LAUNCHER),
        ("attempt4_operator_recorder", ATTEMPT4_OPERATOR_RECORDER),
        ("attempt4_recovery_recorder", ATTEMPT4_RECOVERY_RECORDER),
        ("attempt4_recovery_receipt", ATTEMPT4_CORRECTED_RECOVERY_RECEIPT),
    ]
    attempt5_sources = (
        ("attempt5_operator_launcher", ATTEMPT5_OPERATOR_LAUNCHER),
        ("attempt5_operator_recorder", ATTEMPT5_OPERATOR_RECORDER),
    )
    if all(os.path.lexists(path) for _, path in attempt5_sources):
        source_paths.extend(attempt5_sources)
    elif any(os.path.lexists(path) for _, path in attempt5_sources):
        raise CampaignError("attempt-005 operator source set is only partially present")
    for label, path in source_paths:
        raw, snapshot = canon.stable_file(path, label)
        if raw.startswith(b"\xef\xbb\xbf"):
            raise CampaignError(f"{label} has a UTF-8 BOM")
        evidence[label] = snapshot
    exact_source_pins = {
        "runner": (ATTEMPT4_RUNNER_BYTES, ATTEMPT4_RUNNER_SHA256),
        "attempt2_recovery_recorder": (
            ATTEMPT2_RECOVERY_RECORDER_BYTES,
            ATTEMPT2_RECOVERY_RECORDER_SHA256,
        ),
        "attempt3_recovery_recorder": (
            ATTEMPT3_RECOVERY_RECORDER_BYTES,
            ATTEMPT3_RECOVERY_RECORDER_SHA256,
        ),
        "operator_launcher": (OPERATOR_LAUNCHER_BYTES, OPERATOR_LAUNCHER_SHA256),
        "operator_recorder": (OPERATOR_RECORDER_BYTES, OPERATOR_RECORDER_SHA256),
        "attempt4_operator_launcher": (
            ATTEMPT4_OPERATOR_LAUNCHER_BYTES,
            ATTEMPT4_OPERATOR_LAUNCHER_SHA256,
        ),
        "attempt4_operator_recorder": (
            ATTEMPT4_OPERATOR_RECORDER_BYTES,
            ATTEMPT4_OPERATOR_RECORDER_SHA256,
        ),
        "attempt4_recovery_recorder": (
            ATTEMPT4_RECOVERY_RECORDER_BYTES,
            ATTEMPT4_RECOVERY_RECORDER_SHA256,
        ),
        "attempt4_recovery_receipt": (
            ATTEMPT4_RECOVERY_RECEIPT_BYTES,
            ATTEMPT4_RECOVERY_RECEIPT_SHA256,
        ),
    }
    if "attempt5_operator_launcher" in evidence:
        if None in {
            ATTEMPT5_OPERATOR_LAUNCHER_BYTES,
            ATTEMPT5_OPERATOR_LAUNCHER_SHA256,
            ATTEMPT5_OPERATOR_RECORDER_BYTES,
            ATTEMPT5_OPERATOR_RECORDER_SHA256,
        }:
            raise CampaignError("attempt-005 operator source pins are not finalized")
        exact_source_pins.update(
            {
                "attempt5_operator_launcher": (
                    int(ATTEMPT5_OPERATOR_LAUNCHER_BYTES),
                    str(ATTEMPT5_OPERATOR_LAUNCHER_SHA256),
                ),
                "attempt5_operator_recorder": (
                    int(ATTEMPT5_OPERATOR_RECORDER_BYTES),
                    str(ATTEMPT5_OPERATOR_RECORDER_SHA256),
                ),
            }
        )
    for label, (expected_bytes, expected_sha256) in exact_source_pins.items():
        snapshot = evidence[label]
        if (
            snapshot.get("bytes") != expected_bytes
            or snapshot.get("sha256") != expected_sha256
        ):
            raise CampaignError(f"literal source pin drifted: {label}")
    # This immutable authority is repository-global source evidence, not a
    # per-test/per-campaign output location.
    recovery2_path = CAMPAIGN_RESULTS / "recoveries" / (
        f"{RESUME_CAMPAIGN_ID}-return120-recovery.json"
    )
    recovery2_raw, recovery2_snapshot = canon.stable_file(
        recovery2_path, "attempt-002 recovery receipt"
    )
    if (
        len(recovery2_raw) != ATTEMPT2_RECOVERY_RECEIPT_BYTES
        or sha256_bytes(recovery2_raw) != ATTEMPT2_RECOVERY_RECEIPT_SHA256
    ):
        raise CampaignError("literal attempt-002 recovery receipt pin drifted")
    evidence["attempt2_recovery_receipt"] = recovery2_snapshot
    recovery3_path = CAMPAIGN_RESULTS / "recoveries" / (
        f"{RESUME_ATTEMPT2_CAMPAIGN_ID}-stale-pid-recovery.json"
    )
    recovery3_raw, recovery3_snapshot = canon.stable_file(
        recovery3_path, "attempt-003 recovery receipt"
    )
    if (
        len(recovery3_raw) != ATTEMPT3_RECOVERY_RECEIPT_BYTES
        or sha256_bytes(recovery3_raw) != ATTEMPT3_RECOVERY_RECEIPT_SHA256
    ):
        raise CampaignError("literal attempt-003 recovery receipt pin drifted")
    evidence["attempt3_recovery_receipt"] = recovery3_snapshot
    default_boot = BOOT_CMD.read_text(encoding="utf-8")
    default_executable = "\n".join(
        line
        for line in default_boot.splitlines()
        if not line.lstrip().lower().startswith(("rem ", "::"))
    )
    if (
        "ComfyUI-Manager" in default_executable
        or "--whitelist-custom-nodes ComfyUI-GGUF ComfyUI-KJNodes %EXTRA_ARGS%"
        not in default_executable
    ):
        raise CampaignError("default Manager-disabled boot contract drifted")
    boot = TEST_BOOT_CMD.read_text(encoding="utf-8")
    required = (
        'if not "%LAB_MANAGER_OFFLINE_PROBE%"=="1"',
        "rem remains byte-for-byte unchanged",
        'if not "%HF_TOKEN%"=="offline-disabled"',
        'if not "%HUGGING_FACE_HUB_TOKEN%"=="offline-disabled"',
        'if not "%HF_HUB_OFFLINE%"=="1"',
        'if not "%TRANSFORMERS_OFFLINE%"=="1"',
        'if not "%PIP_NO_INDEX%"=="1"',
        'if not "%PIP_DISABLE_PIP_VERSION_CHECK%"=="1"',
        'if not "%UV_OFFLINE%"=="1"',
        'if not "%GIT_TERMINAL_PROMPT%"=="0"',
        "if defined HUGGINGFACE_HUB_TOKEN",
        "if defined HF_API_TOKEN",
        "--disable-all-custom-nodes",
        "--whitelist-custom-nodes ComfyUI-GGUF ComfyUI-KJNodes ComfyUI-Manager",
        '>> "%LAB_MANAGER_PROBE_LOG%" 2>&1',
    )
    if any(token not in boot for token in required):
        raise CampaignError("test-only Manager boot contract drifted")
    if "--use-sage-attention" in "\n".join(
        line for line in boot.splitlines() if not line.lstrip().lower().startswith("rem ")
    ).lower():
        raise CampaignError("boot execution path enables global SageAttention")
    expected_argv = expected_server_argv(campaign_layout)
    evidence["manager_runtime_sources"] = manager_guard.source_proof()
    evidence["manager_prestartup_noop_state"] = (
        manager_guard.prestartup_state_evidence(
            campaign_layout.actual_user_directory
        )
    )
    evidence["manager_advisory_config"] = manager_guard.config_evidence(
        expected_argv
    )
    evidence["boot_contract"] = {
        "default_manager_disabled": True,
        "test_boot_script": str(TEST_BOOT_CMD),
        "test_opt_in_env": "LAB_MANAGER_OFFLINE_PROBE=1",
        "test_whitelist": EXPECTED_WHITELIST,
        "sage_attention_flag": False,
        "manager_runtime_authority": (
            "exactly one attempt-log network_mode: offline announcement"
        ),
        "vram_lane": {
            "reserve_vram_gib": PROVEN_RESERVE_VRAM_GIB,
            "cache_classic": True,
            "disable_pinned_memory": True,
            "basis": "current flat-V3 h3_r2v_best warm run4",
        },
    }
    return evidence


def require_same_sources(
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
    label: str,
) -> None:
    if baseline != current:
        raise CampaignError(f"campaign source/config evidence changed at {label}")


def expected_server_argv(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> list[str]:
    return [
        str(campaign_layout.comfyui_main),
        "--port",
        "8199",
        "--cuda-malloc",
        "--user-directory",
        str(campaign_layout.actual_user_directory),
        "--output-directory",
        str(campaign_layout.outputs),
        "--extra-model-paths-config",
        str(campaign_layout.root / "comfy_model_paths.yaml"),
        "--disable-metadata",
        "--disable-all-custom-nodes",
        "--whitelist-custom-nodes",
        *EXPECTED_WHITELIST,
        "--reserve-vram",
        "12",
        "--disable-pinned-memory",
        "--cache-classic",
    ]


def validate_server_argv(
    argv: Any, campaign_layout: canon.Layout = DEFAULT_LAYOUT
) -> list[str]:
    expected = expected_server_argv(campaign_layout)
    if not isinstance(argv, list) or len(argv) != len(expected):
        raise CampaignError("receipt server argv shape drift")
    path_positions = {0, 5, 7, 9}
    for index, (actual, wanted) in enumerate(zip(argv, expected)):
        if not isinstance(actual, str):
            raise CampaignError("receipt server argv contains a non-string")
        equal = (
            os.path.normcase(os.path.abspath(actual))
            == os.path.normcase(os.path.abspath(wanted))
            if index in path_positions
            else actual == wanted
        )
        if not equal:
            raise CampaignError(
                f"receipt server argv drift at {index}: {actual!r} != {wanted!r}"
            )
    forbidden = {"--use-sage-attention", "--cache-none"}
    if forbidden.intersection(argv):
        raise CampaignError("receipt server argv contains a forbidden lane flag")
    return list(argv)


def executor_nonce(campaign_id: str, pair_index: int, role: str) -> str:
    validate_campaign_id(campaign_id)
    if role not in {"cold", "warm"}:
        raise CampaignError("cache role must be cold or warm")
    value = f"h3music:{campaign_id}:p{pair_index:02d}:{role}"
    if len(value) > 160:
        raise CampaignError("executor nonce exceeds runner limit")
    return value


def pair_log_path(
    spec: canon.RecipeSpec,
    pair_index: int,
    campaign_id: str,
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> Path:
    validate_campaign_id(campaign_id)
    log_root = (
        campaign_layout.results
        / "h3_unconditioned_music_campaign"
        / "server_logs"
    )
    return log_root / f"{campaign_id}-p{pair_index:02d}-{spec.name}.log"


def failed_attempt_log_path(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> Path:
    return (
        campaign_layout.results
        / "h3_unconditioned_music_campaign"
        / "server_logs"
        / FAILED_LOG_NAME
    )


def recovery_receipt_path(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> Path:
    return (
        campaign_layout.results
        / "h3_unconditioned_music_campaign"
        / "recoveries"
        / f"{FAILED_CAMPAIGN_ID}-manual-cleanup.json"
    )


def attempt2_recovery_receipt_path(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> Path:
    return (
        campaign_layout.results
        / "h3_unconditioned_music_campaign"
        / "recoveries"
        / f"{RESUME_CAMPAIGN_ID}-return120-recovery.json"
    )


def attempt3_recovery_receipt_path(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> Path:
    return (
        campaign_layout.results
        / "h3_unconditioned_music_campaign"
        / "recoveries"
        / f"{RESUME_ATTEMPT2_CAMPAIGN_ID}-stale-pid-recovery.json"
    )


def attempt4_recovery_receipt_path(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> Path:
    return (
        campaign_layout.results
        / "h3_unconditioned_music_campaign"
        / "recoveries"
        / f"{RESUME_ATTEMPT3_CAMPAIGN_ID}-timeout-recovery-correction-001.json"
    )


def attempt4_superseded_recovery_receipt_path(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> Path:
    return (
        campaign_layout.results
        / "h3_unconditioned_music_campaign"
        / "recoveries"
        / f"{RESUME_ATTEMPT3_CAMPAIGN_ID}-timeout-recovery.json"
    )


def attempt2_pair_log_path(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> Path:
    return (
        campaign_layout.results
        / "h3_unconditioned_music_campaign"
        / "server_logs"
        / f"{RESUME_CAMPAIGN_ID}-p01-{CELL_PINS[0][0]}.log"
    )


def attempt3_pair2_log_path(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> Path:
    return (
        campaign_layout.results
        / "h3_unconditioned_music_campaign"
        / "server_logs"
        / f"{RESUME_ATTEMPT2_CAMPAIGN_ID}-p02-{CELL_PINS[1][0]}.log"
    )


def attempt4_pair_log_path(
    spec: canon.RecipeSpec,
    pair_index: int,
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> Path:
    if not 3 <= pair_index <= 10:
        raise CampaignError("attempt-004 Manager log index must be 3 through 10")
    return pair_log_path(
        spec,
        pair_index,
        RESUME_ATTEMPT3_CAMPAIGN_ID,
        campaign_layout,
    )


def require_attempt_manager_log_set(
    campaign_id: str,
    expected_paths: Sequence[Path],
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
    *,
    label: str,
) -> None:
    validate_campaign_id(campaign_id)
    log_root = (
        campaign_layout.results / "h3_unconditioned_music_campaign" / "server_logs"
    )
    found: list[Path] = []
    if os.path.lexists(log_root):
        canon.ensure_real_directory(log_root, "Manager attempt-log directory")
        for entry in log_root.iterdir():
            if not entry.name.startswith(f"{campaign_id}-"):
                continue
            if _is_reparse(entry) or not entry.is_file():
                raise CampaignError(f"{label} Manager log is not a real file: {entry}")
            found.append(Path(os.path.abspath(os.fspath(entry))))
    expected = {
        os.path.normcase(os.path.abspath(os.fspath(path))) for path in expected_paths
    }
    actual = {os.path.normcase(os.path.abspath(os.fspath(path))) for path in found}
    if actual != expected:
        raise CampaignError(
            f"{label} Manager log set drifted: "
            f"found={sorted(path.name for path in found)}"
        )


def operator_transport_paths(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
    attempt_id: str = RESUME_ATTEMPT2_CAMPAIGN_ID,
) -> dict[str, Path]:
    operator_root = (
        campaign_layout.results
        / "h3_unconditioned_music_campaign"
        / "operator_logs"
    )
    attempt_directory = operator_root / validate_campaign_id(attempt_id)

    def absolute(path: Path) -> Path:
        return Path(os.path.abspath(os.fspath(path)))

    return {
        # Keep these lexical so a junction/symlink at any checked leaf is not
        # erased before validate_operator_transport() inspects it.
        "operator_root": absolute(operator_root),
        "attempt_directory": absolute(attempt_directory),
        "stdout": absolute(attempt_directory / "stdout.log"),
        "stderr": absolute(attempt_directory / "stderr.log"),
        "launch_receipt": absolute(attempt_directory / "launch.json"),
    }


def expected_operator_campaign_argv(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
    *,
    attempt_id: str = RESUME_ATTEMPT3_CAMPAIGN_ID,
) -> list[str]:
    paths = operator_transport_paths(campaign_layout, attempt_id)
    resume_switch = {
        RESUME_ATTEMPT3_CAMPAIGN_ID: "--resume-attempt-003",
        RESUME_ATTEMPT4_CAMPAIGN_ID: "--resume-attempt-004",
    }.get(attempt_id)
    if resume_switch is None:
        raise CampaignError("self-reported process provenance attempt is unsupported")
    return [
        str(campaign_layout.python),
        "-B",
        "-u",
        str(CAMPAIGN_SOURCE),
        "--run",
        resume_switch,
        "--campaign-id",
        attempt_id,
        "--operator-stdout-log",
        str(paths["stdout"]),
        "--operator-stderr-log",
        str(paths["stderr"]),
    ]


def validate_campaign_process_identity(
    value: Any,
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
    *,
    attempt_id: str = RESUME_ATTEMPT3_CAMPAIGN_ID,
) -> dict[str, Any]:
    expected_argv = expected_operator_campaign_argv(
        campaign_layout, attempt_id=attempt_id
    )
    attempt_label = (
        "attempt-005"
        if attempt_id == RESUME_ATTEMPT4_CAMPAIGN_ID
        else "attempt-004"
    )
    if not isinstance(value, dict) or set(value) != {
        "authority",
        "pid",
        "process_create_time",
        "cwd",
        "invoked_executable",
        "process_image",
        "argv",
    }:
        raise CampaignError(f"{attempt_label} campaign process identity shape drifted")
    pid = value.get("pid")
    create_time = value.get("process_create_time")
    if (
        value.get("authority") != "campaign self-observation via psutil"
        or not isinstance(pid, int)
        or isinstance(pid, bool)
        or pid <= 0
        or not _finite_positive(create_time)
        or not _same_absolute_path(value.get("cwd", ""), campaign_layout.root)
        or not _same_absolute_path(
            value.get("invoked_executable", ""), campaign_layout.python
        )
        or not isinstance(value.get("process_image"), str)
        or not os.path.isabs(value["process_image"])
        or not isinstance(value.get("argv"), list)
        or not value["argv"]
        or not _same_absolute_path(value["argv"][0], value["process_image"])
        or value["argv"][1:] != expected_argv[1:]
    ):
        raise CampaignError(f"{attempt_label} campaign process identity drifted")
    return dict(value)


def observe_campaign_process_identity(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
    *,
    attempt_id: str = RESUME_ATTEMPT3_CAMPAIGN_ID,
) -> dict[str, Any]:
    pid = os.getpid()
    try:
        process = psutil.Process(pid)
        observed = {
            "authority": "campaign self-observation via psutil",
            "pid": pid,
            "process_create_time": round(float(process.create_time()), 6),
            "cwd": process.cwd(),
            "invoked_executable": sys.executable,
            "process_image": process.exe(),
            "argv": process.cmdline(),
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as exc:
        raise CampaignError(
            f"cannot self-observe campaign process: {exc}"
        ) from exc
    return validate_campaign_process_identity(
        observed, campaign_layout, attempt_id=attempt_id
    )


def child_command(
    spec: canon.RecipeSpec,
    pair_index: int,
    role: str,
    campaign_id: str,
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> list[str]:
    command = [
        str(campaign_layout.python),
        str(campaign_layout.runner),
        str(spec.path),
        "--disable-pinned-memory",
        "--manager-offline-test",
        "--manager-probe-phase",
        role,
        "--executor-cache-nonce",
        executor_nonce(campaign_id, pair_index, role),
    ]
    if campaign_id == RESUME_ATTEMPT4_CAMPAIGN_ID:
        timeout_s = {10: 3_600, 11: 5_400}.get(pair_index)
        if timeout_s is None:
            raise CampaignError("attempt-005 may execute only pairs 10 and 11")
        command.extend(("--completion-timeout-s", str(timeout_s)))
    if role == "warm":
        command.append("--shutdown")
    if "--force" in command:
        raise CampaignError("campaign may never use --force")
    return command


def child_environment(
    log_path: Path, source: Mapping[str, str] | None = None
) -> dict[str, str]:
    environment = dict(source if source is not None else os.environ)
    for key in (
        "LAB_MANAGER_OFFLINE_PROBE",
        "LAB_MANAGER_PROBE_LOG",
        "LAB_RESERVE_VRAM_GB",
        "LAB_DISABLE_PINNED",
        "LAB_CACHE_CLASSIC",
        "LAB_EXTRA_WHITELIST",
        "LAB_SUITE_OWNER_PID",
        "LAB_SUITE_OWNER_CREATE_TIME",
        "LAB_SUITE_NONCE",
        *manager_guard.SCRUBBED_ENVIRONMENT_KEYS,
    ):
        environment.pop(key, None)
    environment.update(manager_guard.OFFLINE_ENVIRONMENT)
    environment["LAB_RESERVE_VRAM_GB"] = "12"
    environment["LAB_CACHE_CLASSIC"] = "1"
    environment["LAB_MANAGER_PROBE_LOG"] = str(log_path.resolve())
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    manager_guard.offline_environment_evidence(environment)
    return environment


def _source_triplet(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": snapshot.get("path"),
        "bytes": snapshot.get("bytes"),
        "sha256": snapshot.get("sha256"),
    }


def operator_log_contract(
    sources: Mapping[str, Any],
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
    *,
    attempt_id: str = RESUME_ATTEMPT2_CAMPAIGN_ID,
) -> dict[str, Any]:
    paths = operator_transport_paths(campaign_layout, attempt_id)
    source_prefix = {
        RESUME_ATTEMPT2_CAMPAIGN_ID: "",
        RESUME_ATTEMPT3_CAMPAIGN_ID: "attempt4_",
        RESUME_ATTEMPT4_CAMPAIGN_ID: "attempt5_",
    }.get(attempt_id)
    if source_prefix is None:
        raise CampaignError("operator log contract attempt is unsupported")
    return {
        "authority": "operator transport only",
        "attempt_directory": str(paths["attempt_directory"]),
        "stdout_log": str(paths["stdout"]),
        "stderr_log": str(paths["stderr"]),
        "launch_receipt": str(paths["launch_receipt"]),
        "launcher_source": _source_triplet(
            sources.get(f"{source_prefix}operator_launcher") or {}
        ),
        "recorder_source": _source_triplet(
            sources.get(f"{source_prefix}operator_recorder") or {}
        ),
        "growing_logs_excluded_from_source_evidence": True,
        "certification_effect": {
            "campaign_status_changed": False,
            "recipe_or_pair_certification_granted": False,
            "exit_120_reclassified_as_success": False,
            "human_quality_judgment_granted": False,
        },
    }


def _same_absolute_path(value: str | os.PathLike[str], expected: Path) -> bool:
    return os.path.normcase(os.path.abspath(os.fspath(value))) == os.path.normcase(
        os.path.abspath(os.fspath(expected))
    )


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & 0x400)


def validate_operator_transport(
    stdout_log: str | os.PathLike[str] | None,
    stderr_log: str | os.PathLike[str] | None,
    sources: Mapping[str, Any],
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
    *,
    attempt_id: str = RESUME_ATTEMPT2_CAMPAIGN_ID,
    stdout_fd: int | None = None,
    stderr_fd: int | None = None,
) -> dict[str, Any]:
    """Bind one exact attempt's CLI paths to its process output FDs."""

    attempt_label = {
        RESUME_ATTEMPT2_CAMPAIGN_ID: "attempt-003",
        RESUME_ATTEMPT3_CAMPAIGN_ID: "attempt-004",
        RESUME_ATTEMPT4_CAMPAIGN_ID: "attempt-005",
    }.get(attempt_id)
    if attempt_label is None:
        raise CampaignError("operator transport attempt is unsupported")
    if stdout_log is None or stderr_log is None:
        raise CampaignError(f"{attempt_label} requires both operator log path arguments")
    paths = operator_transport_paths(campaign_layout, attempt_id)
    if not _same_absolute_path(stdout_log, paths["stdout"]):
        raise CampaignError(f"{attempt_label} operator stdout path drifted")
    if not _same_absolute_path(stderr_log, paths["stderr"]):
        raise CampaignError(f"{attempt_label} operator stderr path drifted")
    for label in ("operator_root", "attempt_directory"):
        path = paths[label]
        if not os.path.lexists(path) or _is_reparse(path) or not path.is_dir():
            raise CampaignError(f"{attempt_label} {label} is not a real directory")
    entries = {entry.name for entry in paths["attempt_directory"].iterdir()}
    if entries != {"stdout.log", "stderr.log"}:
        raise CampaignError(
            f"{attempt_label} operator directory entries drifted: "
            f"{sorted(entries)}"
        )
    if os.path.lexists(paths["launch_receipt"]):
        raise CampaignError(f"{attempt_label} launch receipt exists before campaign exit")

    file_stats: dict[str, os.stat_result] = {}
    for label in ("stdout", "stderr"):
        path = paths[label]
        if not os.path.lexists(path) or _is_reparse(path) or not path.is_file():
            raise CampaignError(f"{attempt_label} operator {label} is not a real file")
        file_stats[label] = path.stat()
        if int(file_stats[label].st_nlink) != 1:
            raise CampaignError(
                f"{attempt_label} operator {label} path has external hardlinks"
            )
    try:
        if os.path.samefile(paths["stdout"], paths["stderr"]):
            raise CampaignError(f"{attempt_label} stdout and stderr are the same file")
    except CampaignError:
        raise
    except OSError as exc:
        raise CampaignError(f"cannot distinguish {attempt_label} operator logs: {exc}") from exc

    try:
        stdout_fd = sys.stdout.fileno() if stdout_fd is None else stdout_fd
        stderr_fd = sys.stderr.fileno() if stderr_fd is None else stderr_fd
        descriptor_stats = {
            "stdout": os.fstat(stdout_fd),
            "stderr": os.fstat(stderr_fd),
        }
    except (AttributeError, OSError, ValueError) as exc:
        raise CampaignError(f"cannot inspect {attempt_label} output descriptors: {exc}") from exc
    if stdout_fd == stderr_fd:
        raise CampaignError(f"{attempt_label} stdout and stderr share one descriptor")
    identities: dict[str, Any] = {}
    for label, fd in (("stdout", stdout_fd), ("stderr", stderr_fd)):
        descriptor = descriptor_stats[label]
        path_stat = file_stats[label]
        if not stat.S_ISREG(descriptor.st_mode):
            raise CampaignError(f"{attempt_label} {label} descriptor is not a regular file")
        if int(descriptor.st_nlink) != 1:
            raise CampaignError(
                f"{attempt_label} {label} descriptor has external hardlinks"
            )
        fd_identity = (int(descriptor.st_dev), int(descriptor.st_ino))
        path_identity = (int(path_stat.st_dev), int(path_stat.st_ino))
        if fd_identity != path_identity:
            raise CampaignError(
                f"{attempt_label} {label} descriptor does not target its exact log path"
            )
        identities[label] = {
            "path": str(paths[label]),
            "fd": int(fd),
            "device": fd_identity[0],
            "inode": fd_identity[1],
            "link_count": 1,
            "regular_file": True,
        }
    if (
        identities["stdout"]["device"],
        identities["stdout"]["inode"],
    ) == (
        identities["stderr"]["device"],
        identities["stderr"]["inode"],
    ):
        raise CampaignError(f"{attempt_label} output descriptors resolve to one file")
    return {
        "contract": operator_log_contract(
            sources, campaign_layout, attempt_id=attempt_id
        ),
        "attempt_directory_entries": ["stderr.log", "stdout.log"],
        "fd_identities": identities,
        "growing_log_bytes_hashed_as_sources": False,
    }


def pair_run_schedule(
    pair_index: int,
    resume_attempt_001: bool,
    resume_attempt_002: bool = False,
    resume_attempt_003: bool = False,
    resume_attempt_004: bool = False,
) -> dict[str, Any]:
    if not isinstance(pair_index, int) or isinstance(pair_index, bool) or not 1 <= pair_index <= 11:
        raise CampaignError("pair index must be 1 through 11")
    if sum(
        (
            resume_attempt_001,
            resume_attempt_002,
            resume_attempt_003,
            resume_attempt_004,
        )
    ) > 1:
        raise CampaignError("attempt recovery modes are mutually exclusive")
    if (
        resume_attempt_001
        or resume_attempt_002
        or resume_attempt_003
        or resume_attempt_004
    ) and pair_index == 1:
        return {
            "cold_run_number": 2,
            "cold_config_run_count": 1,
            "warm_run_number": 3,
            "warm_config_run_count": 2,
            "allowed_run_numbers": [1, 2, 3],
            "cold_artifact_index": 2,
            "warm_artifact_index": 3,
            "allowed_artifact_indices": [1, 2, 3],
            "preserved_historical_run_numbers": [1],
            "reason": (
                "attempt-002 already produced the fully verified run2 cold/run3 "
                "warm pair on one server; attempt-003 carries that exact pair"
                if (resume_attempt_002 or resume_attempt_003 or resume_attempt_004)
                else (
                    "attempt-001 run1 is valid cold evidence, but its server ended; "
                    "run2 must therefore be cold on a new server and run3 warm on "
                    "that same server"
                )
            ),
        }
    if (resume_attempt_003 or resume_attempt_004) and pair_index == 2:
        return {
            "cold_run_number": 1,
            "cold_config_run_count": 1,
            "warm_run_number": 2,
            "warm_config_run_count": 2,
            "allowed_run_numbers": [1, 2],
            "cold_artifact_index": 1,
            "warm_artifact_index": 2,
            "allowed_artifact_indices": [1, 2],
            "preserved_historical_run_numbers": [],
            "reason": (
                "attempt-003 produced the fully verified pair2 run1 cold/run2 "
                "warm pair; attempt-004 carries those exact bytes"
            ),
        }
    if resume_attempt_004 and pair_index == 10:
        return {
            "cold_run_number": 2,
            "cold_config_run_count": 1,
            "warm_run_number": 3,
            "warm_config_run_count": 2,
            "allowed_run_numbers": [1, 2, 3],
            "cold_artifact_index": 1,
            "warm_artifact_index": 2,
            "allowed_artifact_indices": [1, 2],
            "preserved_historical_run_numbers": [1],
            "completion_timeout_s": 3_600,
            "reason": (
                "attempt-004 run1 timed out after sampling with no finalized "
                "artifact; run2 must be cold on a new server and run3 warm on "
                "that same server"
            ),
        }
    if resume_attempt_004 and pair_index == 11:
        return {
            "cold_run_number": 1,
            "cold_config_run_count": 1,
            "warm_run_number": 2,
            "warm_config_run_count": 2,
            "allowed_run_numbers": [1, 2],
            "cold_artifact_index": 1,
            "warm_artifact_index": 2,
            "allowed_artifact_indices": [1, 2],
            "preserved_historical_run_numbers": [],
            "completion_timeout_s": 5_400,
            "reason": "attempt-005 long-frame cold/warm pair on one new server",
        }
    return {
        "cold_run_number": 1,
        "cold_config_run_count": 1,
        "warm_run_number": 2,
        "warm_config_run_count": 2,
        "allowed_run_numbers": [1, 2],
        "cold_artifact_index": 1,
        "warm_artifact_index": 2,
        "allowed_artifact_indices": [1, 2],
        "preserved_historical_run_numbers": [],
        "reason": "ordinary cold/warm pair on one new server",
    }


def runbook(
    campaign_id: str = "DRY-RUN",
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
    *,
    resume_attempt_001: bool = False,
    resume_attempt_002: bool = False,
    resume_attempt_003: bool = False,
    resume_attempt_004: bool = False,
) -> dict[str, Any]:
    campaign_id = validate_campaign_id(campaign_id)
    if sum(
        (
            resume_attempt_001,
            resume_attempt_002,
            resume_attempt_003,
            resume_attempt_004,
        )
    ) > 1:
        raise CampaignError("attempt recovery modes are mutually exclusive")
    if resume_attempt_002 and campaign_id != RESUME_ATTEMPT2_CAMPAIGN_ID:
        raise CampaignError(
            "attempt-002 recovery must use exact campaign id "
            f"{RESUME_ATTEMPT2_CAMPAIGN_ID}"
        )
    if resume_attempt_003 and campaign_id != RESUME_ATTEMPT3_CAMPAIGN_ID:
        raise CampaignError(
            "attempt-004 continuation must use exact campaign id "
            f"{RESUME_ATTEMPT3_CAMPAIGN_ID}"
        )
    if resume_attempt_004 and campaign_id != RESUME_ATTEMPT4_CAMPAIGN_ID:
        raise CampaignError(
            "attempt-005 continuation must use exact campaign id "
            f"{RESUME_ATTEMPT4_CAMPAIGN_ID}"
        )
    specs = load_specs(campaign_layout)
    pairs = []
    nonces = []
    for index, spec in enumerate(specs, start=1):
        roles = next(row[4] for row in CELL_PINS if row[0] == spec.name)
        schedule = pair_run_schedule(
            index,
            resume_attempt_001,
            resume_attempt_002,
            resume_attempt_003,
            resume_attempt_004,
        )
        if resume_attempt_004 and index <= 9:
            if index == 1:
                source_campaign_id = RESUME_CAMPAIGN_ID
                manager_log = attempt2_pair_log_path(campaign_layout)
            elif index == 2:
                source_campaign_id = RESUME_ATTEMPT2_CAMPAIGN_ID
                manager_log = attempt3_pair2_log_path(campaign_layout)
            else:
                source_campaign_id = RESUME_ATTEMPT3_CAMPAIGN_ID
                manager_log = attempt4_pair_log_path(
                    spec, index, campaign_layout
                )
            pairs.append(
                {
                    "pair_index": index,
                    "action": "carry_forward",
                    "source_campaign_id": source_campaign_id,
                    "recipe": spec.name,
                    "recipe_sha256": spec.sha256,
                    "logical_roles": list(roles),
                    "manager_log": str(manager_log),
                    "receipt_schedule": schedule,
                    "new_executions": 0,
                    "recovery_receipt": str(
                        attempt4_recovery_receipt_path(campaign_layout)
                    ),
                }
            )
            continue
        if (resume_attempt_002 or resume_attempt_003) and index == 1:
            pairs.append(
                {
                    "pair_index": index,
                    "action": "carry_forward",
                    "source_campaign_id": RESUME_CAMPAIGN_ID,
                    "recipe": spec.name,
                    "recipe_sha256": spec.sha256,
                    "logical_roles": list(roles),
                    "manager_log": str(attempt2_pair_log_path(campaign_layout)),
                    "receipt_schedule": schedule,
                    "new_executions": 0,
                    "recovery_receipt": str(
                        attempt2_recovery_receipt_path(campaign_layout)
                    ),
                }
            )
            continue
        if resume_attempt_003 and index == 2:
            pairs.append(
                {
                    "pair_index": index,
                    "action": "carry_forward",
                    "source_campaign_id": RESUME_ATTEMPT2_CAMPAIGN_ID,
                    "recipe": spec.name,
                    "recipe_sha256": spec.sha256,
                    "logical_roles": list(roles),
                    "manager_log": str(attempt3_pair2_log_path(campaign_layout)),
                    "receipt_schedule": schedule,
                    "new_executions": 0,
                    "recovery_receipt": str(
                        attempt3_recovery_receipt_path(campaign_layout)
                    ),
                }
            )
            continue
        log_path = pair_log_path(spec, index, campaign_id, campaign_layout)
        cold = child_command(spec, index, "cold", campaign_id, campaign_layout)
        warm = child_command(spec, index, "warm", campaign_id, campaign_layout)
        nonces.extend(
            (
                cold[cold.index("--executor-cache-nonce") + 1],
                warm[warm.index("--executor-cache-nonce") + 1],
            )
        )
        pairs.append(
            {
                "pair_index": index,
                "action": "execute",
                "recipe": spec.name,
                "recipe_sha256": spec.sha256,
                "logical_roles": list(roles),
                "manager_log": str(log_path),
                "receipt_schedule": schedule,
                "cold": cold,
                "warm_shutdown": warm,
                "new_executions": 2,
            }
        )
    expected_nonce_count = (
        4
        if resume_attempt_004
        else (18 if resume_attempt_003 else (20 if resume_attempt_002 else 22))
    )
    if len(nonces) != expected_nonce_count or len(set(nonces)) != expected_nonce_count:
        raise CampaignError("executor nonces are not globally unique")
    operator_paths = operator_transport_paths(
        campaign_layout,
        (
            RESUME_ATTEMPT4_CAMPAIGN_ID
            if resume_attempt_004
            else (
                RESUME_ATTEMPT3_CAMPAIGN_ID
                if resume_attempt_003
                else RESUME_ATTEMPT2_CAMPAIGN_ID
            )
        ),
    )
    return {
        "schema_version": 1,
        "campaign": "H3_UNCONDITIONED_MUSIC",
        "campaign_id": campaign_id,
        "default_read_only": True,
        "execution_authority": "run_recipe.py only",
        "pair_count": 11,
        "logical_cell_count": 14,
        "actual_execution_count": expected_nonce_count,
        "new_execution_count": expected_nonce_count,
        "study_leg_count": 22,
        "orphan_historical_cold_count": 1 if (resume_attempt_002 or resume_attempt_003 or resume_attempt_004) else 0,
        "valid_orphan_historical_cold_count": 1 if resume_attempt_004 else 0,
        "failed_historical_execution_count": 1 if resume_attempt_004 else 0,
        "evidence_execution_count": 24 if resume_attempt_004 else (23 if (resume_attempt_002 or resume_attempt_003) else 22),
        "carried_pair_count": 9 if resume_attempt_004 else (2 if resume_attempt_003 else (1 if resume_attempt_002 else 0)),
        "executed_pair_count": 2 if resume_attempt_004 else (9 if resume_attempt_003 else (10 if resume_attempt_002 else 11)),
        "resume_attempt_001": resume_attempt_001,
        "resume_attempt_002": resume_attempt_002,
        "resume_attempt_003": resume_attempt_003,
        "resume_attempt_004": resume_attempt_004,
        "recovery_receipt": (
            str(attempt4_recovery_receipt_path(campaign_layout))
            if resume_attempt_004
            else (
                str(attempt3_recovery_receipt_path(campaign_layout))
                if resume_attempt_003
                else (
                    str(attempt2_recovery_receipt_path(campaign_layout))
                    if resume_attempt_002
                    else (
                        str(recovery_receipt_path(campaign_layout))
                        if resume_attempt_001
                        else None
                    )
                )
            )
        ),
        "attempt_003_execution": (
            {
                "pair1": "carried from fully verified attempt-002 run2/run3",
                "pairs_2_through_11": "execute cold/warm",
                "new_execution_count": 20,
                "study_legs": 22,
                "orphan_historical_cold": 1,
                "operator_attempt_directory": str(operator_paths["attempt_directory"]),
                "operator_stdout_log": str(operator_paths["stdout"]),
                "operator_stderr_log": str(operator_paths["stderr"]),
            }
            if resume_attempt_002
            else None
        ),
        "attempt_004_execution": (
            {
                "pairs_1_and_2": "carried from fully verified recovery receipts",
                "pairs_3_through_11": "execute cold/warm",
                "new_execution_count": 18,
                "study_legs": 22,
                "orphan_historical_cold": 1,
                "operator_attempt_directory": str(operator_paths["attempt_directory"]),
                "operator_stdout_log": str(operator_paths["stdout"]),
                "operator_stderr_log": str(operator_paths["stderr"]),
            }
            if resume_attempt_003
            else None
        ),
        "attempt_005_execution": (
            {
                "pairs_1_through_9": "carried from corrected sealed attempt-004 recovery",
                "pairs_10_and_11": "execute cold/warm",
                "new_execution_count": 4,
                "study_legs": 22,
                "valid_orphan_historical_cold": 1,
                "failed_historical_execution": 1,
                "operator_attempt_directory": str(operator_paths["attempt_directory"]),
                "operator_stdout_log": str(operator_paths["stdout"]),
                "operator_stderr_log": str(operator_paths["stderr"]),
            }
            if resume_attempt_004
            else None
        ),
        "control_reuse": {
            "recipe": CELL_PINS[0][0],
            "logical_roles": list(CELL_PINS[0][4]),
            "saved_pairs": 3,
            "saved_executions": 6,
            "basis": "exact recipe + receipt + artifact + boot identity",
        },
        "manager_policy": {
            "ordinary_boot": "Manager disabled",
            "this_test_lane": "Manager explicitly whitelisted only for runtime offline proof",
            "authority": "exactly one attempt-log network_mode: offline line before prompt",
        },
        "boot_invariants": {
            "reserve_vram_gib": PROVEN_RESERVE_VRAM_GIB,
            "cache_classic": True,
            "disable_pinned_memory": True,
            "sage_attention": False,
        },
        "pairs": pairs,
    }


def ensure_pristine_pair(
    spec: canon.RecipeSpec,
    log_path: Path,
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
    *,
    resume_attempt_001: bool = False,
    resume_attempt_004: bool = False,
    pair_index: int | None = None,
) -> None:
    if resume_attempt_004 and pair_index == 10:
        expected_receipts = {
            f"{spec.name}.json",
            f"{spec.name}_run1.json",
        }
        found_receipts = {
            path.name
            for path in campaign_layout.results.iterdir()
            if path.name == f"{spec.name}.json"
            or path.name.startswith(f"{spec.name}_run")
        }
        found_outputs = {
            path.name
            for path in campaign_layout.outputs.iterdir()
            if path.name.startswith(spec.prefix)
        }
        archive = campaign_layout.results / f"{spec.name}_run1.json"
        alias = campaign_layout.results / f"{spec.name}.json"
        archive_raw, archive_snapshot = canon.stable_file(
            archive, "attempt-004 pair10 failed run1"
        )
        alias_raw, alias_snapshot = canon.stable_file(
            alias, "attempt-004 pair10 failed alias"
        )
        if (
            found_receipts != expected_receipts
            or found_outputs
            or archive_raw != alias_raw
            or archive_snapshot.get("bytes") != ATTEMPT4_PAIR10_RUN1_BYTES
            or archive_snapshot.get("sha256") != ATTEMPT4_PAIR10_RUN1_SHA256
            or alias_snapshot.get("bytes") != ATTEMPT4_PAIR10_RUN1_BYTES
            or alias_snapshot.get("sha256") != ATTEMPT4_PAIR10_RUN1_SHA256
        ):
            raise CampaignError(
                "attempt-005 pair10 initial failed history is not exact: "
                f"receipts={sorted(found_receipts)}, outputs={sorted(found_outputs)}"
            )
    elif resume_attempt_001 and pair_index == 1:
        expected_receipts = {
            f"{spec.name}.json",
            f"{spec.name}_run1.json",
        }
        found_receipts = {
            path.name
            for path in campaign_layout.results.iterdir()
            if path.name == f"{spec.name}.json"
            or path.name.startswith(f"{spec.name}_run")
        }
        expected_outputs = {f"{spec.prefix}_00001_.mp4"}
        found_outputs = {
            path.name
            for path in campaign_layout.outputs.iterdir()
            if path.name.startswith(spec.prefix)
        }
        if found_receipts != expected_receipts or found_outputs != expected_outputs:
            raise CampaignError(
                "attempt-002 control history is not exactly preserved run1: "
                f"receipts={sorted(found_receipts)}, outputs={sorted(found_outputs)}"
            )
    else:
        canon.ensure_pristine_history(spec, campaign_layout)
    if os.path.lexists(log_path):
        raise CampaignError(f"attempt-unique Manager log already exists: {log_path}")


def _finite_positive(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0
    )


def expected_manager_identity(evidence: Mapping[str, Any]) -> dict[str, Any]:
    advisory = evidence.get("advisory_config") or {}
    scan = evidence.get("log_scan") or {}
    authority = scan.get("authoritative_server_reported_mode") or {}
    source = scan.get("source_proof") or {}
    return {
        "guard_source": evidence.get("guard_source"),
        "test_boot_source": evidence.get("test_boot_source"),
        "offline_environment": evidence.get("offline_environment"),
        "advisory_config_path": (advisory.get("snapshot") or {}).get("path"),
        "advisory_config_sha256": (advisory.get("snapshot") or {}).get("sha256"),
        "authoritative_server_reported_mode": authority.get("resolved_mode"),
        "manager_source_sha256s": {
            key: (source.get(key) or {}).get("sha256")
            for key in (
                "manager_prestartup",
                "manager_server",
                "manager_core",
                "comfy_folder_paths",
                "manager_util",
            )
        },
        "prestartup_state_sha256": (
            (scan.get("current_prestartup_state") or {}).get("state_sha256")
        ),
        "preboot_record_sha256": (
            ((scan.get("preboot_records") or [{}])[0].get("record") or {}).get(
                "record_sha256"
            )
        ),
        "log_path": evidence.get("log_path"),
        "serving_pid": evidence.get("serving_pid"),
        "serving_process_create_time_ns": evidence.get(
            "serving_process_create_time_ns"
        ),
    }


def verify_manager_receipt(
    receipt: Mapping[str, Any],
    *,
    log_path: Path,
    argv: Sequence[str],
    role: str,
) -> dict[str, Any]:
    if role not in {"cold", "warm"}:
        raise CampaignError("Manager receipt role must be cold or warm")
    cold = role == "cold"
    bundle = receipt.get("manager_offline_probe")
    if not isinstance(bundle, dict) or bundle.get("provenance_unchanged") is not True:
        raise CampaignError("Manager receipt bundle is missing or changed")
    pre = bundle.get("pre_queue")
    post = bundle.get("post_render")
    if not isinstance(pre, dict) or not isinstance(post, dict):
        raise CampaignError("Manager pre/post receipt evidence is missing")
    for label, evidence in (("pre", pre), ("post", post)):
        if (
            evidence.get("enabled") is not True
            or evidence.get("valid") is not True
            or evidence.get("log_path") != str(log_path.resolve())
            or evidence.get("offline_environment")
            != manager_guard.offline_environment_evidence(
                {
                    **manager_guard.OFFLINE_ENVIRONMENT,
                }
            )
        ):
            raise CampaignError(f"Manager {label} evidence identity drift")
        advisory = evidence.get("advisory_config") or {}
        current_config = manager_guard.config_evidence(argv)
        if advisory != current_config:
            raise CampaignError(f"Manager {label} advisory config drift")
        scan = evidence.get("log_scan")
        if not isinstance(scan, dict):
            raise CampaignError(f"Manager {label} scan is missing")
        errors = manager_guard.validate_scan_binding(scan, log_path, argv)
        if errors:
            raise CampaignError(f"Manager {label} log binding failed: {errors}")
        authority = scan.get("authoritative_server_reported_mode") or {}
        if (
            authority.get("announcement_count") != 1
            or authority.get("observed_values") != ["offline"]
            or authority.get("resolved_mode") != "offline"
            or authority.get("mode_precedes_startup_completion") is not True
            or authority.get("mode_precedes_first_execution") is not True
            or scan.get("network_markers") != []
            or scan.get("mutation_markers") != []
        ):
            raise CampaignError(f"Manager {label} runtime authority failed")
    if (
        pre.get("require_no_prior_prompt") is not cold
        or (pre.get("log_scan") or {}).get("require_pre_prompt")
        is not cold
    ):
        raise CampaignError("Manager cold/warm pre-prompt phase drift")
    if cold and (pre.get("log_scan") or {}).get("execution_markers") != []:
        raise CampaignError("cold Manager gate was not evaluated before first prompt")
    if expected_manager_identity(pre) != expected_manager_identity(post):
        raise CampaignError("Manager immutable identity changed during render")
    identity = receipt.get("identity") or {}
    if identity.get("manager_offline_probe_identity") != expected_manager_identity(pre):
        raise CampaignError("run identity does not bind Manager offline proof")
    return {"pre_queue": pre, "post_render": post}


def verify_run_receipt(
    spec: canon.RecipeSpec,
    run_number: int,
    nonce: str,
    sources: Mapping[str, Any],
    log_path: Path,
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
    *,
    role: str | None = None,
    expected_config_run_count: int | None = None,
    expected_completion_timeout_s: int | None = None,
    expected_artifact_index: int | None = None,
    require_alias_current: bool = True,
) -> dict[str, Any]:
    archive = campaign_layout.results / f"{spec.name}_run{run_number}.json"
    alias = campaign_layout.results / f"{spec.name}.json"
    receipt, archive_raw = canon.strict_json(
        archive, f"{spec.name} immutable run {run_number} receipt"
    )
    if require_alias_current:
        _, alias_raw = canon.strict_json(alias, f"{spec.name} current receipt")
        if alias_raw != archive_raw:
            raise CampaignError("current receipt alias is not the warm archive")
    if role is None:
        role = "warm" if run_number == 2 else "cold"
    if role not in {"cold", "warm"}:
        raise CampaignError("receipt role must be cold or warm")
    warm = role == "warm"
    if expected_config_run_count is None:
        expected_config_run_count = 2 if warm else 1
    if (
        not isinstance(expected_config_run_count, int)
        or isinstance(expected_config_run_count, bool)
        or expected_config_run_count < 1
    ):
        raise CampaignError("expected configuration run count is invalid")
    required = {
        "receipt_schema_version": 3,
        "recipe": spec.name,
        "run_number": run_number,
        "run_count": run_number,
        "config_run_count": expected_config_run_count,
        "gate_pass": True,
        "pass": warm,
        "warm_pass": warm,
        "recipe_sha256": spec.sha256,
        "runner_sha256": sources["runner"]["sha256"],
        "lab_locks_sha256": sources["lab_locks"]["sha256"],
        "provenance_unchanged": True,
        "provenance_validation_error": "",
        "server_instance_unchanged": True,
        "valid_measurement": True,
        "accepted_prompt": True,
        "blocked": False,
        "requires_human_eyeball": True,
        "eyeball": "pending",
        "promotion_ready": False,
        "certification_scope": "machine-only",
        "boot_lane": EXPECTED_BOOT_LANE,
        "clamp_target_gib": None,
        "reserve_vram_gib": PROVEN_RESERVE_VRAM_GIB,
        "encoded_width": 1344,
        "encoded_height": 768,
        "encoded_frame_count": spec.frames,
        "encoded_fps": 24.0,
        "audio_present": True,
    }
    for field, expected in required.items():
        if receipt.get(field) != expected:
            raise CampaignError(
                f"{spec.name} run {run_number} field {field} drift: "
                f"{receipt.get(field)!r} != {expected!r}"
            )
    if expected_completion_timeout_s is not None:
        if (
            not isinstance(expected_completion_timeout_s, int)
            or isinstance(expected_completion_timeout_s, bool)
            or not 1 <= expected_completion_timeout_s <= 7_200
            or receipt.get("completion_timeout_s")
            != expected_completion_timeout_s
        ):
            raise CampaignError(
                f"{spec.name} run {run_number} completion timeout drift"
            )
    statuses = {"PASS", "PASS (marginal)"} if warm else {
        "PASS (cold)",
        "PASS (cold, marginal)",
    }
    if receipt.get("status") not in statuses:
        raise CampaignError(f"{spec.name} run {run_number} status is not a gate pass")
    peak = receipt.get("peak_vram_gb")
    duration = receipt.get("duration_s")
    if not _finite_positive(peak) or float(peak) > 14.5 or not _finite_positive(duration):
        raise CampaignError(f"{spec.name} run {run_number} numeric gate evidence invalid")
    for field in ("baseline_vram_gb", "peak_host_ram_gb", "baseline_host_ram_gb"):
        value = receipt.get(field)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or float(value) < 0
        ):
            raise CampaignError(f"{spec.name} run {run_number} {field} is invalid")
    if float(receipt["baseline_vram_gb"]) > float(peak):
        raise CampaignError("baseline VRAM exceeds recorded peak")
    marginal = receipt.get("marginal")
    if not isinstance(marginal, bool):
        raise CampaignError("receipt marginal field is not boolean")
    if float(peak) < 14.25 and marginal is not False:
        raise CampaignError("sub-14.25 receipt is incorrectly marginal")
    if float(peak) > 14.25 and marginal is not True:
        raise CampaignError("over-14.25 receipt is not marked marginal")
    if marginal != ("marginal" in str(receipt.get("status"))):
        raise CampaignError("receipt status/marginal classification mismatch")
    expected_video_duration = spec.frames / 24.0
    if (
        not _finite_positive(receipt.get("video_duration_s"))
        or abs(float(receipt["video_duration_s"]) - expected_video_duration) > 0.05
        or not _finite_positive(receipt.get("audio_duration_s"))
        or abs(float(receipt["audio_duration_s"]) - expected_video_duration) > 0.1
    ):
        raise CampaignError("native audio/video duration evidence drift")
    argv = validate_server_argv(receipt.get("server_argv"), campaign_layout)
    server_instance = receipt.get("server_instance")
    if (
        not isinstance(server_instance, dict)
        or server_instance != receipt.get("final_server_instance")
        or not isinstance(server_instance.get("serving_pid"), int)
        or isinstance(server_instance.get("serving_pid"), bool)
        or server_instance["serving_pid"] <= 0
        or not _finite_positive(server_instance.get("process_create_time"))
    ):
        raise CampaignError("server identity evidence is invalid")
    identity = receipt.get("identity")
    if not isinstance(identity, dict) or canon.stable_identity(identity) != receipt.get(
        "run_identity_sha256"
    ):
        raise CampaignError("run identity hash mismatch")
    comfy_commit = receipt.get("comfyui_git_commit")
    if (
        not isinstance(comfy_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", comfy_commit) is None
        or identity.get("comfyui_git_commit") != comfy_commit
    ):
        raise CampaignError("ComfyUI commit identity drift")
    expected_identity = {
        "recipe_sha256": spec.sha256,
        "runner_sha256": sources["runner"]["sha256"],
        "lab_locks_sha256": sources["lab_locks"]["sha256"],
        "fixture_sha256s": dict(spec.fixture_hashes),
        "boot_lane": EXPECTED_BOOT_LANE,
        "server_argv": argv,
        "server_instance": server_instance,
    }
    if expected_completion_timeout_s is not None:
        expected_identity["completion_timeout_s"] = expected_completion_timeout_s
    for field, expected in expected_identity.items():
        if identity.get(field) != expected:
            raise CampaignError(f"run identity field drift: {field}")
    if receipt.get("fixture_sha256s") != dict(spec.fixture_hashes):
        raise CampaignError("portrait fixture identity drift")
    models = canon.validate_model_fingerprints(spec, receipt.get("model_fingerprints"))
    if identity.get("model_fingerprints") != models:
        raise CampaignError("model identity drift")
    if receipt.get("audio_receipt_sha256s") != {} or identity.get(
        "audio_receipt_sha256s"
    ) != {}:
        raise CampaignError("unconditioned study unexpectedly binds input audio")
    manager = verify_manager_receipt(
        receipt, log_path=log_path, argv=argv, role=role
    )
    expected_guard = sources.get("manager_guard") or {}
    expected_test_boot = sources.get("manager_test_boot_cmd") or {}
    for phase in (manager["pre_queue"], manager["post_render"]):
        retained_guard = phase.get("guard_source") or {}
        retained_test_boot = phase.get("test_boot_source") or {}
        if (
            retained_guard.get("path") != expected_guard.get("path")
            or retained_guard.get("sha256") != expected_guard.get("sha256")
            or retained_test_boot.get("path") != expected_test_boot.get("path")
            or retained_test_boot.get("sha256") != expected_test_boot.get("sha256")
        ):
            raise CampaignError("Manager guard/test-boot source is not campaign-bound")
    cache = receipt.get("execution_cache_control")
    expected_cache = canon.expected_cache_contract(spec, nonce)
    if not isinstance(cache, dict):
        raise CampaignError("executor cache receipt is missing")
    for field, expected in expected_cache.items():
        if field == "queued_prompt_sha256":
            continue
        if cache.get(field) != expected:
            raise CampaignError(f"executor cache field drift: {field}")
    if cache.get("cache_event_found") is not True or cache.get(
        "fresh_execution_proved"
    ) is not True or cache.get("cached_fresh_node_ids") != []:
        raise CampaignError("fresh sampler/output execution is unproved")
    cached = cache.get("cached_node_ids")
    if not isinstance(cached, list) or len(cached) != len(set(cached)):
        raise CampaignError("cached node evidence is malformed")
    stable = set(expected_cache["stable_node_ids"])
    if not set(cached).issubset(stable):
        raise CampaignError("cache hits escape the stable closure")
    if (not warm and cached != []) or (warm and not stable.issubset(set(cached))):
        raise CampaignError("cold/warm cache role is unproved")
    runtime = receipt.get("standalone_cache_runtime_sha256s")
    if (
        not isinstance(runtime, dict)
        or runtime != receipt.get("final_standalone_cache_runtime_sha256s")
        or identity.get("standalone_cache_runtime_sha256s") != runtime
        or set(runtime) != canon.EXPECTED_STANDALONE_CACHE_SOURCES
        or any(
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            for digest in runtime.values()
        )
    ):
        raise CampaignError("standalone cache runtime identity drift")
    if expected_artifact_index is None:
        expected_artifact_index = run_number
    if (
        not isinstance(expected_artifact_index, int)
        or isinstance(expected_artifact_index, bool)
        or expected_artifact_index < 1
    ):
        raise CampaignError("expected artifact index is invalid")
    expected_name = f"{spec.prefix}_{expected_artifact_index:05d}_.mp4"
    artifact_path, artifact = canon.strict_artifact(
        receipt.get("output_path"), expected_name, campaign_layout
    )
    if (
        receipt.get("artifact_sha256") != artifact["sha256"]
        or receipt.get("artifact_bytes") != artifact["bytes"]
        or receipt.get("queued_prompt_sha256")
        != expected_cache["queued_prompt_sha256"]
    ):
        raise CampaignError("artifact or queued prompt evidence drift")
    return {
        "receipt": str(archive),
        "receipt_sha256": sha256_bytes(archive_raw),
        "artifact": artifact,
        "artifact_path": str(artifact_path),
        "identity": identity,
        "run_identity_sha256": receipt["run_identity_sha256"],
        "server_instance": server_instance,
        "server_argv": argv,
        "queued_prompt_sha256": receipt["queued_prompt_sha256"],
        "manager": manager,
        "peak_vram_gb": peak,
        "duration_s": duration,
    }


def verify_failed_attempt_evidence(
    sources: Mapping[str, Any],
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
    *,
    require_alias_run1: bool,
) -> dict[str, Any]:
    specs = load_specs(campaign_layout)
    control = specs[0]
    lifecycle_raw, _ = canon.stable_file(
        campaign_layout.lifecycle, "attempt-001 lifecycle"
    )
    if len(lifecycle_raw) < FAILED_LIFECYCLE_PREFIX_BYTES:
        raise CampaignError("attempt-001 lifecycle was truncated")
    prefix = lifecycle_raw[:FAILED_LIFECYCLE_PREFIX_BYTES]
    if sha256_bytes(prefix) != FAILED_LIFECYCLE_PREFIX_SHA256:
        raise CampaignError("attempt-001 lifecycle prefix changed")
    prefix_rows = prefix.splitlines()
    if len(prefix_rows) != 5:
        raise CampaignError("attempt-001 lifecycle prefix row count changed")
    try:
        final_prefix_row = json.loads(prefix_rows[-1].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignError("attempt-001 lifecycle final row is malformed") from exc
    if (
        final_prefix_row.get("campaign_id") != FAILED_CAMPAIGN_ID
        or final_prefix_row.get("event") != "campaign_failed"
        or final_prefix_row.get("event_sha256")
        != FAILED_LIFECYCLE_LAST_EVENT_SHA256
    ):
        raise CampaignError("attempt-001 lifecycle terminal identity changed")
    failed_details = final_prefix_row.get("details") or {}
    failed_state = failed_details.get("failure_state") or {}
    pending = failed_details.get("pending_cold_child_outcome") or {}
    if (
        failed_details.get("status") != "FAILED"
        or failed_details.get("error")
        != "executor cache field drift: queued_prompt_sha256"
        or failed_details.get("completed_pair_count") != 0
        or failed_details.get("owned_server_cleanup") != {"attempted": False}
        or failed_state.get("server_pid_receipt") != 51136
        or failed_state.get("server_pid_create_time") != 1786329027.50907
        or failed_state.get("listener_pids_8199") != [51136]
        or pending.get("returncode") != 0
        or pending.get("ownership_monitor_errors")
        != [
            "CampaignError: candidate process does not have one expected ComfyUI main.py",
            "CampaignError: receipt server argv length drift: expected 16, found 20",
        ]
    ):
        raise CampaignError("attempt-001 failure diagnosis evidence changed")

    archive = campaign_layout.results / f"{control.name}_run1.json"
    alias = campaign_layout.results / f"{control.name}.json"
    archive_raw, archive_snapshot = canon.stable_file(
        archive, "attempt-001 immutable run1"
    )
    if archive_snapshot["sha256"] != FAILED_RUN1_SHA256:
        raise CampaignError("attempt-001 run1 receipt changed")
    if require_alias_run1:
        alias_raw, _ = canon.stable_file(alias, "attempt-001 current alias")
        if alias_raw != archive_raw:
            raise CampaignError("attempt-001 alias no longer equals immutable run1")
        try:
            if os.path.samefile(alias, archive):
                raise CampaignError(
                    "attempt-001 alias must not be the immutable run1 file"
                )
        except CampaignError:
            raise
        except OSError as exc:
            raise CampaignError(
                f"cannot distinguish attempt-001 alias from run1: {exc}"
            ) from exc

    old_log = failed_attempt_log_path(campaign_layout)
    _, log_snapshot = canon.stable_file(old_log, "attempt-001 Manager log")
    if log_snapshot["sha256"] != FAILED_LOG_SHA256:
        raise CampaignError("attempt-001 Manager log changed")
    verified_run1 = verify_run_receipt(
        control,
        1,
        executor_nonce(FAILED_CAMPAIGN_ID, 1, "cold"),
        sources,
        old_log,
        campaign_layout,
        role="cold",
        expected_config_run_count=1,
        require_alias_current=False,
    )
    if (
        verified_run1["receipt_sha256"] != FAILED_RUN1_SHA256
        or verified_run1["artifact"]["sha256"] != FAILED_ARTIFACT_SHA256
        or verified_run1["server_instance"]
        != {"serving_pid": 51136, "process_create_time": 1786329027.50907}
    ):
        raise CampaignError("attempt-001 run1 semantic evidence changed")
    return {
        "campaign_id": FAILED_CAMPAIGN_ID,
        "lifecycle_prefix": {
            "bytes": FAILED_LIFECYCLE_PREFIX_BYTES,
            "sha256": FAILED_LIFECYCLE_PREFIX_SHA256,
            "row_count": 5,
            "last_event_sha256": FAILED_LIFECYCLE_LAST_EVENT_SHA256,
        },
        "run1_receipt": archive_snapshot,
        "manager_log": log_snapshot,
        "artifact": verified_run1["artifact"],
        "run1_semantics": verified_run1,
        "alias_equal_run1_required": require_alias_run1,
    }


def failed_attempt_evidence_summary(evidence: Mapping[str, Any]) -> dict[str, Any]:
    semantics = evidence.get("run1_semantics") or {}
    return {
        "campaign_id": evidence.get("campaign_id"),
        "lifecycle_prefix": evidence.get("lifecycle_prefix"),
        "run1_receipt": evidence.get("run1_receipt"),
        "manager_log": evidence.get("manager_log"),
        "artifact": evidence.get("artifact"),
        "run_identity_sha256": semantics.get("run_identity_sha256"),
        "queued_prompt_sha256": semantics.get("queued_prompt_sha256"),
        "alias_equal_run1_required": evidence.get("alias_equal_run1_required"),
    }


def verify_recovery_receipt(
    sources: Mapping[str, Any],
    current_state: Mapping[str, Any],
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> dict[str, Any]:
    if (
        not isinstance(RECOVERY_RECEIPT_SHA256, str)
        or re.fullmatch(r"[0-9a-f]{64}", RECOVERY_RECEIPT_SHA256) is None
    ):
        raise CampaignError("manual cleanup recovery receipt is not SHA-pinned")
    canon.require_clean_state(current_state, "attempt-002 recovery preflight")
    path = recovery_receipt_path(campaign_layout)
    receipt, raw = canon.strict_json(path, "manual cleanup recovery receipt")
    if sha256_bytes(raw) != RECOVERY_RECEIPT_SHA256:
        raise CampaignError("manual cleanup recovery receipt SHA drift")
    required = {
        "receipt_schema_version": 1,
        "receipt_kind": "h3-unconditioned-music-manual-cleanup-recovery",
        "recovery_id": RECOVERY_ID,
        "failed_campaign_id": FAILED_CAMPAIGN_ID,
        "status": "ATTEMPT_001_FAILED_COLD_ONLY_MANUAL_CLEANUP_RECORDED",
        "success": True,
    }
    for field, expected in required.items():
        if receipt.get(field) != expected:
            raise CampaignError(f"manual cleanup recovery field drift: {field}")
    recorded_at_ns = receipt.get("recorded_at_ns")
    if (
        not isinstance(recorded_at_ns, int)
        or isinstance(recorded_at_ns, bool)
        or recorded_at_ns <= 0
        or not isinstance(receipt.get("recorded_at_utc"), str)
        or not receipt["recorded_at_utc"].endswith("Z")
    ):
        raise CampaignError("manual cleanup recovery timestamp is invalid")

    immutable = receipt.get("immutable_evidence") or {}
    lifecycle = immutable.get("lifecycle") or {}
    prefix = lifecycle.get("prefix") or {}
    terminal = (lifecycle.get("terminal_failure") or {})
    run1 = immutable.get("run1_receipt") or {}
    alias = immutable.get("alias") or {}
    old_log = immutable.get("server_log") or {}
    artifact = immutable.get("artifact") or {}
    if (
        prefix
        != {
            "bytes": FAILED_LIFECYCLE_PREFIX_BYTES,
            "sha256": FAILED_LIFECYCLE_PREFIX_SHA256,
            "row_count": 5,
            "last_event_sha256": FAILED_LIFECYCLE_LAST_EVENT_SHA256,
        }
        or terminal.get("status") != "FAILED"
        or terminal.get("error")
        != "executor cache field drift: queued_prompt_sha256"
        or terminal.get("completed_pair_count") != 0
        or run1.get("sha256") != FAILED_RUN1_SHA256
        or run1.get("bytes") != 63_281
        or alias.get("sha256") != FAILED_RUN1_SHA256
        or alias.get("byte_equal_to_run1") is not True
        or old_log.get("sha256") != FAILED_LOG_SHA256
        or old_log.get("bytes") != 22_947
        or artifact.get("sha256") != FAILED_ARTIFACT_SHA256
        or artifact.get("bytes") != 909_151
        or immutable.get("server_identity_from_run1")
        != {"serving_pid": 51136, "process_create_time": 1786329027.50907}
        or (immutable.get("run1_disposition") or {}).get("warm_pass") is not False
        or (immutable.get("run1_disposition") or {}).get("completed_pair") is not False
    ):
        raise CampaignError("manual cleanup recovery immutable evidence drift")
    if receipt.get("failed_incident") != terminal:
        raise CampaignError("manual cleanup recovery incident copy drift")

    operator = receipt.get("operator_captured_cleanup") or {}
    exact_shutdown = {
        "had_receipt": True,
        "listener_exited": True,
        "pid": 51136,
        "pid_verified": True,
        "process_exited": True,
        "reason": "verified server process and listener exited",
        "receipt_removed": True,
        "success": True,
        "termination_attempted": True,
        "termination_reported_success": True,
    }
    if (
        "operator capture" not in str(operator.get("authority"))
        or operator.get("capture_timestamp") is not None
        or operator.get("capture_timestamp_status")
        != "not present in the operator capture"
        or operator.get("server_identity_from_immutable_run1")
        != {"serving_pid": 51136, "process_create_time": 1786329027.50907}
        or operator.get("shutdown_lab_server_return") != exact_shutdown
        or operator.get("console_lines")
        != [
            "[SERVER] Shutting down verified lab server (PID 51136)...",
            "[SERVER] Process 51136 and listener exited; removed .server.pid receipt.",
        ]
    ):
        raise CampaignError("operator-captured manual cleanup evidence drift")

    if receipt.get("current_clean_state") != dict(current_state):
        raise CampaignError("recorded cleanup postconditions differ from current state")
    clean_evidence = receipt.get("current_clean_state_evidence") or {}
    if (
        clean_evidence.get("authority") != "machine-observed at receipt recording"
        or clean_evidence.get("recorded_at_ns") != recorded_at_ns
        or clean_evidence.get("shape")
        != "scratch.run_h3_canonical_campaign.runtime_state"
        or clean_evidence.get("expected_server_identity")
        != {"serving_pid": 51136, "process_create_time": 1786329027.50907}
        or clean_evidence.get("http_or_comfyui_query_performed") is not False
        or (clean_evidence.get("coordinator_guard") or {}).get(
            "acquired_nonblocking"
        )
        is not True
    ):
        raise CampaignError("manual cleanup current-state evidence drift")

    source_map = receipt.get("source_sha256s") or {}
    expected_sources = {
        "recorder": "recovery_recorder",
        "canonical_campaign_helper": "campaign_canonical",
        "run_recipe": "runner",
        "lab_locks": "lab_locks",
        "manager_guard": "manager_guard",
    }
    if set(source_map) != set(expected_sources):
        raise CampaignError("manual cleanup recovery source set drift")
    for receipt_label, campaign_label in expected_sources.items():
        recorded = source_map.get(receipt_label) or {}
        current = sources.get(campaign_label) or {}
        if (
            recorded.get("sha256") != current.get("sha256")
            or recorded.get("bytes") != current.get("bytes")
        ):
            raise CampaignError(
                f"manual cleanup recovery source drift: {receipt_label}"
            )
    anti_circularity = receipt.get("anti_circularity") or {}
    if (
        anti_circularity.get("main_music_campaign_source_included") is not False
        or anti_circularity.get("receipt_is_resume_authority_without_external_sha_pin")
        is not False
    ):
        raise CampaignError("manual cleanup recovery anti-circularity drift")

    certification = receipt.get("certification_effect") or {}
    if certification != {
        "attempt_001_status": "FAILED",
        "run1_is_valid_cold_evidence": True,
        "run1_is_warm_evidence": False,
        "completed_pair_count": 0,
        "normal_runner_shutdown_proved": False,
        "manual_cleanup_is_operator_captured": True,
        "current_postconditions_are_machine_verified": True,
        "promotion_or_pass_granted": False,
    }:
        raise CampaignError("manual cleanup recovery certification effect drift")
    policy = receipt.get("recovery_policy") or {}
    if (
        policy.get("resume_campaign_id") != RESUME_CAMPAIGN_ID
        or policy.get("pair_index") != 1
        or policy.get("preserve_run1_immutable") is not True
        or policy.get("run1_may_not_pair_with_a_later_warm_run") is not True
        or policy.get("run2")
        != {
            "run_number": 2,
            "config_run_count": 1,
            "role": "cold",
            "new_server_identity_required": True,
        }
        or policy.get("run3")
        != {
            "run_number": 3,
            "config_run_count": 2,
            "role": "warm",
            "must_immediately_follow": "run2",
            "same_server_identity_as": "run2",
            "shutdown_required": True,
        }
    ):
        raise CampaignError("manual cleanup recovery resume policy drift")
    safety = receipt.get("safety") or {}
    if safety != {
        "failed_lifecycle_appended_or_rewritten": False,
        "artifact_or_run_receipt_modified": False,
        "foreign_server_adopted_or_killed_by_recorder": False,
        "prompt_or_render_submitted_by_recorder": False,
        "network_used_by_recorder": False,
    }:
        raise CampaignError("manual cleanup recovery safety claims drift")
    return {
        "path": str(path.resolve()),
        "bytes": len(raw),
        "sha256": RECOVERY_RECEIPT_SHA256,
        "recovery_id": RECOVERY_ID,
        "recorded_at_ns": recorded_at_ns,
        "operator_capture_only": True,
        "current_postconditions_reverified": True,
        "resume_policy": policy,
    }


def verify_final_log(
    log_path: Path, argv: Sequence[str]
) -> dict[str, Any]:
    scan = manager_guard.scan_log(
        log_path,
        argv,
        expected_url="http://127.0.0.1:8199",
        require_pre_prompt=False,
    )
    errors = manager_guard.validate_scan_binding(scan, log_path, argv)
    if errors:
        raise CampaignError(f"final Manager log audit failed: {errors}")
    if not scan.get("execution_markers"):
        raise CampaignError("final Manager log has no prompt execution evidence")
    return scan


def verify_pair(
    spec: canon.RecipeSpec,
    pair_index: int,
    campaign_id: str,
    sources: Mapping[str, Any],
    log_path: Path,
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
    cold_snapshot: Mapping[str, Any] | None = None,
    *,
    cold_run_number: int = 1,
    cold_config_run_count: int = 1,
    warm_run_number: int = 2,
    warm_config_run_count: int = 2,
    allowed_run_numbers: Sequence[int] = (1, 2),
    expected_completion_timeout_s: int | None = None,
    cold_artifact_index: int | None = None,
    warm_artifact_index: int | None = None,
    allowed_artifact_indices: Sequence[int] | None = None,
) -> dict[str, Any]:
    if (
        any(
            not isinstance(number, int)
            or isinstance(number, bool)
            or number < 1
            for number in allowed_run_numbers
        )
        or len(set(allowed_run_numbers)) != len(allowed_run_numbers)
        or cold_run_number not in allowed_run_numbers
        or warm_run_number not in allowed_run_numbers
        or cold_run_number >= warm_run_number
    ):
        raise CampaignError("pair receipt schedule is invalid")
    if cold_artifact_index is None:
        cold_artifact_index = cold_run_number
    if warm_artifact_index is None:
        warm_artifact_index = warm_run_number
    if allowed_artifact_indices is None:
        allowed_artifact_indices = tuple(allowed_run_numbers)
    if (
        any(
            not isinstance(number, int)
            or isinstance(number, bool)
            or number < 1
            for number in allowed_artifact_indices
        )
        or len(set(allowed_artifact_indices)) != len(allowed_artifact_indices)
        or cold_artifact_index not in allowed_artifact_indices
        or warm_artifact_index not in allowed_artifact_indices
        or cold_artifact_index >= warm_artifact_index
    ):
        raise CampaignError("pair artifact schedule is invalid")
    cold = verify_run_receipt(
        spec,
        cold_run_number,
        executor_nonce(campaign_id, pair_index, "cold"),
        sources,
        log_path,
        campaign_layout,
        role="cold",
        expected_config_run_count=cold_config_run_count,
        expected_completion_timeout_s=expected_completion_timeout_s,
        expected_artifact_index=cold_artifact_index,
        require_alias_current=False,
    )
    warm = verify_run_receipt(
        spec,
        warm_run_number,
        executor_nonce(campaign_id, pair_index, "warm"),
        sources,
        log_path,
        campaign_layout,
        role="warm",
        expected_config_run_count=warm_config_run_count,
        expected_completion_timeout_s=expected_completion_timeout_s,
        expected_artifact_index=warm_artifact_index,
    )
    for field in ("run_identity_sha256", "identity", "server_instance", "server_argv"):
        if cold[field] != warm[field]:
            raise CampaignError(f"cold/warm {field} changed")
    if cold["queued_prompt_sha256"] == warm["queued_prompt_sha256"]:
        raise CampaignError("unique executor nonces did not change queued prompt")
    if cold_snapshot is not None:
        for field in ("receipt_sha256", "artifact"):
            if cold.get(field) != cold_snapshot.get(field):
                raise CampaignError(f"cold evidence changed after warm: {field}")
    final_log = verify_final_log(log_path, warm["server_argv"])
    allowed_receipts = {
        f"{spec.name}_run{number}.json" for number in allowed_run_numbers
    }
    extra_receipts = [
        path.name
        for path in campaign_layout.results.iterdir()
        if path.name.startswith(f"{spec.name}_run")
        and path.name not in allowed_receipts
    ]
    allowed_outputs = {
        f"{spec.prefix}_{number:05d}_.mp4" for number in allowed_artifact_indices
    }
    extra_outputs = [
        path.name
        for path in campaign_layout.outputs.iterdir()
        if path.name.startswith(spec.prefix) and path.name not in allowed_outputs
    ]
    if extra_receipts or extra_outputs:
        raise CampaignError(
            f"unexpected evidence for {spec.name}: "
            f"receipts={extra_receipts}, outputs={extra_outputs}"
        )
    return {"cold": cold, "warm": warm, "final_manager_log": final_log}


def _require_pinned_file(
    path: Path,
    label: str,
    expected_bytes: int,
    expected_sha256: str,
) -> tuple[bytes, dict[str, Any]]:
    raw, snapshot = canon.stable_file(path, label)
    if len(raw) != expected_bytes or sha256_bytes(raw) != expected_sha256:
        raise CampaignError(f"immutable {label} pin drifted")
    return raw, snapshot


def verify_attempt2_lifecycle_prefix(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> dict[str, Any]:
    raw, _ = canon.stable_file(
        campaign_layout.lifecycle, "attempt-002 lifecycle prefix"
    )
    if len(raw) < ATTEMPT2_LIFECYCLE_PREFIX_BYTES:
        raise CampaignError("attempt-002 lifecycle prefix was truncated")
    prefix = raw[:ATTEMPT2_LIFECYCLE_PREFIX_BYTES]
    if (
        sha256_bytes(prefix) != ATTEMPT2_LIFECYCLE_PREFIX_SHA256
        or not prefix.endswith(b"\n")
    ):
        raise CampaignError("attempt-002 lifecycle prefix pin drifted")
    lines = prefix.splitlines()
    if len(lines) != 13:
        raise CampaignError("attempt-002 lifecycle prefix must contain thirteen rows")
    previous = None
    records: list[dict[str, Any]] = []
    for ledger_sequence, (line, expected) in enumerate(
        zip(lines, ATTEMPT2_EXPECTED_LIFECYCLE_ROWS, strict=True), start=1
    ):
        try:
            row = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CampaignError(
                f"attempt-002 lifecycle row {ledger_sequence} is malformed"
            ) from exc
        if not isinstance(row, dict):
            raise CampaignError("attempt-002 lifecycle row is not an object")
        body = dict(row)
        digest = body.pop("event_sha256", None)
        if digest != sha256_bytes(canon.canonical_bytes(body)):
            raise CampaignError("attempt-002 lifecycle canonical event SHA drifted")
        campaign_id, event, campaign_sequence, event_sha = expected
        if (
            row.get("ledger_sequence") != ledger_sequence
            or row.get("campaign_id") != campaign_id
            or row.get("campaign_sequence") != campaign_sequence
            or row.get("event") != event
            or digest != event_sha
            or row.get("previous_event_sha256") != previous
        ):
            raise CampaignError(
                f"attempt-002 lifecycle row {ledger_sequence} identity/chain drifted"
            )
        previous = digest
        records.append(row)
    terminal = records[-1].get("details") or {}
    if terminal != {
        "status": "FAILED",
        "error_type": "CampaignError",
        "error": f"{CELL_PINS[0][0]} warm child returned 120",
        "completed_pair_count": 0,
        "failure_state": {
            "gpu_lock_exists": False,
            "suite_lock_exists": False,
            "server_pid_receipt_exists": False,
            "server_pid_receipt": None,
            "server_pid_create_time": None,
            "queue_quarantine_exists": False,
            "listener_pids_8199": [],
            "expected_server_identity_live": False,
        },
        "pending_cold_child_outcome": None,
        "owned_server_cleanup": {"attempted": False},
        "stopped_without_force_or_additional_render": True,
    }:
        raise CampaignError("attempt-002 terminal failure evidence drifted")
    sources = (records[6].get("details") or {}).get("sources")
    if not isinstance(sources, dict):
        raise CampaignError("attempt-002 lifecycle source evidence is absent")
    return {
        "prefix": {
            "path": str(campaign_layout.lifecycle.resolve()),
            "bytes": ATTEMPT2_LIFECYCLE_PREFIX_BYTES,
            "sha256": ATTEMPT2_LIFECYCLE_PREFIX_SHA256,
            "row_count": 13,
            "last_event_sha256": ATTEMPT2_LIFECYCLE_LAST_EVENT_SHA256,
            "hash_chain_verified": True,
        },
        "sources": sources,
        "terminal": {
            "status": "FAILED",
            "error": terminal["error"],
            "completed_pair_count": 0,
            "warm_child_returncode": 120,
            "exit_120_cause": "UNKNOWN_UNPROVED",
        },
    }


def verify_attempt2_preserved_evidence(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> dict[str, Any]:
    """Rehash attempts 1/2, both recoveries, and the recovered pair 1."""

    lifecycle = verify_attempt2_lifecycle_prefix(campaign_layout)
    historical_sources = lifecycle["sources"]
    recovery2_path = attempt2_recovery_receipt_path(campaign_layout)
    recovery2, recovery2_raw = canon.strict_json(
        recovery2_path, "attempt-002 recovery receipt"
    )
    if (
        len(recovery2_raw) != ATTEMPT2_RECOVERY_RECEIPT_BYTES
        or sha256_bytes(recovery2_raw) != ATTEMPT2_RECOVERY_RECEIPT_SHA256
    ):
        raise CampaignError("attempt-002 recovery receipt literal pin drifted")
    required = {
        "receipt_schema_version": 1,
        "receipt_kind": "h3-unconditioned-music-attempt-002-return120-recovery",
        "recovery_id": ATTEMPT2_RECOVERY_ID,
        "failed_campaign_id": RESUME_CAMPAIGN_ID,
        "status": "ATTEMPT_002_FAILED_PAIR1_MACHINE_RECOVERED",
        "success": True,
    }
    for field, expected in required.items():
        if recovery2.get(field) != expected:
            raise CampaignError(f"attempt-002 recovery field drifted: {field}")
    immutable = recovery2.get("immutable_evidence") or {}
    recorded_prefix = ((immutable.get("lifecycle") or {}).get("current_prefix") or {})
    if recorded_prefix != {
        "path": LIFECYCLE.relative_to(ROOT).as_posix(),
        "bytes": ATTEMPT2_LIFECYCLE_PREFIX_BYTES,
        "sha256": ATTEMPT2_LIFECYCLE_PREFIX_SHA256,
        "row_count": 13,
        "last_event_sha256": ATTEMPT2_LIFECYCLE_LAST_EVENT_SHA256,
        "hash_chain_verified": True,
    }:
        raise CampaignError("attempt-002 recovery lifecycle binding drifted")
    certification = recovery2.get("certification_effect") or {}
    if certification != {
        "attempt_002_status": "FAILED",
        "attempt_002_ledger_completed_pair_count": 0,
        "pair1_machine_pair_recoverable_and_complete": True,
        "pair1_completion_basis_is_full_final_verifier_only": True,
        "human_judgment": "PENDING",
        "exit_120_cause": "UNKNOWN_UNPROVED",
        "current_postconditions_are_machine_verified": True,
        "promotion_or_study_pass_granted": False,
    }:
        raise CampaignError("attempt-002 recovery certification drifted")
    policy = recovery2.get("recovery_policy") or {}
    if (
        policy.get("resume_campaign_id") != RESUME_ATTEMPT2_CAMPAIGN_ID
        or policy.get("skip_pair_indices") != [1]
        or policy.get("next_pair_index") != 2
        or policy.get("remaining_pair_indices") != list(range(2, 12))
        or policy.get("remaining_pair_count") != 10
        or policy.get("executions_per_pair") != 2
        or policy.get("remaining_execution_count") != 20
    ):
        raise CampaignError("attempt-002 recovery policy drifted")
    incident = recovery2.get("failed_incident") or {}
    exit_cause = incident.get("exit_120_cause") or {}
    if (
        incident.get("status") != "FAILED"
        or incident.get("completed_pair_count") != 0
        or incident.get("warm_child_returncode") != 120
        or exit_cause.get("classification") != "UNKNOWN_UNPROVED"
        or exit_cause.get("causal_claim_asserted") is not False
    ):
        raise CampaignError("attempt-002 recovery incident truthfulness drifted")

    expected_source_pins = {
        "attempt1_recovery_receipt": (7_610, RECOVERY_RECEIPT_SHA256),
        "attempt1_recovery_recorder": (
            27_204,
            "7ecc98fa6a9157a1080406d556f0b1df055b0ac00f89367753bbe421c7a84b38",
        ),
        "attempt2_campaign": (
            ATTEMPT2_CAMPAIGN_SOURCE_BYTES,
            ATTEMPT2_CAMPAIGN_SOURCE_SHA256,
        ),
        "canonical_campaign_helper": (
            77_526,
            "0c3246a435d0c9f208ecbca4bc77b172e2a1e3793cbb96332a2e41781fd5cb38",
        ),
        "lab_locks": (
            19_611,
            "0200e8620558fe3a7ddf75bf54678439905d6041a65d1c06bd2b2ba01def0ff1",
        ),
        "manager_guard": (
            39_609,
            "1b06e5662e9bad8d17aac05d31e393683f3cd450dadbeb86c3763c3a47b2a821",
        ),
        "recorder": (
            ATTEMPT2_RECOVERY_RECORDER_BYTES,
            ATTEMPT2_RECOVERY_RECORDER_SHA256,
        ),
        "run_recipe": (
            174_954,
            "938c72ad5b4cb6565804dde85222103707be67c410b4affec766b6fc9ed7acad",
        ),
    }
    source_map = recovery2.get("source_sha256s") or {}
    if set(source_map) != set(expected_source_pins):
        raise CampaignError("attempt-002 recovery source set drifted")
    for label, (expected_bytes, expected_sha) in expected_source_pins.items():
        recorded = source_map.get(label) or {}
        if (
            recorded.get("bytes") != expected_bytes
            or recorded.get("sha256") != expected_sha
        ):
            raise CampaignError(f"attempt-002 recovery source drifted: {label}")

    control = load_specs(campaign_layout)[0]
    fixed_files = {
        "attempt-001 recovery receipt": (
            recovery_receipt_path(campaign_layout),
            7_610,
            str(RECOVERY_RECEIPT_SHA256),
        ),
        "attempt-002 recovery recorder": (
            ATTEMPT2_RECOVERY_RECORDER,
            ATTEMPT2_RECOVERY_RECORDER_BYTES,
            ATTEMPT2_RECOVERY_RECORDER_SHA256,
        ),
        "attempt-001 run1": (
            campaign_layout.results / f"{control.name}_run1.json",
            63_281,
            FAILED_RUN1_SHA256,
        ),
        "attempt-002 run2": (
            campaign_layout.results / f"{control.name}_run2.json",
            63_350,
            ATTEMPT2_RUN2_SHA256,
        ),
        "attempt-002 run3": (
            campaign_layout.results / f"{control.name}_run3.json",
            64_162,
            ATTEMPT2_RUN3_SHA256,
        ),
        "attempt-002 alias": (
            campaign_layout.results / f"{control.name}.json",
            64_162,
            ATTEMPT2_RUN3_SHA256,
        ),
        "attempt-002 Manager log": (
            attempt2_pair_log_path(campaign_layout),
            25_081,
            ATTEMPT2_LOG_SHA256,
        ),
    }
    snapshots = {}
    for label, (path, expected_bytes, expected_sha) in fixed_files.items():
        _, snapshots[label] = _require_pinned_file(
            path, label, expected_bytes, expected_sha
        )
    receipt_paths = [
        campaign_layout.results / f"{control.name}_run1.json",
        campaign_layout.results / f"{control.name}_run2.json",
        campaign_layout.results / f"{control.name}_run3.json",
        campaign_layout.results / f"{control.name}.json",
    ]
    for left_index, left in enumerate(receipt_paths):
        for right in receipt_paths[left_index + 1 :]:
            try:
                if os.path.samefile(left, right):
                    raise CampaignError("attempt-002 pair receipts/alias are hardlinked")
            except CampaignError:
                raise
            except OSError as exc:
                raise CampaignError("cannot prove attempt-002 receipt independence") from exc

    artifacts = []
    for run_number in (1, 2, 3):
        path = campaign_layout.outputs / f"{control.prefix}_{run_number:05d}_.mp4"
        _, snapshot = _require_pinned_file(
            path,
            f"attempt pair1 artifact run{run_number}",
            909_151,
            FAILED_ARTIFACT_SHA256,
        )
        artifacts.append((path, snapshot))
    for left_index, (left, _) in enumerate(artifacts):
        for right, _ in artifacts[left_index + 1 :]:
            try:
                if os.path.samefile(left, right):
                    raise CampaignError("attempt-002 pair artifacts are hardlinked")
            except CampaignError:
                raise
            except OSError as exc:
                raise CampaignError("cannot prove attempt-002 artifact independence") from exc

    preserved_attempt1 = verify_failed_attempt_evidence(
        historical_sources,
        campaign_layout,
        require_alias_run1=False,
    )
    schedule = pair_run_schedule(1, False, True)
    pair = verify_pair(
        control,
        1,
        RESUME_CAMPAIGN_ID,
        historical_sources,
        attempt2_pair_log_path(campaign_layout),
        campaign_layout,
        cold_run_number=schedule["cold_run_number"],
        cold_config_run_count=schedule["cold_config_run_count"],
        warm_run_number=schedule["warm_run_number"],
        warm_config_run_count=schedule["warm_config_run_count"],
        allowed_run_numbers=schedule["allowed_run_numbers"],
    )
    if sha256_bytes(canon.canonical_bytes(pair)) != ATTEMPT2_PAIR_RESULT_SHA256:
        raise CampaignError("attempt-002 full pair verifier result drifted")
    pair_receipt = recovery2.get("pair1_machine_verification") or {}
    full = pair_receipt.get("full_final_verifier") or {}
    if (
        pair_receipt.get("status") != "RECOVERABLE_COMPLETE"
        or pair_receipt.get("human_judgment") != "PENDING"
        or pair_receipt.get("promotion_granted") is not False
        or full.get("canonical_result_sha256") != ATTEMPT2_PAIR_RESULT_SHA256
        or (full.get("cold") or {}).get("receipt_sha256")
        != pair["cold"]["receipt_sha256"]
        or (full.get("warm") or {}).get("receipt_sha256")
        != pair["warm"]["receipt_sha256"]
        or (full.get("final_manager_log") or {}).get("sha256")
        != pair["final_manager_log"]["log"]["sha256"]
    ):
        raise CampaignError("attempt-002 recovery/full verifier binding drifted")
    if (
        pair["cold"]["server_instance"] != ATTEMPT2_SERVER_IDENTITY
        or pair["warm"]["server_instance"] != ATTEMPT2_SERVER_IDENTITY
        or pair["cold"]["run_identity_sha256"] != ATTEMPT2_RUN_IDENTITY_SHA256
        or pair["warm"]["run_identity_sha256"] != ATTEMPT2_RUN_IDENTITY_SHA256
        or pair["cold"]["queued_prompt_sha256"] != ATTEMPT2_COLD_QUEUED_SHA256
        or pair["warm"]["queued_prompt_sha256"] != ATTEMPT2_WARM_QUEUED_SHA256
    ):
        raise CampaignError("attempt-002 recovered pair identity drifted")
    return {
        "lifecycle": lifecycle,
        "attempt2_sources": historical_sources,
        "attempt1": preserved_attempt1,
        "recovery2": {
            "path": str(recovery2_path.resolve()),
            "bytes": len(recovery2_raw),
            "sha256": ATTEMPT2_RECOVERY_RECEIPT_SHA256,
            "recovery_id": ATTEMPT2_RECOVERY_ID,
        },
        "recovery1": snapshots["attempt-001 recovery receipt"],
        "pair": pair,
        "receipt_schedule": schedule,
        "pair1_human_judgment": "PENDING",
        "attempt2_status": "FAILED",
        "attempt2_ledger_completed_pair_count": 0,
        "orphan_historical_cold_count": 1,
    }


def verify_attempt2_recovery_receipt(
    current_sources: Mapping[str, Any],
    current_state: Mapping[str, Any],
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> dict[str, Any]:
    canon.require_clean_state(current_state, "attempt-003 recovery preflight")
    lifecycle_raw, _ = canon.stable_file(
        campaign_layout.lifecycle, "attempt-003 starting lifecycle"
    )
    if len(lifecycle_raw) != ATTEMPT2_LIFECYCLE_PREFIX_BYTES:
        raise CampaignError(
            "attempt-003 must begin immediately after the exact thirteen-row "
            "attempt-002 lifecycle"
        )
    preserved = verify_attempt2_preserved_evidence(campaign_layout)
    recovery2, _ = canon.strict_json(
        attempt2_recovery_receipt_path(campaign_layout),
        "attempt-002 recovery receipt",
    )
    if recovery2.get("current_clean_state") != dict(current_state):
        raise CampaignError("attempt-002 recovery clean-state binding drifted")
    if (
        (current_sources.get("attempt2_recovery_recorder") or {}).get("sha256")
        != ATTEMPT2_RECOVERY_RECORDER_SHA256
        or (current_sources.get("attempt2_recovery_receipt") or {}).get("sha256")
        != ATTEMPT2_RECOVERY_RECEIPT_SHA256
    ):
        raise CampaignError("attempt-003 source set does not pin recovery-002")
    preserved["recovery1_verification"] = verify_recovery_receipt(
        preserved["attempt2_sources"],
        current_state,
        campaign_layout,
    )
    return preserved


def attempt2_evidence_summary(evidence: Mapping[str, Any]) -> dict[str, Any]:
    pair = evidence.get("pair") or {}
    cold = pair.get("cold") or {}
    warm = pair.get("warm") or {}
    final_log = (pair.get("final_manager_log") or {}).get("log") or {}
    lifecycle = evidence.get("lifecycle") or {}
    return {
        "source_campaign_id": RESUME_CAMPAIGN_ID,
        "attempt2_status": evidence.get("attempt2_status"),
        "attempt2_ledger_completed_pair_count": evidence.get(
            "attempt2_ledger_completed_pair_count"
        ),
        "lifecycle_prefix": lifecycle.get("prefix"),
        "recovery1": evidence.get("recovery1"),
        "recovery2": evidence.get("recovery2"),
        "cold_receipt_sha256": cold.get("receipt_sha256"),
        "warm_receipt_sha256": warm.get("receipt_sha256"),
        "cold_artifact_sha256": (cold.get("artifact") or {}).get("sha256"),
        "warm_artifact_sha256": (warm.get("artifact") or {}).get("sha256"),
        "manager_log_sha256": final_log.get("sha256"),
        "run_identity_sha256": cold.get("run_identity_sha256"),
        "server_instance": cold.get("server_instance"),
        "receipt_schedule": evidence.get("receipt_schedule"),
        "pair1_machine_status": "RECOVERABLE_COMPLETE",
        "pair1_human_judgment": evidence.get("pair1_human_judgment"),
        "orphan_historical_cold_count": evidence.get(
            "orphan_historical_cold_count"
        ),
    }


def verify_attempt3_lifecycle_prefix(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> dict[str, Any]:
    raw, _ = canon.stable_file(
        campaign_layout.lifecycle, "attempt-003 lifecycle prefix"
    )
    if len(raw) < ATTEMPT3_LIFECYCLE_PREFIX_BYTES:
        raise CampaignError("attempt-003 lifecycle prefix was truncated")
    prefix = raw[:ATTEMPT3_LIFECYCLE_PREFIX_BYTES]
    if (
        sha256_bytes(prefix) != ATTEMPT3_LIFECYCLE_PREFIX_SHA256
        or not prefix.endswith(b"\n")
    ):
        raise CampaignError("attempt-003 lifecycle prefix pin drifted")
    lines = prefix.splitlines()
    if len(lines) != 22:
        raise CampaignError("attempt-003 lifecycle prefix must contain 22 rows")
    previous = None
    records: list[dict[str, Any]] = []
    expected_campaigns = (
        [FAILED_CAMPAIGN_ID] * 5
        + [RESUME_CAMPAIGN_ID] * 8
        + [RESUME_ATTEMPT2_CAMPAIGN_ID] * 9
    )
    expected_events = (
        [
            "campaign_started",
            "campaign_preflight_passed",
            "pair_started",
            "cold_child_returned",
            "campaign_failed",
        ]
        + [
            "recovery_started",
            "campaign_started",
            "campaign_preflight_passed",
            "pair_started",
            "cold_child_returned",
            "cold_verified",
            "warm_shutdown_child_returned",
            "campaign_failed",
        ]
        + [
            "recovery_started",
            "campaign_started",
            "campaign_preflight_passed",
            "pair_carried_forward",
            "pair_started",
            "cold_child_returned",
            "cold_verified",
            "warm_shutdown_child_returned",
            "campaign_failed",
        ]
    )
    campaign_sequences = {FAILED_CAMPAIGN_ID: 0, RESUME_CAMPAIGN_ID: 0, RESUME_ATTEMPT2_CAMPAIGN_ID: 0}
    for ledger_sequence, line in enumerate(lines, start=1):
        try:
            row = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CampaignError("attempt-003 lifecycle row is malformed") from exc
        if not isinstance(row, dict):
            raise CampaignError("attempt-003 lifecycle row is not an object")
        body = dict(row)
        digest = body.pop("event_sha256", None)
        campaign_name = expected_campaigns[ledger_sequence - 1]
        campaign_sequences[campaign_name] += 1
        if (
            digest != sha256_bytes(canon.canonical_bytes(body))
            or row.get("ledger_sequence") != ledger_sequence
            or row.get("campaign_id") != campaign_name
            or row.get("campaign_sequence") != campaign_sequences[campaign_name]
            or row.get("event") != expected_events[ledger_sequence - 1]
            or row.get("previous_event_sha256") != previous
        ):
            raise CampaignError("attempt-003 lifecycle identity/hash chain drifted")
        previous = digest
        records.append(row)
    if previous != ATTEMPT3_LIFECYCLE_LAST_EVENT_SHA256:
        raise CampaignError("attempt-003 lifecycle terminal SHA drifted")
    terminal = records[-1].get("details") or {}
    if (
        terminal.get("status") != "FAILED"
        or terminal.get("error_type") != "CampaignError"
        or terminal.get("error")
        != f"{CELL_PINS[1][0]} post-shutdown is not clean: server_pid_receipt_exists=True"
        or terminal.get("completed_pair_count") != 1
        or terminal.get("carried_pair_count") != 1
        or terminal.get("new_verified_pair_count") != 0
        or terminal.get("owned_server_cleanup") != {"attempted": False}
    ):
        raise CampaignError("attempt-003 terminal failure evidence drifted")
    failure_state = terminal.get("failure_state") or {}
    if (
        failure_state.get("server_pid_receipt_exists") is not True
        or failure_state.get("server_pid_receipt") != 19_256
        or failure_state.get("server_pid_create_time") is not None
        or failure_state.get("listener_pids_8199") != []
        or failure_state.get("expected_server_identity_live") is not False
        or failure_state.get("gpu_lock_exists") is not False
        or failure_state.get("suite_lock_exists") is not False
        or failure_state.get("queue_quarantine_exists") is not False
    ):
        raise CampaignError("attempt-003 terminal stale-receipt state drifted")
    sources = (records[14].get("details") or {}).get("sources")
    if not isinstance(sources, dict):
        raise CampaignError("attempt-003 lifecycle source evidence is absent")
    return {
        "prefix": {
            "path": str(campaign_layout.lifecycle.resolve()),
            "bytes": ATTEMPT3_LIFECYCLE_PREFIX_BYTES,
            "sha256": ATTEMPT3_LIFECYCLE_PREFIX_SHA256,
            "row_count": 22,
            "last_event_sha256": ATTEMPT3_LIFECYCLE_LAST_EVENT_SHA256,
            "hash_chain_verified": True,
        },
        "sources": sources,
        "terminal": {
            "status": "FAILED",
            "error": terminal["error"],
            "completed_pair_count": 1,
            "carried_pair_count": 1,
            "pair2_machine_recoverable": True,
        },
    }


def verify_attempt3_preserved_evidence(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> dict[str, Any]:
    lifecycle = verify_attempt3_lifecycle_prefix(campaign_layout)
    historical_sources = lifecycle["sources"]
    recovery_path = attempt3_recovery_receipt_path(campaign_layout)
    recovery3, recovery_raw = canon.strict_json(
        recovery_path, "attempt-003 stale-PID recovery receipt"
    )
    if (
        len(recovery_raw) != ATTEMPT3_RECOVERY_RECEIPT_BYTES
        or sha256_bytes(recovery_raw) != ATTEMPT3_RECOVERY_RECEIPT_SHA256
    ):
        raise CampaignError("attempt-003 recovery receipt literal pin drifted")
    required = {
        "receipt_schema_version": 1,
        "receipt_kind": "h3-unconditioned-music-attempt-003-stale-pid-recovery",
        "failed_campaign_id": RESUME_ATTEMPT2_CAMPAIGN_ID,
        "resume_campaign_id": RESUME_ATTEMPT3_CAMPAIGN_ID,
        "status": "ATTEMPT_003_FAILED_PAIR2_MACHINE_RECOVERED",
        "success": True,
    }
    for field, expected in required.items():
        if recovery3.get(field) != expected:
            raise CampaignError(f"attempt-003 recovery field drifted: {field}")
    policy = recovery3.get("recovery_policy") or {}
    cleanup_policy = policy.get("stale_receipt_cleanup") or {}
    if (
        policy.get("carry_pair_indices") != [1, 2]
        or policy.get("execute_pair_indices") != list(range(3, 12))
        or policy.get("next_pair_index") != 3
        or policy.get("remaining_pair_count") != 9
        or policy.get("remaining_execution_count") != 18
        or cleanup_policy.get("performed_by_this_recorder") is not False
        or cleanup_policy.get("operator_must_match_exact_bytes_and_sha256") is not True
        or cleanup_policy.get("operator_must_independently_reprove_pid_dead_and_listener_absent") is not True
        or cleanup_policy.get("attempt004_must_start_from_clean_state") is not True
    ):
        raise CampaignError("attempt-003 recovery policy drifted")
    incident = recovery3.get("incident_classification") or {}
    if (
        incident.get("classification")
        != "EXPECTED_SERVER_EXITED_STALE_PID_RECEIPT_UNLINK_FAILED"
        or incident.get("warm_child_returncode") != 0
        or incident.get("owned_server_pid") != 19_256
        or incident.get("lifecycle_post_child_listener_pids_8199") != []
        or incident.get("lifecycle_post_child_expected_server_identity_live") is not False
        or incident.get("ambiguous_live_server") is not False
    ):
        raise CampaignError("attempt-003 incident classification drifted")
    immutable = recovery3.get("immutable_evidence") or {}
    prefix = ((immutable.get("lifecycle") or {}).get("prefix") or {})
    if (
        prefix.get("bytes") != ATTEMPT3_LIFECYCLE_PREFIX_BYTES
        or prefix.get("sha256") != ATTEMPT3_LIFECYCLE_PREFIX_SHA256
        or prefix.get("last_event_sha256") != ATTEMPT3_LIFECYCLE_LAST_EVENT_SHA256
    ):
        raise CampaignError("attempt-003 recovery lifecycle binding drifted")

    fixed_files = {
        "pair2 cold": (
            campaign_layout.results / f"{CELL_PINS[1][0]}_run1.json",
            63_402,
            ATTEMPT3_PAIR2_COLD_SHA256,
        ),
        "pair2 warm": (
            campaign_layout.results / f"{CELL_PINS[1][0]}_run2.json",
            64_214,
            ATTEMPT3_PAIR2_WARM_SHA256,
        ),
        "pair2 alias": (
            campaign_layout.results / f"{CELL_PINS[1][0]}.json",
            64_214,
            ATTEMPT3_PAIR2_WARM_SHA256,
        ),
        "pair2 Manager log": (
            attempt3_pair2_log_path(campaign_layout),
            25_081,
            ATTEMPT3_PAIR2_LOG_SHA256,
        ),
        "attempt3 operator stdout": (
            campaign_layout.results
            / "h3_unconditioned_music_campaign"
            / "operator_logs"
            / RESUME_ATTEMPT2_CAMPAIGN_ID
            / "stdout.log",
            3_865,
            "3d805bca0d44bba06b19ea316dbfb9a9753daaeca3b57f1df21f121174f76868",
        ),
        "attempt3 operator stderr": (
            campaign_layout.results
            / "h3_unconditioned_music_campaign"
            / "operator_logs"
            / RESUME_ATTEMPT2_CAMPAIGN_ID
            / "stderr.log",
            150,
            "2f0db3bb5cdda0b02311f561265a10d153551f2f6d7999d07fa20b890f687b2e",
        ),
    }
    snapshots: dict[str, Any] = {}
    raws: dict[str, bytes] = {}
    for label, (path, expected_bytes, expected_sha) in fixed_files.items():
        raw, snapshots[label] = _require_pinned_file(
            path, label, expected_bytes, expected_sha
        )
        raws[label] = raw
    if raws["pair2 warm"] != raws["pair2 alias"]:
        raise CampaignError("attempt-003 pair2 alias is not warm run2")
    artifacts = []
    for run_number in (1, 2):
        path = campaign_layout.outputs / (
            f"{CELL_PINS[1][0]}_out_{run_number:05d}_.mp4"
        )
        _, snapshot = _require_pinned_file(
            path,
            f"attempt-003 pair2 artifact run{run_number}",
            860_629,
            ATTEMPT3_PAIR2_ARTIFACT_SHA256,
        )
        artifacts.append(snapshot)

    pair1_evidence = verify_attempt2_preserved_evidence(campaign_layout)
    spec = load_specs(campaign_layout)[1]
    pair2 = verify_pair(
        spec,
        2,
        RESUME_ATTEMPT2_CAMPAIGN_ID,
        historical_sources,
        attempt3_pair2_log_path(campaign_layout),
        campaign_layout,
        cold_run_number=1,
        cold_config_run_count=1,
        warm_run_number=2,
        warm_config_run_count=2,
        allowed_run_numbers=(1, 2),
    )
    if sha256_bytes(canon.canonical_bytes(pair2)) != ATTEMPT3_PAIR2_RESULT_SHA256:
        raise CampaignError("attempt-003 pair2 full verifier result drifted")
    if (
        pair2["cold"]["receipt_sha256"] != ATTEMPT3_PAIR2_COLD_SHA256
        or pair2["warm"]["receipt_sha256"] != ATTEMPT3_PAIR2_WARM_SHA256
        or pair2["cold"]["server_instance"] != ATTEMPT3_PAIR2_SERVER_IDENTITY
        or pair2["warm"]["server_instance"] != ATTEMPT3_PAIR2_SERVER_IDENTITY
        or pair2["cold"]["run_identity_sha256"] != ATTEMPT3_PAIR2_RUN_IDENTITY_SHA256
        or pair2["warm"]["run_identity_sha256"] != ATTEMPT3_PAIR2_RUN_IDENTITY_SHA256
        or pair2["cold"]["queued_prompt_sha256"] != ATTEMPT3_PAIR2_COLD_QUEUED_SHA256
        or pair2["warm"]["queued_prompt_sha256"] != ATTEMPT3_PAIR2_WARM_QUEUED_SHA256
    ):
        raise CampaignError("attempt-003 pair2 recovered identity drifted")
    recorded = recovery3.get("full_pair_verification") or {}
    if (
        ((recorded.get("pair1") or {}).get("canonical_result_sha256"))
        != ATTEMPT2_PAIR_RESULT_SHA256
        or ((recorded.get("pair2") or {}).get("canonical_result_sha256"))
        != ATTEMPT3_PAIR2_RESULT_SHA256
        or ((recorded.get("pair2") or {}).get("cold_receipt_sha256"))
        != ATTEMPT3_PAIR2_COLD_SHA256
        or ((recorded.get("pair2") or {}).get("warm_receipt_sha256"))
        != ATTEMPT3_PAIR2_WARM_SHA256
    ):
        raise CampaignError("attempt-003 recovery full-pair binding drifted")
    return {
        "lifecycle": lifecycle,
        "attempt3_sources": historical_sources,
        "recovery3": {
            "path": str(recovery_path.resolve()),
            "bytes": len(recovery_raw),
            "sha256": ATTEMPT3_RECOVERY_RECEIPT_SHA256,
        },
        "pair1": pair1_evidence["pair"],
        "pair1_evidence": pair1_evidence,
        "pair2": pair2,
        "pair2_files": snapshots,
        "pair2_artifacts": artifacts,
        "attempt3_status": "FAILED",
        "attempt3_ledger_completed_pair_count": 1,
        "human_judgment": "PENDING",
    }


def verify_attempt3_recovery_receipt(
    current_sources: Mapping[str, Any],
    current_state: Mapping[str, Any],
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> dict[str, Any]:
    canon.require_clean_state(current_state, "attempt-004 recovery preflight")
    lifecycle_raw, _ = canon.stable_file(
        campaign_layout.lifecycle, "attempt-004 starting lifecycle"
    )
    if len(lifecycle_raw) != ATTEMPT3_LIFECYCLE_PREFIX_BYTES:
        raise CampaignError(
            "attempt-004 must begin immediately after the exact 22-row "
            "attempt-003 lifecycle"
        )
    preserved = verify_attempt3_preserved_evidence(campaign_layout)
    if (
        (current_sources.get("attempt3_recovery_recorder") or {}).get("sha256")
        != ATTEMPT3_RECOVERY_RECORDER_SHA256
        or (current_sources.get("attempt3_recovery_receipt") or {}).get("sha256")
        != ATTEMPT3_RECOVERY_RECEIPT_SHA256
    ):
        raise CampaignError("attempt-004 source set does not pin recovery-003")
    preserved["post_publication_cleanup_state"] = dict(current_state)
    preserved["post_publication_cleanup_reproved"] = True
    return preserved


def attempt3_evidence_summary(evidence: Mapping[str, Any]) -> dict[str, Any]:
    pair1 = evidence.get("pair1") or {}
    pair2 = evidence.get("pair2") or {}
    lifecycle = evidence.get("lifecycle") or {}
    return {
        "source_campaign_ids": [RESUME_CAMPAIGN_ID, RESUME_ATTEMPT2_CAMPAIGN_ID],
        "attempt3_status": evidence.get("attempt3_status"),
        "attempt3_ledger_completed_pair_count": evidence.get(
            "attempt3_ledger_completed_pair_count"
        ),
        "lifecycle_prefix": lifecycle.get("prefix"),
        "recovery3": evidence.get("recovery3"),
        "pair1_cold_receipt_sha256": (pair1.get("cold") or {}).get("receipt_sha256"),
        "pair1_warm_receipt_sha256": (pair1.get("warm") or {}).get("receipt_sha256"),
        "pair2_cold_receipt_sha256": (pair2.get("cold") or {}).get("receipt_sha256"),
        "pair2_warm_receipt_sha256": (pair2.get("warm") or {}).get("receipt_sha256"),
        "pair2_manager_log_sha256": (
            ((pair2.get("final_manager_log") or {}).get("log") or {}).get("sha256")
        ),
        "pair2_server_instance": (pair2.get("cold") or {}).get("server_instance"),
        "pair2_machine_status": "RECOVERABLE_COMPLETE",
        "human_judgment": evidence.get("human_judgment"),
        "post_publication_cleanup_state": evidence.get("post_publication_cleanup_state"),
    }


def verify_attempt4_lifecycle_prefix(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> dict[str, Any]:
    raw, _ = canon.stable_file(
        campaign_layout.lifecycle, "attempt-004 lifecycle prefix"
    )
    if len(raw) < ATTEMPT4_LIFECYCLE_PREFIX_BYTES:
        raise CampaignError("attempt-004 lifecycle prefix was truncated")
    prefix = raw[:ATTEMPT4_LIFECYCLE_PREFIX_BYTES]
    if (
        sha256_bytes(prefix) != ATTEMPT4_LIFECYCLE_PREFIX_SHA256
        or not prefix.endswith(b"\n")
    ):
        raise CampaignError("attempt-004 lifecycle prefix pin drifted")
    lines = prefix.splitlines()
    if len(lines) != ATTEMPT4_LIFECYCLE_ROW_COUNT:
        raise CampaignError("attempt-004 lifecycle prefix must contain 65 rows")
    previous: str | None = None
    campaign_sequences: dict[str, int] = {}
    records: list[dict[str, Any]] = []
    for ledger_sequence, line in enumerate(lines, start=1):
        try:
            row = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CampaignError("attempt-004 lifecycle row is malformed") from exc
        if not isinstance(row, dict):
            raise CampaignError("attempt-004 lifecycle row is not an object")
        body = dict(row)
        digest = body.pop("event_sha256", None)
        row_campaign = row.get("campaign_id")
        if not isinstance(row_campaign, str):
            raise CampaignError("attempt-004 lifecycle campaign id is malformed")
        campaign_sequences[row_campaign] = campaign_sequences.get(row_campaign, 0) + 1
        if (
            digest != sha256_bytes(canon.canonical_bytes(body))
            or row.get("ledger_sequence") != ledger_sequence
            or row.get("campaign_sequence") != campaign_sequences[row_campaign]
            or row.get("previous_event_sha256") != previous
        ):
            raise CampaignError("attempt-004 lifecycle identity/hash chain drifted")
        previous = digest
        records.append(row)
    if previous != ATTEMPT4_LIFECYCLE_LAST_EVENT_SHA256:
        raise CampaignError("attempt-004 lifecycle terminal SHA drifted")

    attempt4 = [
        row for row in records if row.get("campaign_id") == RESUME_ATTEMPT3_CAMPAIGN_ID
    ]
    expected_events = [
        "recovery_started",
        "campaign_started",
        "campaign_preflight_passed",
        "pair_carried_forward",
        "pair_carried_forward",
    ]
    for _ in range(3, 10):
        expected_events.extend(
            (
                "pair_started",
                "cold_child_returned",
                "cold_verified",
                "warm_shutdown_child_returned",
                "pair_verified",
            )
        )
    expected_events.extend(("pair_started", "cold_child_returned", "campaign_failed"))
    if len(attempt4) != 43 or [row.get("event") for row in attempt4] != expected_events:
        raise CampaignError("attempt-004 lifecycle event schedule drifted")
    terminal = attempt4[-1].get("details") or {}
    if (
        terminal.get("status") != "FAILED"
        or terminal.get("completed_pair_count") != 9
        or terminal.get("carried_pair_count") != 2
        or terminal.get("new_verified_pair_count") != 7
        or terminal.get("error")
        != f"{CELL_PINS[9][0]} run 1 field gate_pass drift: False != True"
        or terminal.get("stopped_without_force_or_additional_render") is not True
    ):
        raise CampaignError("attempt-004 terminal failure evidence drifted")
    sources = (attempt4[1].get("details") or {}).get("sources")
    if not isinstance(sources, dict):
        raise CampaignError("attempt-004 lifecycle source evidence is absent")
    pair_rows: dict[int, dict[str, Any]] = {}
    for row in attempt4:
        if row.get("event") not in {"pair_carried_forward", "pair_verified"}:
            continue
        details = row.get("details") or {}
        index = details.get("pair_index")
        if not isinstance(index, int) or index not in range(1, 10):
            raise CampaignError("attempt-004 completed pair index drifted")
        if index in pair_rows:
            raise CampaignError("attempt-004 completed pair was recorded twice")
        pair_rows[index] = details
    if sorted(pair_rows) != list(range(1, 10)):
        raise CampaignError("attempt-004 must preserve exactly pairs 1 through 9")
    return {
        "prefix": {
            "path": str(campaign_layout.lifecycle.resolve()),
            "bytes": ATTEMPT4_LIFECYCLE_PREFIX_BYTES,
            "sha256": ATTEMPT4_LIFECYCLE_PREFIX_SHA256,
            "row_count": ATTEMPT4_LIFECYCLE_ROW_COUNT,
            "last_event_sha256": ATTEMPT4_LIFECYCLE_LAST_EVENT_SHA256,
            "hash_chain_verified": True,
        },
        "sources": sources,
        "pair_rows": pair_rows,
        "terminal": {
            "status": "FAILED",
            "completed_pair_count": 9,
            "carried_pair_count": 2,
            "new_verified_pair_count": 7,
            "failure_state": terminal.get("failure_state"),
        },
    }


def _require_snapshot_sha(path: Path, label: str, expected_sha256: str) -> dict[str, Any]:
    _, snapshot = canon.stable_file(path, label)
    if snapshot.get("sha256") != expected_sha256:
        raise CampaignError(f"immutable {label} SHA drifted")
    return snapshot


def _require_alias_matches_archive(alias: Path, archive: Path, label: str) -> None:
    alias_raw, _ = canon.stable_file(alias, f"{label} alias")
    archive_raw, _ = canon.stable_file(archive, f"{label} archive")
    if alias_raw != archive_raw:
        raise CampaignError(f"{label} alias does not equal certified warm archive")


def _require_exact_carried_history(
    spec: canon.RecipeSpec,
    schedule: Mapping[str, Any],
    campaign_layout: canon.Layout,
    pair_index: int,
) -> None:
    allowed_receipts = {
        f"{spec.name}_run{number}.json" for number in schedule["allowed_run_numbers"]
    }
    found_receipts = {
        path.name
        for path in campaign_layout.results.iterdir()
        if path.name.startswith(f"{spec.name}_run")
    }
    allowed_outputs = {
        f"{spec.prefix}_{number:05d}_.mp4"
        for number in schedule["allowed_artifact_indices"]
    }
    found_outputs = {
        path.name
        for path in campaign_layout.outputs.iterdir()
        if path.name.startswith(spec.prefix)
    }
    if found_receipts != allowed_receipts or found_outputs != allowed_outputs:
        raise CampaignError(
            f"carried pair {pair_index} history drifted: "
            f"receipts={sorted(found_receipts)}, outputs={sorted(found_outputs)}"
        )


def verify_attempt4_preserved_evidence(
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
    *,
    require_initial_history: bool = False,
) -> dict[str, Any]:
    """Rehash the corrected attempt-004 authority without blocking new tail bytes."""

    lifecycle = verify_attempt4_lifecycle_prefix(campaign_layout)
    recovery_path = attempt4_recovery_receipt_path(campaign_layout)
    recovery4, recovery_raw = canon.strict_json(
        recovery_path, "corrected attempt-004 timeout recovery receipt"
    )
    if (
        len(recovery_raw) != ATTEMPT4_RECOVERY_RECEIPT_BYTES
        or sha256_bytes(recovery_raw) != ATTEMPT4_RECOVERY_RECEIPT_SHA256
    ):
        raise CampaignError("corrected attempt-004 recovery receipt pin drifted")
    superseded_path = attempt4_superseded_recovery_receipt_path(campaign_layout)
    _, superseded_snapshot = _require_pinned_file(
        superseded_path,
        "superseded attempt-004 recovery receipt",
        ATTEMPT4_SUPERSEDED_RECOVERY_RECEIPT_BYTES,
        ATTEMPT4_SUPERSEDED_RECOVERY_RECEIPT_SHA256,
    )
    _, recorder_snapshot = _require_pinned_file(
        ATTEMPT4_RECOVERY_RECORDER,
        "attempt-004 recovery recorder",
        ATTEMPT4_RECOVERY_RECORDER_BYTES,
        ATTEMPT4_RECOVERY_RECORDER_SHA256,
    )
    required = {
        "receipt_schema_version": 1,
        "receipt_kind": "h3-unconditioned-music-attempt-004-timeout-recovery-correction",
        "failed_campaign_id": RESUME_ATTEMPT3_CAMPAIGN_ID,
        "resume_campaign_id": RESUME_ATTEMPT4_CAMPAIGN_ID,
        "status": "ATTEMPT_004_FAILED_PAIRS_1_THROUGH_9_MACHINE_COMPLETE_CORRECTED",
        "success": True,
    }
    for field, expected in required.items():
        if recovery4.get(field) != expected:
            raise CampaignError(f"corrected attempt-004 recovery field drifted: {field}")
    immutable = recovery4.get("immutable_evidence") or {}
    prefix = ((immutable.get("lifecycle") or {}).get("prefix") or {})
    if (
        prefix.get("bytes") != ATTEMPT4_LIFECYCLE_PREFIX_BYTES
        or prefix.get("sha256") != ATTEMPT4_LIFECYCLE_PREFIX_SHA256
        or prefix.get("last_event_sha256")
        != ATTEMPT4_LIFECYCLE_LAST_EVENT_SHA256
    ):
        raise CampaignError("corrected attempt-004 lifecycle binding drifted")
    superseded = immutable.get("superseded_recovery") or {}
    if (
        superseded.get("classification") != "UNUSABLE_RESUME_AUTHORITY"
        or superseded.get("must_not_authorize_render") is not True
        or (superseded.get("snapshot") or {}).get("sha256")
        != ATTEMPT4_SUPERSEDED_RECOVERY_RECEIPT_SHA256
    ):
        raise CampaignError("superseded attempt-004 authority classification drifted")
    policy = recovery4.get("recovery_policy") or {}
    pair10_policy = policy.get("pair10") or {}
    pair11_policy = policy.get("pair11") or {}
    if (
        policy.get("carry_pair_indices") != list(range(1, 10))
        or policy.get("execute_pair_indices") != [10, 11]
        or policy.get("new_leg_count") != 4
        or policy.get("all_other_pair_execution_forbidden") is not True
        or policy.get("attempt004_run1_must_not_be_reclassified_or_overwritten")
        is not True
        or pair10_policy.get("recipe") != CELL_PINS[9][0]
        or pair10_policy.get("cold_run_number") != 2
        or pair10_policy.get("cold_config_run_count") != 1
        or pair10_policy.get("warm_run_number") != 3
        or pair10_policy.get("warm_config_run_count") != 2
        or pair10_policy.get("allowed_run_numbers") != [1, 2, 3]
        or pair10_policy.get("preserved_noncertifying_run_numbers") != [1]
        or pair11_policy.get("recipe") != CELL_PINS[10][0]
        or pair11_policy.get("cold_run_number") != 1
        or pair11_policy.get("cold_config_run_count") != 1
        or pair11_policy.get("warm_run_number") != 2
        or pair11_policy.get("warm_config_run_count") != 2
        or pair11_policy.get("allowed_run_numbers") != [1, 2]
        or pair11_policy.get("preserved_noncertifying_run_numbers") != []
        or policy.get("new_pair10_cold_and_warm_must_share_one_new_owned_server")
        is not True
        or policy.get("new_pair11_cold_and_warm_must_share_one_new_owned_server")
        is not True
    ):
        raise CampaignError("corrected attempt-004 recovery policy drifted")
    unfinished = recovery4.get("canonical_unfinished_specs")
    if (
        not isinstance(unfinished, list)
        or len(unfinished) != 2
        or (unfinished[0] or {}).get("pair_index") != 10
        or (unfinished[0] or {}).get("recipe") != CELL_PINS[9][0]
        or (unfinished[0] or {}).get("frames") != 192
        or (unfinished[1] or {}).get("pair_index") != 11
        or (unfinished[1] or {}).get("recipe") != CELL_PINS[10][0]
        or (unfinished[1] or {}).get("frames") != 277
        or (unfinished[1] or {}).get("recipe_sha256") != CELL_PINS[10][1]
    ):
        raise CampaignError("corrected recovery unfinished-spec authority drifted")

    specs = load_specs(campaign_layout)
    compact_rows = recovery4.get("full_pair_verification")
    if not isinstance(compact_rows, list) or len(compact_rows) != 9:
        raise CampaignError("corrected recovery pair verification set drifted")
    compact_by_index = {row.get("pair_index"): row for row in compact_rows}
    if set(compact_by_index) != set(range(1, 10)):
        raise CampaignError("corrected recovery pair indices drifted")
    pairs: dict[int, dict[str, Any]] = {}
    pair_sources: dict[int, dict[str, Any]] = {}
    for index in range(1, 10):
        spec = specs[index - 1]
        details = lifecycle["pair_rows"][index]
        pair = details.get("pair")
        compact = compact_by_index[index]
        if not isinstance(pair, dict):
            raise CampaignError(f"attempt-004 pair {index} evidence is absent")
        source_campaign_id = (
            RESUME_CAMPAIGN_ID
            if index == 1
            else (
                RESUME_ATTEMPT2_CAMPAIGN_ID
                if index == 2
                else RESUME_ATTEMPT3_CAMPAIGN_ID
            )
        )
        schedule = pair_run_schedule(
            index, False, False, True, False
        )
        cold_number = schedule["cold_run_number"]
        warm_number = schedule["warm_run_number"]
        cold_artifact_index = schedule["cold_artifact_index"]
        warm_artifact_index = schedule["warm_artifact_index"]
        manager_log = (
            attempt2_pair_log_path(campaign_layout)
            if index == 1
            else (
                attempt3_pair2_log_path(campaign_layout)
                if index == 2
                else attempt4_pair_log_path(spec, index, campaign_layout)
            )
        )
        expected = {
            "recipe": spec.name,
            "source_campaign_id": source_campaign_id,
            "canonical_result_sha256": sha256_bytes(canon.canonical_bytes(pair)),
            "cold_receipt_sha256": (pair.get("cold") or {}).get("receipt_sha256"),
            "warm_receipt_sha256": (pair.get("warm") or {}).get("receipt_sha256"),
            "cold_artifact_sha256": ((pair.get("cold") or {}).get("artifact") or {}).get("sha256"),
            "warm_artifact_sha256": ((pair.get("warm") or {}).get("artifact") or {}).get("sha256"),
            "manager_log_sha256": (((pair.get("final_manager_log") or {}).get("log") or {}).get("sha256")),
            "status": "MACHINE_COMPLETE",
            "human_judgment": "PENDING_HUMAN",
        }
        if any(compact.get(field) != value for field, value in expected.items()):
            raise CampaignError(f"corrected recovery pair {index} binding drifted")
        _require_snapshot_sha(
            campaign_layout.results / f"{spec.name}_run{cold_number}.json",
            f"pair {index} cold receipt",
            expected["cold_receipt_sha256"],
        )
        _require_snapshot_sha(
            campaign_layout.results / f"{spec.name}_run{warm_number}.json",
            f"pair {index} warm receipt",
            expected["warm_receipt_sha256"],
        )
        _require_alias_matches_archive(
            campaign_layout.results / f"{spec.name}.json",
            campaign_layout.results / f"{spec.name}_run{warm_number}.json",
            f"pair {index}",
        )
        _require_snapshot_sha(
            campaign_layout.outputs
            / f"{spec.prefix}_{cold_artifact_index:05d}_.mp4",
            f"pair {index} cold artifact",
            expected["cold_artifact_sha256"],
        )
        _require_snapshot_sha(
            campaign_layout.outputs
            / f"{spec.prefix}_{warm_artifact_index:05d}_.mp4",
            f"pair {index} warm artifact",
            expected["warm_artifact_sha256"],
        )
        _require_snapshot_sha(
            manager_log,
            f"pair {index} Manager log",
            expected["manager_log_sha256"],
        )
        _require_exact_carried_history(spec, schedule, campaign_layout, index)
        pairs[index] = pair
        pair_sources[index] = {
            "source_campaign_id": source_campaign_id,
            "manager_log": str(manager_log),
            "receipt_schedule": schedule,
        }

    pair10 = specs[9]
    run1_path = campaign_layout.results / f"{pair10.name}_run1.json"
    run1_raw, run1_snapshot = _require_pinned_file(
        run1_path,
        "attempt-004 pair10 failed run1",
        ATTEMPT4_PAIR10_RUN1_BYTES,
        ATTEMPT4_PAIR10_RUN1_SHA256,
    )
    old_pair10_log = attempt4_pair_log_path(pair10, 10, campaign_layout)
    _, pair10_log_snapshot = _require_pinned_file(
        old_pair10_log,
        "attempt-004 pair10 Manager log",
        ATTEMPT4_PAIR10_LOG_BYTES,
        ATTEMPT4_PAIR10_LOG_SHA256,
    )
    old_operator_paths = operator_transport_paths(
        campaign_layout, RESUME_ATTEMPT3_CAMPAIGN_ID
    )
    _, stdout_snapshot = _require_pinned_file(
        old_operator_paths["stdout"],
        "attempt-004 operator stdout",
        ATTEMPT4_OPERATOR_STDOUT_BYTES,
        ATTEMPT4_OPERATOR_STDOUT_SHA256,
    )
    _, stderr_snapshot = _require_pinned_file(
        old_operator_paths["stderr"],
        "attempt-004 operator stderr",
        ATTEMPT4_OPERATOR_STDERR_BYTES,
        ATTEMPT4_OPERATOR_STDERR_SHA256,
    )
    failed_receipt = ((immutable.get("pair10_failed_run1") or {}).get("receipt") or {})
    if (
        failed_receipt.get("sha256") != ATTEMPT4_PAIR10_RUN1_SHA256
        or ((immutable.get("pair10_failed_run1") or {}).get("manager_log") or {}).get("sha256")
        != ATTEMPT4_PAIR10_LOG_SHA256
    ):
        raise CampaignError("corrected recovery pair10 failure binding drifted")
    if require_initial_history:
        lifecycle_raw, _ = canon.stable_file(
            campaign_layout.lifecycle, "attempt-005 starting lifecycle"
        )
        if len(lifecycle_raw) != ATTEMPT4_LIFECYCLE_PREFIX_BYTES:
            raise CampaignError(
                "attempt-005 must begin immediately after the exact 65-row attempt-004 lifecycle"
            )
        alias_raw, _ = canon.stable_file(
            campaign_layout.results / f"{pair10.name}.json",
            "attempt-004 pair10 failed alias",
        )
        if alias_raw != run1_raw:
            raise CampaignError("attempt-004 pair10 alias no longer equals failed run1")
        for relative in immutable.get("required_absences") or []:
            path_text = relative.get("path") if isinstance(relative, dict) else None
            if not isinstance(path_text, str) or not relative.get("absent"):
                raise CampaignError("corrected recovery absence record drifted")
            path = campaign_layout.root / Path(path_text)
            if os.path.lexists(path):
                raise CampaignError(f"attempt-005 initial absence gate failed: {path_text}")
    return {
        "lifecycle": lifecycle,
        "recovery4": {
            "path": str(recovery_path.resolve()),
            "bytes": len(recovery_raw),
            "sha256": ATTEMPT4_RECOVERY_RECEIPT_SHA256,
            "recovery_id": recovery4.get("recovery_id"),
        },
        "superseded_recovery": superseded_snapshot,
        "recovery_recorder": recorder_snapshot,
        "pairs": pairs,
        "pair_sources": pair_sources,
        "pair10_failed_run1": {
            "receipt": run1_snapshot,
            "manager_log": pair10_log_snapshot,
            "qualifying_study_leg": False,
            "artifact_finalized": False,
        },
        "operator_streams": {
            "stdout": stdout_snapshot,
            "stderr": stderr_snapshot,
        },
        "attempt4_status": "FAILED",
        "attempt4_ledger_completed_pair_count": 9,
        "carried_pair_count": 9,
        "failed_historical_execution_count": 1,
        "valid_orphan_historical_cold_count": 1,
        "human_judgment": "PENDING_HUMAN",
    }


def verify_attempt4_recovery_receipt(
    current_sources: Mapping[str, Any],
    current_state: Mapping[str, Any],
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> dict[str, Any]:
    canon.require_clean_state(current_state, "attempt-005 recovery preflight")
    if (
        (current_sources.get("runner") or {}).get("sha256")
        != ATTEMPT5_RUNNER_SHA256
        or (current_sources.get("attempt4_recovery_recorder") or {}).get("sha256")
        != ATTEMPT4_RECOVERY_RECORDER_SHA256
        or (current_sources.get("attempt4_recovery_receipt") or {}).get("sha256")
        != ATTEMPT4_RECOVERY_RECEIPT_SHA256
        or not (current_sources.get("attempt5_operator_launcher") or {}).get("sha256")
        or not (current_sources.get("attempt5_operator_recorder") or {}).get("sha256")
    ):
        raise CampaignError("attempt-005 source set does not pin its recovery/transport")
    return verify_attempt4_preserved_evidence(
        campaign_layout, require_initial_history=True
    )


def attempt4_evidence_summary(evidence: Mapping[str, Any]) -> dict[str, Any]:
    pairs = evidence.get("pairs") or {}
    pair_sources = evidence.get("pair_sources") or {}
    return {
        "source_campaign_id": RESUME_ATTEMPT3_CAMPAIGN_ID,
        "attempt4_status": evidence.get("attempt4_status"),
        "attempt4_ledger_completed_pair_count": evidence.get(
            "attempt4_ledger_completed_pair_count"
        ),
        "lifecycle_prefix": (evidence.get("lifecycle") or {}).get("prefix"),
        "recovery4": evidence.get("recovery4"),
        "superseded_recovery": evidence.get("superseded_recovery"),
        "pair_indices": sorted(pairs),
        "pair_source_campaign_ids": {
            index: (pair_sources.get(index) or {}).get("source_campaign_id")
            for index in sorted(pairs)
        },
        "pair10_failed_run1": evidence.get("pair10_failed_run1"),
        "carried_pair_count": evidence.get("carried_pair_count"),
        "valid_orphan_historical_cold_count": evidence.get(
            "valid_orphan_historical_cold_count"
        ),
        "failed_historical_execution_count": evidence.get(
            "failed_historical_execution_count"
        ),
        "human_judgment": evidence.get("human_judgment"),
    }


def execute_campaign(
    *,
    campaign_id: str | None = None,
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
    child_runner: Callable[[Sequence[str], Mapping[str, str], Path], Any]
    | None = None,
    state_probe: Callable[[Mapping[str, Any] | None], dict[str, Any]]
    | None = None,
    cleanup_owned_server: Callable[[], dict[str, Any]] | None = None,
    resume_attempt_001: bool = False,
    resume_attempt_002: bool = False,
    resume_attempt_003: bool = False,
    resume_attempt_004: bool = False,
    operator_stdout_log: str | os.PathLike[str] | None = None,
    operator_stderr_log: str | os.PathLike[str] | None = None,
    operator_transport_probe: Callable[
        [str | os.PathLike[str] | None, str | os.PathLike[str] | None, Mapping[str, Any]],
        dict[str, Any],
    ]
    | None = None,
    campaign_process_probe: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    campaign_id = validate_campaign_id(campaign_id or campaign_id_now())
    if sum(
        (
            resume_attempt_001,
            resume_attempt_002,
            resume_attempt_003,
            resume_attempt_004,
        )
    ) > 1:
        raise CampaignError("attempt recovery modes are mutually exclusive")
    if resume_attempt_001 and campaign_id != RESUME_CAMPAIGN_ID:
        raise CampaignError(
            f"attempt-001 recovery must use exact campaign id {RESUME_CAMPAIGN_ID}"
        )
    if resume_attempt_002 and campaign_id != RESUME_ATTEMPT2_CAMPAIGN_ID:
        raise CampaignError(
            "attempt-002 recovery must use exact campaign id "
            f"{RESUME_ATTEMPT2_CAMPAIGN_ID}"
        )
    if resume_attempt_003 and campaign_id != RESUME_ATTEMPT3_CAMPAIGN_ID:
        raise CampaignError(
            "attempt-004 continuation must use exact campaign id "
            f"{RESUME_ATTEMPT3_CAMPAIGN_ID}"
        )
    if resume_attempt_004 and campaign_id != RESUME_ATTEMPT4_CAMPAIGN_ID:
        raise CampaignError(
            "attempt-005 continuation must use exact campaign id "
            f"{RESUME_ATTEMPT4_CAMPAIGN_ID}"
        )
    if not (resume_attempt_002 or resume_attempt_003 or resume_attempt_004) and (
        operator_stdout_log is not None or operator_stderr_log is not None
    ):
        raise CampaignError("operator log arguments are reserved for durable recovery attempts")
    specs = load_specs(campaign_layout)
    plan = runbook(
        campaign_id,
        campaign_layout,
        resume_attempt_001=resume_attempt_001,
        resume_attempt_002=resume_attempt_002,
        resume_attempt_003=resume_attempt_003,
        resume_attempt_004=resume_attempt_004,
    )
    sources = source_evidence(campaign_layout)
    probe_state = state_probe or (
        lambda expected=None: canon.runtime_state(expected, campaign_layout)
    )
    invoke_child = child_runner or (
        lambda command, environment, cwd: canon._subprocess_child(
            command,
            environment,
            cwd,
            campaign_layout,
            validate_server_argv,
        )
    )
    if cleanup_owned_server is None:
        def cleanup_owned_server() -> dict[str, Any]:
            import run_recipe

            return run_recipe.shutdown_lab_server()

    owned_server: dict[str, Any] | None = None
    pending_cold: canon.ChildOutcome | None = None
    completed: list[dict[str, Any]] = []
    initial_state = probe_state(None)
    canon.require_clean_state(initial_state, "campaign initial state")
    recovery: dict[str, Any] | None = None
    preserved_attempt1: dict[str, Any] | None = None
    recovery2: dict[str, Any] | None = None
    recovery3: dict[str, Any] | None = None
    recovery4: dict[str, Any] | None = None
    operator_transport: dict[str, Any] | None = None
    campaign_process: dict[str, Any] | None = None
    if resume_attempt_001:
        preserved_attempt1 = verify_failed_attempt_evidence(
            sources,
            campaign_layout,
            require_alias_run1=True,
        )
        recovery = verify_recovery_receipt(
            sources,
            initial_state,
            campaign_layout,
        )
    elif resume_attempt_002:
        recovery2 = verify_attempt2_recovery_receipt(
            sources,
            initial_state,
            campaign_layout,
        )
        if operator_transport_probe is None:
            operator_transport = validate_operator_transport(
                operator_stdout_log,
                operator_stderr_log,
                sources,
                campaign_layout,
            )
        else:
            operator_transport = operator_transport_probe(
                operator_stdout_log,
                operator_stderr_log,
                sources,
            )
        if not isinstance(operator_transport, dict):
            raise CampaignError("attempt-003 operator transport probe returned no evidence")
        if operator_transport.get("contract") != operator_log_contract(
            sources, campaign_layout
        ):
            raise CampaignError("attempt-003 operator transport contract drifted")
    elif resume_attempt_003:
        recovery3 = verify_attempt3_recovery_receipt(
            sources,
            initial_state,
            campaign_layout,
        )
        if operator_transport_probe is None:
            operator_transport = validate_operator_transport(
                operator_stdout_log,
                operator_stderr_log,
                sources,
                campaign_layout,
                attempt_id=RESUME_ATTEMPT3_CAMPAIGN_ID,
            )
        else:
            operator_transport = operator_transport_probe(
                operator_stdout_log,
                operator_stderr_log,
                sources,
            )
        if not isinstance(operator_transport, dict):
            raise CampaignError("attempt-004 operator transport probe returned no evidence")
        if operator_transport.get("contract") != operator_log_contract(
            sources,
            campaign_layout,
            attempt_id=RESUME_ATTEMPT3_CAMPAIGN_ID,
        ):
            raise CampaignError("attempt-004 operator transport contract drifted")
        campaign_process = validate_campaign_process_identity(
            (
                campaign_process_probe()
                if campaign_process_probe is not None
                else observe_campaign_process_identity(campaign_layout)
            ),
            campaign_layout,
        )
    elif resume_attempt_004:
        recovery4 = verify_attempt4_recovery_receipt(
            sources,
            initial_state,
            campaign_layout,
        )
        if operator_transport_probe is None:
            operator_transport = validate_operator_transport(
                operator_stdout_log,
                operator_stderr_log,
                sources,
                campaign_layout,
                attempt_id=RESUME_ATTEMPT4_CAMPAIGN_ID,
            )
        else:
            operator_transport = operator_transport_probe(
                operator_stdout_log,
                operator_stderr_log,
                sources,
            )
        if not isinstance(operator_transport, dict):
            raise CampaignError("attempt-005 operator transport probe returned no evidence")
        if operator_transport.get("contract") != operator_log_contract(
            sources,
            campaign_layout,
            attempt_id=RESUME_ATTEMPT4_CAMPAIGN_ID,
        ):
            raise CampaignError("attempt-005 operator transport contract drifted")
        campaign_process = validate_campaign_process_identity(
            (
                campaign_process_probe()
                if campaign_process_probe is not None
                else observe_campaign_process_identity(
                    campaign_layout,
                    attempt_id=RESUME_ATTEMPT4_CAMPAIGN_ID,
                )
            ),
            campaign_layout,
            attempt_id=RESUME_ATTEMPT4_CAMPAIGN_ID,
        )
    if resume_attempt_004:
        require_attempt_manager_log_set(
            campaign_id,
            (),
            campaign_layout,
            label="attempt-005 initial",
        )
    ledger = canon.AppendOnlyLifecycle(campaign_layout.lifecycle, campaign_id)
    if recovery is not None:
        ledger.append(
            "recovery_started",
            {
                "failed_campaign_id": FAILED_CAMPAIGN_ID,
                "recovery_receipt": recovery,
                "preserved_attempt1": failed_attempt_evidence_summary(
                    preserved_attempt1 or {}
                ),
                "resume_policy": pair_run_schedule(1, True),
                "current_clean_state": initial_state,
            },
        )
    if recovery2 is not None:
        ledger.append(
            "recovery_started",
            {
                "failed_campaign_id": RESUME_CAMPAIGN_ID,
                "recovery_receipt": recovery2["recovery2"],
                "preserved_attempt2": attempt2_evidence_summary(recovery2),
                "resume_policy": {
                    "carried_pair_indices": [1],
                    "execute_pair_indices": list(range(2, 12)),
                    "new_execution_count": 20,
                },
                "current_clean_state": initial_state,
            },
        )
    if recovery3 is not None:
        ledger.append(
            "recovery_started",
            {
                "failed_campaign_id": RESUME_ATTEMPT2_CAMPAIGN_ID,
                "recovery_receipt": recovery3["recovery3"],
                "preserved_attempt3": attempt3_evidence_summary(recovery3),
                "resume_policy": {
                    "carried_pair_indices": [1, 2],
                    "execute_pair_indices": list(range(3, 12)),
                    "new_execution_count": 18,
                },
                "current_clean_state": initial_state,
            },
        )
    if recovery4 is not None:
        ledger.append(
            "recovery_started",
            {
                "failed_campaign_id": RESUME_ATTEMPT3_CAMPAIGN_ID,
                "recovery_receipt": recovery4["recovery4"],
                "preserved_attempt4": attempt4_evidence_summary(recovery4),
                "resume_policy": {
                    "carried_pair_indices": list(range(1, 10)),
                    "execute_pair_indices": [10, 11],
                    "new_execution_count": 4,
                    "failed_historical_execution_count": 1,
                },
                "current_clean_state": initial_state,
            },
        )
    ledger.append(
        "campaign_started",
        {
            "plan": plan,
            "sources": sources,
            "execution_authority": "run_recipe.py only",
            "quality_judgment": "out of scope",
            "otr_touched": False,
            "resume_attempt_001": resume_attempt_001,
            "resume_attempt_002": resume_attempt_002,
            "resume_attempt_003": resume_attempt_003,
            "resume_attempt_004": resume_attempt_004,
            "recovery_receipt": recovery if recovery is not None else (
                recovery2["recovery2"] if recovery2 is not None else (
                    recovery3["recovery3"] if recovery3 is not None else (
                        recovery4["recovery4"] if recovery4 is not None else None
                    )
                )
            ),
            "operator_logs": (
                operator_transport["contract"]
                if operator_transport is not None
                else None
            ),
            "operator_transport_preflight": operator_transport,
            "campaign_process": campaign_process,
        },
    )
    try:
        for index, spec in enumerate(specs, start=1):
            canon.require_recipe_unchanged(spec)
            canon.require_fixtures_unchanged(spec, campaign_layout)
            carried_in_current_resume = (
                (resume_attempt_002 and index == 1)
                or (resume_attempt_003 and index in {1, 2})
                or (resume_attempt_004 and index <= 9)
            )
            if carried_in_current_resume:
                unused_log = pair_log_path(
                    spec, index, campaign_id, campaign_layout
                )
                if os.path.lexists(unused_log):
                    raise CampaignError(
                        f"current recovery carried pair {index} must not have a new Manager log"
                    )
                continue
            ensure_pristine_pair(
                spec,
                pair_log_path(spec, index, campaign_id, campaign_layout),
                campaign_layout,
                resume_attempt_001=resume_attempt_001,
                resume_attempt_004=resume_attempt_004,
                pair_index=index,
            )
        ledger.append(
            "campaign_preflight_passed",
            {
                "state": initial_state,
                "histories_match_attempt_plan": True,
                "preserved_attempt1": (
                    failed_attempt_evidence_summary(preserved_attempt1)
                    if preserved_attempt1 is not None
                    else None
                ),
                "preserved_attempt2": (
                    attempt2_evidence_summary(recovery2)
                    if recovery2 is not None
                    else None
                ),
                "preserved_attempt3": (
                    attempt3_evidence_summary(recovery3)
                    if recovery3 is not None
                    else None
                ),
                "preserved_attempt4": (
                    attempt4_evidence_summary(recovery4)
                    if recovery4 is not None
                    else None
                ),
                "operator_transport_preflight": operator_transport,
            },
        )
        if recovery2 is not None:
            carried = {
                "pair_index": 1,
                "recipe": specs[0].name,
                "logical_roles": list(CELL_PINS[0][4]),
                "status": "CARRIED_FORWARD",
                "source_campaign_id": RESUME_CAMPAIGN_ID,
                "receipt_schedule": recovery2["receipt_schedule"],
                "pair": recovery2["pair"],
                "current_carry_preflight_state": initial_state,
                "attempt2_exit_120_cause": "UNKNOWN_UNPROVED",
                "normal_runner_shutdown_proved": False,
                "preserved_attempt2": attempt2_evidence_summary(recovery2),
                "new_execution_count": 0,
                "human_judgment": "PENDING",
            }
            completed.append(carried)
            ledger.append("pair_carried_forward", carried)
        if recovery3 is not None:
            carried_pair1 = {
                "pair_index": 1,
                "recipe": specs[0].name,
                "logical_roles": list(CELL_PINS[0][4]),
                "status": "CARRIED_FORWARD",
                "source_campaign_id": RESUME_CAMPAIGN_ID,
                "receipt_schedule": pair_run_schedule(1, False, False, True),
                "pair": recovery3["pair1"],
                "current_carry_preflight_state": initial_state,
                "preserved_attempt3": attempt3_evidence_summary(recovery3),
                "new_execution_count": 0,
                "human_judgment": "PENDING",
            }
            carried_pair2 = {
                "pair_index": 2,
                "recipe": specs[1].name,
                "logical_roles": list(CELL_PINS[1][4]),
                "status": "CARRIED_FORWARD",
                "source_campaign_id": RESUME_ATTEMPT2_CAMPAIGN_ID,
                "receipt_schedule": pair_run_schedule(2, False, False, True),
                "pair": recovery3["pair2"],
                "current_carry_preflight_state": initial_state,
                "preserved_attempt3": attempt3_evidence_summary(recovery3),
                "new_execution_count": 0,
                "human_judgment": "PENDING",
            }
            completed.extend((carried_pair1, carried_pair2))
            ledger.append("pair_carried_forward", carried_pair1)
            ledger.append("pair_carried_forward", carried_pair2)
        if recovery4 is not None:
            for index in range(1, 10):
                spec = specs[index - 1]
                pair_source = recovery4["pair_sources"][index]
                carried = {
                    "pair_index": index,
                    "recipe": spec.name,
                    "logical_roles": list(CELL_PINS[index - 1][4]),
                    "status": "CARRIED_FORWARD",
                    "source_campaign_id": pair_source["source_campaign_id"],
                    "source_manager_log": pair_source["manager_log"],
                    "receipt_schedule": pair_source["receipt_schedule"],
                    "pair": recovery4["pairs"][index],
                    "current_carry_preflight_state": initial_state,
                    "preserved_attempt4": attempt4_evidence_summary(recovery4),
                    "new_execution_count": 0,
                    "human_judgment": "PENDING_HUMAN",
                }
                completed.append(carried)
                ledger.append("pair_carried_forward", carried)
        execution_specs = (
            list(enumerate(specs[9:], start=10))
            if resume_attempt_004
            else (
                list(enumerate(specs[2:], start=3))
                if resume_attempt_003
                else (
                    list(enumerate(specs[1:], start=2))
                    if resume_attempt_002
                    else list(enumerate(specs, start=1))
                )
            )
        )
        for index, spec in execution_specs:
            schedule = pair_run_schedule(
                index,
                resume_attempt_001,
                resume_attempt_002,
                resume_attempt_003,
                resume_attempt_004,
            )
            require_same_sources(
                sources,
                source_evidence(campaign_layout),
                f"pair {index} pre-cold",
            )
            before = probe_state(None)
            canon.require_clean_state(before, f"pair {index} pre-cold")
            log_path = pair_log_path(spec, index, campaign_id, campaign_layout)
            ensure_pristine_pair(
                spec,
                log_path,
                campaign_layout,
                resume_attempt_001=resume_attempt_001,
                resume_attempt_004=resume_attempt_004,
                pair_index=index,
            )
            log_path.parent.mkdir(parents=True, exist_ok=True)
            canon.ensure_real_directory(
                log_path.parent, "Manager attempt-log directory"
            )
            environment = child_environment(log_path)
            cold_command = child_command(
                spec, index, "cold", campaign_id, campaign_layout
            )
            warm_command = child_command(
                spec, index, "warm", campaign_id, campaign_layout
            )
            ledger.append(
                "pair_started",
                {
                    "pair_index": index,
                    "recipe": spec.name,
                    "manager_log": str(log_path),
                    "receipt_schedule": schedule,
                    "cold_argv": cold_command,
                    "warm_shutdown_argv": warm_command,
                },
            )
            cold_outcome = canon.normalize_child_outcome(
                invoke_child(cold_command, environment, campaign_layout.root)
            )
            pending_cold = cold_outcome
            preserved_after_cold_child = None
            preserved_attempt2_after_cold = None
            preserved_attempt3_after_cold = None
            preserved_attempt4_after_cold = None
            if resume_attempt_001:
                preserved_after_cold_child = verify_failed_attempt_evidence(
                    sources,
                    campaign_layout,
                    require_alias_run1=False,
                )
            elif resume_attempt_002:
                preserved_attempt2_after_cold = (
                    verify_attempt2_preserved_evidence(campaign_layout)
                )
            elif resume_attempt_003:
                preserved_attempt3_after_cold = (
                    verify_attempt3_preserved_evidence(campaign_layout)
                )
            elif resume_attempt_004:
                preserved_attempt4_after_cold = (
                    verify_attempt4_preserved_evidence(campaign_layout)
                )
            require_same_sources(
                sources,
                source_evidence(campaign_layout),
                f"pair {index} post-cold-child",
            )
            ledger.append(
                "cold_child_returned",
                {
                    "pair_index": index,
                    "outcome": cold_outcome.as_dict(),
                    "preserved_attempt1": (
                        failed_attempt_evidence_summary(
                            preserved_after_cold_child
                        )
                        if preserved_after_cold_child is not None
                        else None
                    ),
                    "preserved_attempt2": (
                        attempt2_evidence_summary(preserved_attempt2_after_cold)
                        if preserved_attempt2_after_cold is not None
                        else None
                    ),
                    "preserved_attempt3": (
                        attempt3_evidence_summary(preserved_attempt3_after_cold)
                        if preserved_attempt3_after_cold is not None
                        else None
                    ),
                    "preserved_attempt4": (
                        attempt4_evidence_summary(preserved_attempt4_after_cold)
                        if preserved_attempt4_after_cold is not None
                        else None
                    ),
                },
            )
            if cold_outcome.returncode != 0:
                raise CampaignError(
                    f"{spec.name} cold child returned {cold_outcome.returncode}"
                )
            cold = verify_run_receipt(
                spec,
                schedule["cold_run_number"],
                executor_nonce(campaign_id, index, "cold"),
                sources,
                log_path,
                campaign_layout,
                role="cold",
                expected_config_run_count=schedule["cold_config_run_count"],
                expected_completion_timeout_s=schedule.get(
                    "completion_timeout_s"
                ),
                expected_artifact_index=schedule["cold_artifact_index"],
            )
            canon.require_observed_child_server(
                cold_outcome,
                cold["server_instance"],
                campaign_layout,
                expected_server_argv,
            )
            owned_server = dict(cold["server_instance"])
            pending_cold = None
            boundary = probe_state(owned_server)
            canon.require_warm_server_state(
                boundary, owned_server, f"{spec.name} cold-to-warm"
            )
            require_same_sources(
                sources,
                source_evidence(campaign_layout),
                f"pair {index} pre-warm",
            )
            ledger.append(
                "cold_verified",
                {
                    "pair_index": index,
                    "cold": cold,
                    "boundary": boundary,
                    "preserved_attempt1": (
                        failed_attempt_evidence_summary(
                            preserved_after_cold_child
                        )
                        if preserved_after_cold_child is not None
                        else None
                    ),
                    "preserved_attempt2": (
                        attempt2_evidence_summary(preserved_attempt2_after_cold)
                        if preserved_attempt2_after_cold is not None
                        else None
                    ),
                    "preserved_attempt3": (
                        attempt3_evidence_summary(preserved_attempt3_after_cold)
                        if preserved_attempt3_after_cold is not None
                        else None
                    ),
                    "preserved_attempt4": (
                        attempt4_evidence_summary(preserved_attempt4_after_cold)
                        if preserved_attempt4_after_cold is not None
                        else None
                    ),
                },
            )
            warm_outcome = canon.normalize_child_outcome(
                invoke_child(warm_command, environment, campaign_layout.root)
            )
            preserved_after_warm_child = None
            preserved_attempt2_after_warm = None
            preserved_attempt3_after_warm = None
            preserved_attempt4_after_warm = None
            if resume_attempt_001:
                preserved_after_warm_child = verify_failed_attempt_evidence(
                    sources,
                    campaign_layout,
                    require_alias_run1=False,
                )
            elif resume_attempt_002:
                preserved_attempt2_after_warm = (
                    verify_attempt2_preserved_evidence(campaign_layout)
                )
            elif resume_attempt_003:
                preserved_attempt3_after_warm = (
                    verify_attempt3_preserved_evidence(campaign_layout)
                )
            elif resume_attempt_004:
                preserved_attempt4_after_warm = (
                    verify_attempt4_preserved_evidence(campaign_layout)
                )
            require_same_sources(
                sources,
                source_evidence(campaign_layout),
                f"pair {index} post-warm-child",
            )
            ledger.append(
                "warm_shutdown_child_returned",
                {
                    "pair_index": index,
                    "outcome": warm_outcome.as_dict(),
                    "preserved_attempt1": (
                        failed_attempt_evidence_summary(
                            preserved_after_warm_child
                        )
                        if preserved_after_warm_child is not None
                        else None
                    ),
                    "preserved_attempt2": (
                        attempt2_evidence_summary(preserved_attempt2_after_warm)
                        if preserved_attempt2_after_warm is not None
                        else None
                    ),
                    "preserved_attempt3": (
                        attempt3_evidence_summary(preserved_attempt3_after_warm)
                        if preserved_attempt3_after_warm is not None
                        else None
                    ),
                    "preserved_attempt4": (
                        attempt4_evidence_summary(preserved_attempt4_after_warm)
                        if preserved_attempt4_after_warm is not None
                        else None
                    ),
                },
            )
            if warm_outcome.returncode != 0:
                raise CampaignError(
                    f"{spec.name} warm child returned {warm_outcome.returncode}"
                )
            require_same_sources(
                sources,
                source_evidence(campaign_layout),
                f"pair {index} post-warm",
            )
            pair = verify_pair(
                spec,
                index,
                campaign_id,
                sources,
                log_path,
                campaign_layout,
                cold_snapshot=cold,
                cold_run_number=schedule["cold_run_number"],
                cold_config_run_count=schedule["cold_config_run_count"],
                warm_run_number=schedule["warm_run_number"],
                warm_config_run_count=schedule["warm_config_run_count"],
                allowed_run_numbers=schedule["allowed_run_numbers"],
                expected_completion_timeout_s=schedule.get(
                    "completion_timeout_s"
                ),
                cold_artifact_index=schedule["cold_artifact_index"],
                warm_artifact_index=schedule["warm_artifact_index"],
                allowed_artifact_indices=schedule["allowed_artifact_indices"],
            )
            after = probe_state(owned_server)
            canon.require_clean_state(after, f"{spec.name} post-shutdown")
            row = {
                "pair_index": index,
                "recipe": spec.name,
                "logical_roles": list(CELL_PINS[index - 1][4]),
                "receipt_schedule": schedule,
                "pair": pair,
                "post_shutdown_state": after,
                "preserved_attempt1_after_warm": (
                    failed_attempt_evidence_summary(preserved_after_warm_child)
                    if preserved_after_warm_child is not None
                    else None
                ),
                "preserved_attempt2_after_warm": (
                    attempt2_evidence_summary(preserved_attempt2_after_warm)
                    if preserved_attempt2_after_warm is not None
                    else None
                ),
                "preserved_attempt3_after_warm": (
                    attempt3_evidence_summary(preserved_attempt3_after_warm)
                    if preserved_attempt3_after_warm is not None
                    else None
                ),
                "preserved_attempt4_after_warm": (
                    attempt4_evidence_summary(preserved_attempt4_after_warm)
                    if preserved_attempt4_after_warm is not None
                    else None
                ),
                "new_execution_count": 2,
            }
            completed.append(row)
            ledger.append("pair_verified", row)
            owned_server = None

        if resume_attempt_004:
            require_attempt_manager_log_set(
                campaign_id,
                (
                    pair_log_path(specs[9], 10, campaign_id, campaign_layout),
                    pair_log_path(specs[10], 11, campaign_id, campaign_layout),
                ),
                campaign_layout,
                label="attempt-005 final",
            )
        final_state = probe_state(None)
        canon.require_clean_state(final_state, "campaign final state")
        require_same_sources(
            sources, source_evidence(campaign_layout), "campaign final audit"
        )
        if len(completed) != len(specs):
            raise CampaignError("completed pair count drift")
        final_audit = []
        carried_attempt4_audit = (
            verify_attempt4_preserved_evidence(campaign_layout)
            if resume_attempt_004
            else None
        )
        for index, (spec, prior) in enumerate(zip(specs, completed), start=1):
            schedule = pair_run_schedule(
                index,
                resume_attempt_001,
                resume_attempt_002,
                resume_attempt_003,
                resume_attempt_004,
            )
            canon.require_recipe_unchanged(spec)
            canon.require_fixtures_unchanged(spec, campaign_layout)
            if resume_attempt_004 and index <= 9:
                if carried_attempt4_audit is None:
                    raise CampaignError("attempt-005 carried audit is absent")
                audited = carried_attempt4_audit["pairs"][index]
                pair_source = carried_attempt4_audit["pair_sources"][index]
                audit_campaign_id = pair_source["source_campaign_id"]
                audit_log = Path(pair_source["manager_log"])
                audit_disposition = "CARRIED_FORWARD"
            elif resume_attempt_003 and index == 1:
                carried_audit = verify_attempt3_preserved_evidence(
                    campaign_layout
                )
                audited = carried_audit["pair1"]
                audit_campaign_id = RESUME_CAMPAIGN_ID
                audit_log = attempt2_pair_log_path(campaign_layout)
                audit_disposition = "CARRIED_FORWARD"
            elif resume_attempt_003 and index == 2:
                carried_audit = verify_attempt3_preserved_evidence(
                    campaign_layout
                )
                audited = carried_audit["pair2"]
                audit_campaign_id = RESUME_ATTEMPT2_CAMPAIGN_ID
                audit_log = attempt3_pair2_log_path(campaign_layout)
                audit_disposition = "CARRIED_FORWARD"
            elif resume_attempt_002 and index == 1:
                carried_audit = verify_attempt2_preserved_evidence(
                    campaign_layout
                )
                audited = carried_audit["pair"]
                audit_campaign_id = RESUME_CAMPAIGN_ID
                audit_log = attempt2_pair_log_path(campaign_layout)
                audit_disposition = "CARRIED_FORWARD"
            else:
                audited = verify_pair(
                    spec,
                    index,
                    campaign_id,
                    sources,
                    pair_log_path(spec, index, campaign_id, campaign_layout),
                    campaign_layout,
                    cold_snapshot=prior["pair"]["cold"],
                    cold_run_number=schedule["cold_run_number"],
                    cold_config_run_count=schedule["cold_config_run_count"],
                    warm_run_number=schedule["warm_run_number"],
                    warm_config_run_count=schedule["warm_config_run_count"],
                    allowed_run_numbers=schedule["allowed_run_numbers"],
                    expected_completion_timeout_s=schedule.get(
                        "completion_timeout_s"
                    ),
                    cold_artifact_index=schedule["cold_artifact_index"],
                    warm_artifact_index=schedule["warm_artifact_index"],
                    allowed_artifact_indices=schedule["allowed_artifact_indices"],
                )
                audit_campaign_id = campaign_id
                audit_log = pair_log_path(
                    spec, index, campaign_id, campaign_layout
                )
                audit_disposition = "EXECUTED"
            if audited != prior["pair"]:
                raise CampaignError(f"{spec.name} evidence changed before completion")
            final_audit.append(
                {
                    "pair_index": index,
                    "recipe": spec.name,
                    "disposition": audit_disposition,
                    "source_campaign_id": audit_campaign_id,
                    "manager_log": str(audit_log),
                    "cold_receipt_sha256": audited["cold"]["receipt_sha256"],
                    "warm_receipt_sha256": audited["warm"]["receipt_sha256"],
                    "cold_artifact_sha256": audited["cold"]["artifact"]["sha256"],
                    "warm_artifact_sha256": audited["warm"]["artifact"]["sha256"],
                    "manager_log_sha256": audited["final_manager_log"]["log"]["sha256"],
                }
            )
        final_preserved_attempt1 = None
        final_preserved_attempt2 = None
        final_preserved_attempt3 = None
        final_preserved_attempt4 = None
        if resume_attempt_001:
            final_preserved_attempt1 = verify_failed_attempt_evidence(
                sources,
                campaign_layout,
                require_alias_run1=False,
            )
        elif resume_attempt_002:
            final_preserved_attempt2 = verify_attempt2_preserved_evidence(
                campaign_layout
            )
        elif resume_attempt_003:
            final_preserved_attempt3 = verify_attempt3_preserved_evidence(
                campaign_layout
            )
        elif resume_attempt_004:
            final_preserved_attempt4 = verify_attempt4_preserved_evidence(
                campaign_layout
            )
        if resume_attempt_004 and (
            ledger.ledger_sequence != 87 or ledger.campaign_sequence != 22
        ):
            raise CampaignError(
                "attempt-005 completion boundary must be ledger 87/campaign sequence 22"
            )
        completion_record = ledger.append(
            "campaign_completed",
            {
                "status": "COMPLETE",
                "pair_count": len(completed),
                "logical_cell_count": 14,
                "actual_execution_count": 4 if resume_attempt_004 else (18 if resume_attempt_003 else (20 if resume_attempt_002 else 22)),
                "new_execution_count": 4 if resume_attempt_004 else (18 if resume_attempt_003 else (20 if resume_attempt_002 else 22)),
                "study_leg_count": 22,
                "orphan_historical_cold_count": 1 if (resume_attempt_002 or resume_attempt_003 or resume_attempt_004) else 0,
                "valid_orphan_historical_cold_count": 1 if resume_attempt_004 else 0,
                "failed_historical_execution_count": 1 if resume_attempt_004 else 0,
                "evidence_execution_count": 24 if resume_attempt_004 else (23 if (resume_attempt_002 or resume_attempt_003) else 22),
                "carried_pair_count": 9 if resume_attempt_004 else (2 if resume_attempt_003 else (1 if resume_attempt_002 else 0)),
                "executed_pair_count": 2 if resume_attempt_004 else (9 if resume_attempt_003 else (10 if resume_attempt_002 else 11)),
                "pairs": completed,
                "final_state": final_state,
                "final_evidence_audit": final_audit,
                "preserved_attempt1": (
                    failed_attempt_evidence_summary(final_preserved_attempt1)
                    if final_preserved_attempt1 is not None
                    else None
                ),
                "preserved_attempt2": (
                    attempt2_evidence_summary(final_preserved_attempt2)
                    if final_preserved_attempt2 is not None
                    else None
                ),
                "preserved_attempt3": (
                    attempt3_evidence_summary(final_preserved_attempt3)
                    if final_preserved_attempt3 is not None
                    else None
                ),
                "preserved_attempt4": (
                    attempt4_evidence_summary(final_preserved_attempt4)
                    if final_preserved_attempt4 is not None
                    else None
                ),
                "recovery_receipt": recovery if recovery is not None else (
                    recovery2["recovery2"] if recovery2 is not None else (
                        recovery3["recovery3"] if recovery3 is not None else (
                            recovery4["recovery4"] if recovery4 is not None else None
                        )
                    )
                ),
                "operator_logs": (
                    operator_transport["contract"]
                    if operator_transport is not None
                    else None
                ),
                "quality_judgment": "PENDING_HUMAN",
            },
        )
        if resume_attempt_004 and (
            completion_record.get("ledger_sequence") != 88
            or completion_record.get("campaign_sequence") != 23
        ):
            raise CampaignError("attempt-005 terminal lifecycle identity drifted")
        return {
            "status": "COMPLETE",
            "campaign_id": campaign_id,
            "pairs": completed,
            "carried_pair_count": 9 if resume_attempt_004 else (2 if resume_attempt_003 else (1 if resume_attempt_002 else 0)),
            "new_execution_count": 4 if resume_attempt_004 else (18 if resume_attempt_003 else (20 if resume_attempt_002 else 22)),
            "valid_orphan_historical_cold_count": 1 if resume_attempt_004 else 0,
            "failed_historical_execution_count": 1 if resume_attempt_004 else 0,
            "lifecycle": str(campaign_layout.lifecycle),
        }
    except Exception as exc:
        cleanup_identity = owned_server
        try:
            failure_state = probe_state(cleanup_identity)
            if cleanup_identity is None:
                cleanup_identity = canon.pending_child_owned_server(
                    pending_cold,
                    failure_state,
                    campaign_layout,
                    validate_server_argv,
                    expected_server_argv,
                )
                if cleanup_identity is not None:
                    failure_state = probe_state(cleanup_identity)
        except Exception as state_exc:
            failure_state = {
                "probe_error": f"{type(state_exc).__name__}: {state_exc}"
            }
        cleanup: dict[str, Any] = {"attempted": False}
        if (
            cleanup_identity is not None
            and failure_state.get("server_pid_receipt")
            == cleanup_identity.get("serving_pid")
            and failure_state.get("listener_pids_8199")
            == [cleanup_identity.get("serving_pid")]
            and failure_state.get("expected_server_identity_live") is True
            and failure_state.get("gpu_lock_exists") is False
            and failure_state.get("suite_lock_exists") is False
        ):
            cleanup = {"attempted": True}
            try:
                cleanup["run_recipe_shutdown_result"] = cleanup_owned_server()
                cleanup["post_cleanup_state"] = probe_state(cleanup_identity)
                canon.require_clean_state(
                    cleanup["post_cleanup_state"], "failure cleanup final state"
                )
                cleanup["success"] = True
            except Exception as cleanup_exc:
                cleanup["success"] = False
                cleanup["error"] = (
                    f"{type(cleanup_exc).__name__}: {cleanup_exc}"
                )
        carried_count = sum(
            row.get("status") == "CARRIED_FORWARD" for row in completed
        )
        ledger.append(
            "campaign_failed",
            {
                "status": "FAILED",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "completed_pair_count": len(completed),
                "carried_pair_count": carried_count,
                "new_verified_pair_count": len(completed) - carried_count,
                "resume_attempt_001": resume_attempt_001,
                "resume_attempt_002": resume_attempt_002,
                "resume_attempt_003": resume_attempt_003,
                "resume_attempt_004": resume_attempt_004,
                "failure_state": failure_state,
                "pending_cold_child_outcome": (
                    pending_cold.as_dict() if pending_cold is not None else None
                ),
                "owned_server_cleanup": cleanup,
                "stopped_without_force_or_additional_render": True,
            },
        )
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        help="execute the selected fail-closed campaign; default prints its runbook",
    )
    parser.add_argument("--campaign-id")
    recovery_group = parser.add_mutually_exclusive_group()
    recovery_group.add_argument(
        "--resume-attempt-001",
        action="store_true",
        help=(
            "resume the preserved failed attempt using run2 cold/run3 warm for "
            "the control; requires the exact attempt-002 campaign id and recovery receipt"
        ),
    )
    recovery_group.add_argument(
        "--resume-attempt-002",
        action="store_true",
        help=(
            "carry the fully verified attempt-002 pair1 into the exact attempt-003 "
            "campaign and execute only pairs 2-11"
        ),
    )
    recovery_group.add_argument(
        "--resume-attempt-003",
        action="store_true",
        help=(
            "carry fully verified pairs 1 and 2 into the exact attempt-004 "
            "campaign and execute only pairs 3-11"
        ),
    )
    recovery_group.add_argument(
        "--resume-attempt-004",
        action="store_true",
        help=(
            "carry fully verified pairs 1 through 9 into the exact attempt-005 "
            "campaign and execute only pairs 10 and 11"
        ),
    )
    parser.add_argument("--operator-stdout-log")
    parser.add_argument("--operator-stderr-log")
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    campaign_layout: canon.Layout = DEFAULT_LAYOUT,
) -> int:
    args = parse_args(argv)
    if not args.run:
        dry_id = validate_campaign_id(args.campaign_id or "DRY-RUN")
        print(
            json.dumps(
                runbook(
                    dry_id,
                    campaign_layout,
                    resume_attempt_001=args.resume_attempt_001,
                    resume_attempt_002=args.resume_attempt_002,
                    resume_attempt_003=args.resume_attempt_003,
                    resume_attempt_004=args.resume_attempt_004,
                ),
                indent=2,
            )
        )
        return 0
    if not (
        args.resume_attempt_001
        or args.resume_attempt_002
        or args.resume_attempt_003
        or args.resume_attempt_004
    ):
        print(
            "[H3 MUSIC CAMPAIGN FAILED] CampaignError: the current lab has "
            "preserved recovery evidence; execution requires one exact resume mode",
            file=sys.stderr,
        )
        return 1
    try:
        result = execute_campaign(
            campaign_id=args.campaign_id,
            campaign_layout=campaign_layout,
            resume_attempt_001=args.resume_attempt_001,
            resume_attempt_002=args.resume_attempt_002,
            resume_attempt_003=args.resume_attempt_003,
            resume_attempt_004=args.resume_attempt_004,
            operator_stdout_log=args.operator_stdout_log,
            operator_stderr_log=args.operator_stderr_log,
        )
    except Exception as exc:
        print(f"[H3 MUSIC CAMPAIGN FAILED] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
