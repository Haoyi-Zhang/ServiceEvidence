"""Portable gates for the fresh Linux workflow; not a durable timing result."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_durable_workflow_mws", ROOT / "scripts/verify_durable_workflow_mws.py")
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class DurableWorkflowContractTests(unittest.TestCase):
    def test_fresh_bounded_job_preserves_existing_checks(self):
        workflow = (ROOT / ".github/workflows/scientific-checks.yml").read_text(
            encoding="utf-8")
        job = workflow.split("  durable-mws-workflow:\n", 1)[1].split(
            "  bounded-science:\n", 1)[0]
        self.assertIn("runs-on: ubuntu-24.04", job)
        self.assertIn("timeout-minutes: 8", job)
        self.assertIn('$RUNNER_TEMP/p024-durable-mws-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}', job)
        self.assertIn('[[ -e "$out" || -e "$logs" ]]', job)
        self.assertIn('experiments/workflow_mws.py --persistence durable --out "$DURABLE_MWS_OUT"', job)
        self.assertIn('scripts/verify_durable_workflow_mws.py --out "$DURABLE_MWS_OUT"', job)
        self.assertIn("timeout 240s", job)
        self.assertIn("timeout 90s", job)
        self.assertIn("if: always()", job)
        self.assertIn("${{ env.DURABLE_MWS_OUT }}/", job)
        self.assertIn("${{ env.DURABLE_MWS_LOGS }}/", job)
        self.assertNotIn("pip install", job)
        self.assertIn("  focused-regressions:", workflow)
        self.assertIn("bash scripts/check_all.sh", workflow)
        self.assertIn("scripts/verify_workflow_mws.py --root results/primary-mws-20261014", workflow)

    def test_volatile_output_is_not_durable_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "summary.json").write_text(
                json.dumps({"durable_service_costs_measured": False}), encoding="utf-8")
            with self.assertRaisesRegex((AssertionError, ValueError), "durable"):
                VERIFIER.verify(out)

    def test_changed_source_binding_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            for name, obj in (
                ("summary.json", {"durable_service_costs_measured": True, "source_unchanged": True}),
                ("source-before.json", {"a": "before"}),
                ("source-after.json", {"a": "after"}),
            ):
                (out / name).write_text(json.dumps(obj), encoding="utf-8")
            with self.assertRaisesRegex((AssertionError, ValueError), "source"):
                VERIFIER.verify(out)


if __name__ == "__main__":
    unittest.main()
