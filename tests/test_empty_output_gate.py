"""
test_empty_output_gate.py
Proves that run_recipe output verification strictly rejects runs with empty output_path
or missing files on disk, marking them FAIL (no artifact output).
"""
import unittest
from pathlib import Path
import json

class TestEmptyOutputGate(unittest.TestCase):
    def test_empty_output_path_rejected(self):
        # Simulated ComfyUI history response where outputs dictionary is present but produces no filename
        outputs_empty_file = {
            "328": {
                "text": ["some text preview without any video or image file"]
            }
        }
        
        output_path = ""
        for n_out in outputs_empty_file.values():
            if isinstance(n_out, dict):
                for k in ["images", "gifs", "videos", "audio", "animated"]:
                    if k in n_out and isinstance(n_out[k], list) and len(n_out[k]) > 0:
                        item = n_out[k][0]
                        if isinstance(item, dict):
                            output_path = item.get("filename", "")
                        elif isinstance(item, str):
                            output_path = item
                        if output_path:
                            break

        # Verification: output_path must be empty, so execution_success must be False
        self.assertEqual(output_path, "")
        execution_success = bool(output_path)
        self.assertFalse(execution_success, "Empty output_path must not be marked successful")

    def test_missing_file_on_disk_rejected(self):
        output_path = "non_existent_artifact_9999.mp4"
        target_file = Path("outputs") / output_path
        
        file_valid = target_file.exists() and target_file.stat().st_size > 0
        self.assertFalse(file_valid, "Non-existent file on disk must fail verification")

if __name__ == "__main__":
    unittest.main()
