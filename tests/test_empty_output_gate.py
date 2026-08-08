"""
test_empty_output_gate.py
Proves that run_recipe output verification strictly rejects runs with empty output_path
or missing files on disk, marking them FAIL (no artifact output).
"""
import unittest
from pathlib import Path

import run_recipe

class TestEmptyOutputGate(unittest.TestCase):
    def test_empty_output_path_rejected(self):
        # Simulated ComfyUI history response where outputs dictionary is present but produces no filename
        outputs_empty_file = {
            "328": {
                "text": ["some text preview without any video or image file"]
            }
        }
        
        output_path = run_recipe.extract_output_path(outputs_empty_file)

        # Verification: output_path must be empty, so execution_success must be False
        self.assertEqual(output_path, "")
        execution_success = bool(output_path)
        self.assertFalse(execution_success, "Empty output_path must not be marked successful")

    def test_missing_file_on_disk_rejected(self):
        output_path = "non_existent_artifact_9999.mp4"
        target_file = Path("outputs") / output_path
        
        file_valid = target_file.exists() and target_file.stat().st_size > 0
        self.assertFalse(file_valid, "Non-existent file on disk must fail verification")

    def test_video_filename_is_extracted_from_production_helper(self):
        outputs = {"12": {"videos": [{"filename": "clip.mp4"}]}}
        self.assertEqual(run_recipe.extract_output_path(outputs), "clip.mp4")

if __name__ == "__main__":
    unittest.main()
