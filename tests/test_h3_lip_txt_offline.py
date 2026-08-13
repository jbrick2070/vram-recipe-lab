import hashlib
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

import numpy as np

from scratch import build_h3_lip_txt_campaign as candidates
from scratch import h3_lip_txt_common as common
from scratch import h3_lip_txt_window as window
from scratch import package_h3_lip_txt_review as review


def fake_transcript_receipt() -> dict:
    text = "A deliberately canonical test transcript."
    return {
        "receipt_path": "fixtures/audio_receipts/tts_dialogue_h3_target_window_transcript.json",
        "receipt_sha256": "a" * 64,
        "transcript": {
            "verbatim_utf8": text,
            "utf8_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        },
    }


class H3LipTxtWindowTests(unittest.TestCase):
    def test_full_source_scan_finds_known_offset_with_two_representations(self):
        rng = np.random.default_rng(20260812)
        target = rng.normal(0.0, 0.1, common.TARGET_SAMPLES)
        source = rng.normal(0.0, 0.02, common.SOURCE_SAMPLES)
        start = 44_100
        source[start : start + common.TARGET_SAMPLES] = target

        analysis = window.analyze_arrays(source, target)

        self.assertEqual(analysis["machine_alignment_status"], "UNAMBIGUOUS_MACHINE")
        self.assertEqual(analysis["selected_window"]["start_sample"], start)
        self.assertEqual(
            analysis["selected_window"]["end_sample"],
            start + common.TARGET_SAMPLES,
        )
        self.assertGreaterEqual(
            analysis["block_support"]["distributed_support_count"],
            window.MIN_DISTRIBUTED_BLOCKS,
        )

    def test_near_tied_nonoverlap_peak_is_machine_ambiguous(self):
        scores = np.array([0.91, 0.20, 0.87], dtype=np.float64)
        starts = np.array([0, 10_000, 50_000], dtype=np.int64)

        summary = window.representation_summary("test", scores, starts)

        self.assertFalse(summary["machine_pass"])
        self.assertTrue(
            any("top-minus-second" in reason for reason in summary["machine_failure_reasons"])
        )

    def test_envelope_scans_the_exact_last_legal_source_start(self):
        rng = np.random.default_rng(20260813)
        target = rng.normal(0.0, 0.1, common.TARGET_SAMPLES)
        source = rng.normal(0.0, 0.02, common.SOURCE_SAMPLES)
        start = common.SOURCE_MAX_START_SAMPLE
        source[start : start + common.TARGET_SAMPLES] = target

        analysis = window.analyze_arrays(source, target)

        self.assertEqual(analysis["envelope"]["score_count"], start + 1)
        self.assertEqual(analysis["envelope"]["best_start_sample"], start)
        self.assertEqual(analysis["selected_window"]["start_sample"], start)

    def test_transcript_bytes_are_literal_nfc_utf8_without_terminal_newline(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "transcript.txt"
            path.write_bytes("Caf\u00e9 speaks.".encode("utf-8"))
            text, raw = common.read_canonical_transcript(path)
            self.assertEqual(text, "Caf\u00e9 speaks.")
            self.assertEqual(raw, text.encode("utf-8"))

            path.write_bytes(b"with newline\n")
            with self.assertRaisesRegex(common.H3LipTxtError, "terminal newline"):
                common.read_canonical_transcript(path)

            path.write_bytes(b"\xef\xbb\xbfno bom")
            with self.assertRaisesRegex(common.H3LipTxtError, "without BOM"):
                common.read_canonical_transcript(path)

    def test_immutable_writer_is_idempotent_and_refuses_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "receipt.json"
            self.assertTrue(common.write_immutable(path, b"{\"ok\":true}\n"))
            self.assertFalse(common.write_immutable(path, b"{\"ok\":true}\n"))
            with self.assertRaisesRegex(common.H3LipTxtError, "already differs"):
                common.write_immutable(path, b"{}\n")

    def test_certifier_revalidates_analysis_before_any_immutable_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "receipt.json"
            with mock.patch.object(
                window,
                "validate_analysis",
                side_effect=window.WindowError("forged analysis"),
            ):
                with self.assertRaisesRegex(window.WindowError, "forged analysis"):
                    window.write_final_receipt(
                        Path(temporary) / "analysis.json",
                        receipt,
                        transcript_path=None,
                        reviewer=None,
                        reviewed_at=None,
                        ear_confirmation=None,
                        confidence=None,
                        stop=True,
                    )
            self.assertFalse(receipt.exists())

    def test_transcript_receipt_validator_requires_complete_human_record(self):
        review = {
            "verdict": "confirmed_ordered_words_and_pauses",
            "reviewer": "Jeffrey",
            "reviewed_at": "2026-08-12T00:00:00-07:00",
            "method": "ear confirmation",
            "confirmation": "ordered words and pauses confirmed",
            "confidence": 0.95,
        }
        window.validate_human_review(review)
        for field in ("reviewer", "reviewed_at", "method", "confirmation"):
            broken = dict(review)
            broken[field] = ""
            with self.assertRaisesRegex(window.WindowError, "nonblank"):
                window.validate_human_review(broken)
        broken = dict(review)
        broken["confidence"] = 1.1
        with self.assertRaisesRegex(window.WindowError, "confidence"):
            window.validate_human_review(broken)


class H3LipTxtCandidateTests(unittest.TestCase):
    def test_candidate_is_same_seed_prompt_only(self):
        receipt = fake_transcript_receipt()
        candidate = candidates.build_candidate(42, receipt)
        control, _, _ = candidates._load_hash_pinned_control(42)

        self.assertEqual(
            candidates.exact.difference_paths(control["prompt"], candidate["prompt"]),
            {"7.inputs.prompt"},
        )
        self.assertIn(receipt["transcript"]["verbatim_utf8"], candidate["prompt"]["7"]["inputs"]["prompt"])
        self.assertEqual(candidate["prompt"]["7"]["inputs"]["ref_image_size"], "match")
        self.assertEqual(
            candidates.exact.source_consumers(candidate["prompt"], "16"),
            {("7", "ref_audios.ref_audio_0")},
        )

    def test_pair_writer_is_canonical_idempotent_and_rejects_drift(self):
        receipt = fake_transcript_receipt()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            with mock.patch.object(window, "validate_transcript_receipt", return_value=receipt):
                first = candidates.write_pair(Path("ignored.json"), output)
                self.assertEqual(set(first), set(candidates.CANDIDATE_NAME_BY_SEED.values()))
                self.assertTrue(all(first.values()))
                second = candidates.write_pair(Path("ignored.json"), output)
                self.assertFalse(any(second.values()))
            seed42 = output / f"{candidates.CANDIDATE_NAME_BY_SEED[42]}.json"
            self.assertFalse(seed42.read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertNotIn(b"\r\n", seed42.read_bytes())
            seed42.write_bytes(b"{}\n")
            with mock.patch.object(window, "validate_transcript_receipt", return_value=receipt):
                with self.assertRaisesRegex(common.H3LipTxtError, "already differs"):
                    candidates.write_pair(Path("ignored.json"), output)

    def test_cross_seed_candidate_graph_diff_is_seed_and_existing_prefix_only(self):
        receipt = fake_transcript_receipt()
        seed42 = candidates.build_candidate(42, receipt)
        seed43 = candidates.build_candidate(43, receipt)
        self.assertEqual(
            candidates.exact.difference_paths(seed42["prompt"], seed43["prompt"]),
            {"5.inputs.noise_seed", "12.inputs.filename_prefix"},
        )


class H3LipTxtReviewTests(unittest.TestCase):
    def test_review_mux_is_stream_copy_with_exact_target_span(self):
        command = review.build_mux_command(
            Path("machine.mp4"), Path("source_window.wav"), Path("review.mov")
        )
        self.assertEqual(command[command.index("-c:v") + 1], "copy")
        self.assertEqual(command[command.index("-c:a") + 1], "pcm_s16le")
        self.assertEqual(
            command[command.index("-t") + 1],
            f"{common.TARGET_SAMPLES / common.SAMPLE_RATE_HZ:.9f}",
        )
        self.assertIn("source_window.wav", command)

    def test_shared_runner_bundle_rejects_any_bundle_drift(self):
        baseline = {
            "runner_sha256": "runner",
            "comfyui_git_commit": "commit",
            "server_argv": ["main.py", "--port", "8199"],
            "model_fingerprints": {"model": {"bytes": 1}},
            "lab_locks_sha256": "locks",
            "timestamp": "2026-08-12T00:00:00Z",
        }
        control = {
            "receipt": "results/h3_r2v_refaudio_tts_lipsync_exact_seed42_run2.json",
            "receipt_sha256": "receipt42",
            "artifact_sha256": "artifact42",
        }
        takes = []
        for role, seed in review.ROLE_SPECS:
            takes.append(
                {
                    "role": role,
                    "seed": seed,
                    "recipe": review.ROLE_SPECS[(role, seed)],
                    "run_receipt": (
                        control["receipt"]
                        if role == "native" and seed == 42
                        else f"results/{role}_{seed}_run1.json"
                    ),
                    "run_receipt_sha256": (
                        control["receipt_sha256"]
                        if role == "native" and seed == 42
                        else f"receipt-{role}-{seed}"
                    ),
                    "artifact_sha256": (
                        control["artifact_sha256"]
                        if role == "native" and seed == 42
                        else f"artifact-{role}-{seed}"
                    ),
                    "receipt": dict(baseline),
                }
            )
        for take in takes:
            if take["role"] != "native" or take["seed"] != 42:
                take["receipt"]["timestamp"] = "2026-08-12T00:00:01Z"
        transcript = {"fresh_native_control": control}
        self.assertEqual(
            review.validate_shared_runner_bundle(takes, transcript),
            {field: baseline[field] for field in review.BUNDLE_FIELDS},
        )
        takes[-1]["receipt"]["runner_sha256"] = "different"
        with self.assertRaisesRegex(review.ReviewError, "Runner bundle differs"):
            review.validate_shared_runner_bundle(takes, transcript)

    def test_source_window_extraction_is_sample_exact_without_gpu(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "source_window.wav"
            digest, command = review.extract_source_window(
                0, common.TARGET_SAMPLES, output
            )
            self.assertEqual(digest, common.sha256_file(output))
            self.assertIn(
                "atrim=start_sample=0:end_sample=227850",
                command[command.index("-af") + 1],
            )
            with wave.open(str(output), "rb") as handle:
                self.assertEqual(handle.getframerate(), common.SAMPLE_RATE_HZ)
                self.assertEqual(handle.getnframes(), common.TARGET_SAMPLES)


if __name__ == "__main__":
    unittest.main()
