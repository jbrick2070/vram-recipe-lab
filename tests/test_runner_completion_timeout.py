import ast
import unittest
from pathlib import Path

import run_recipe


class CompletionTimeoutParserTests(unittest.TestCase):
    def test_default_preserves_legacy_completion_window(self):
        self.assertEqual(run_recipe.DEFAULT_COMPLETION_TIMEOUT_S, 1800)
        self.assertEqual(run_recipe.MAX_COMPLETION_TIMEOUT_S, 7200)
        self.assertEqual(
            run_recipe.parse_completion_timeout_s(
                ["run_recipe.py", "recipes/example.json"]
            ),
            1800,
        )

    def test_explicit_positive_integer_accepts_inclusive_bounds(self):
        for value in (1, 3600, 7200):
            with self.subTest(value=value):
                self.assertEqual(
                    run_recipe.parse_completion_timeout_s(
                        [
                            "run_recipe.py",
                            "recipes/example.json",
                            run_recipe.COMPLETION_TIMEOUT_FLAG,
                            str(value),
                        ]
                    ),
                    value,
                )

    def test_flag_may_be_supplied_only_once(self):
        with self.assertRaisesRegex(ValueError, "only once"):
            run_recipe.parse_completion_timeout_s(
                [
                    "run_recipe.py",
                    "recipes/example.json",
                    run_recipe.COMPLETION_TIMEOUT_FLAG,
                    "3600",
                    run_recipe.COMPLETION_TIMEOUT_FLAG,
                    "5400",
                ]
            )

    def test_missing_or_noncanonical_values_fail_closed(self):
        invalid_argv = (
            ["run_recipe.py", "recipes/example.json", run_recipe.COMPLETION_TIMEOUT_FLAG],
            [
                "run_recipe.py",
                "recipes/example.json",
                run_recipe.COMPLETION_TIMEOUT_FLAG,
                "--shutdown",
            ],
            [
                "run_recipe.py",
                "recipes/example.json",
                run_recipe.COMPLETION_TIMEOUT_FLAG,
                "0",
            ],
            [
                "run_recipe.py",
                "recipes/example.json",
                run_recipe.COMPLETION_TIMEOUT_FLAG,
                "-1",
            ],
            [
                "run_recipe.py",
                "recipes/example.json",
                run_recipe.COMPLETION_TIMEOUT_FLAG,
                "+1",
            ],
            [
                "run_recipe.py",
                "recipes/example.json",
                run_recipe.COMPLETION_TIMEOUT_FLAG,
                "01",
            ],
            [
                "run_recipe.py",
                "recipes/example.json",
                run_recipe.COMPLETION_TIMEOUT_FLAG,
                "1.0",
            ],
            [
                "run_recipe.py",
                "recipes/example.json",
                run_recipe.COMPLETION_TIMEOUT_FLAG,
                "7201",
            ],
            [
                "run_recipe.py",
                "recipes/example.json",
                f"{run_recipe.COMPLETION_TIMEOUT_FLAG}=3600",
            ],
        )
        for argv in invalid_argv:
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                run_recipe.parse_completion_timeout_s(argv)


class CompletionTimeoutWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(run_recipe.__file__).read_text(encoding="utf-8")
        module = ast.parse(cls.source)
        cls.main_node = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )

    def dict_assignment(self, target_name):
        for node in ast.walk(self.main_node):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
                continue
            if any(
                isinstance(target, ast.Name) and target.id == target_name
                for target in node.targets
            ):
                return {
                    key.value: value
                    for key, value in zip(node.value.keys, node.value.values)
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
        self.fail(f"main() has no dictionary assignment for {target_name}")

    def test_selected_timeout_is_identity_bound_and_recorded_in_schema_v3_receipt(self):
        self.assertEqual(run_recipe.RECEIPT_SCHEMA_VERSION, 3)
        for assignment_name in ("identity_payload", "res_payload"):
            with self.subTest(assignment=assignment_name):
                value = self.dict_assignment(assignment_name).get(
                    "completion_timeout_s"
                )
                self.assertIsInstance(value, ast.Name)
                self.assertEqual(value.id, "completion_timeout_s")

    def test_poll_loop_and_timeout_status_use_selected_value(self):
        self.assertNotIn("RUNNER_COMPLETION_TIMEOUT_S", self.source)
        self.assertIn(
            "while time.time() - start_time < completion_timeout_s:", self.source
        )
        self.assertIn(
            'f"TIMEOUT (exceeded {completion_timeout_s}s; owned server shutdown proved)"',
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
