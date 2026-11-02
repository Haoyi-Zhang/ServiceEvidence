"""Bounded main/supplement consumer controls; no TeX or campaigns are run."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT.parent / "paper"
CHECKER = ROOT / "scripts/check_paper_assets.py"
TIMINGS = r"\EqualPeerTime{}, \EqualQuorumTime{}, \EqualCentralTime{}"
INPUTS = (
    "main.tex", "supplement.tex", "supplement-content.tex", "authors.tex",
    "tables/equal-work.tex", "tables/equal-ranges.tex",
    "tables/measured-values.tex", "tables/generated-summary.json",
)
sys.path.insert(0, str(ROOT / "scripts"))
import check_paper_assets as gate


@unittest.skipUnless(all((PAPER / name).is_file() for name in INPUTS),
                     "Full paper/artifact packet required for manuscript integration checks")
class PaperAssetGateTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        paper = Path(temporary.name) / "paper"
        for name in INPUTS:
            target = paper / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PAPER / name, target)
        return paper

    def check(self, paper):
        return subprocess.run(
            [sys.executable, "-B", str(CHECKER), "--paper-dir", str(paper)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15,
        )

    def replace(self, paper, name, old, new):
        path = paper / name
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), encoding="utf-8")

    def test_current_supplement_timing_consumer_passes_read_only(self):
        result = self.check(PAPER)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_discussion_can_move_to_main_without_duplicate_timings(self):
        paper = self.fixture()
        self.replace(paper, "supplement-content.tex", TIMINGS, "timings moved")
        self.replace(paper, "main.tex", r"\end{document}", TIMINGS + "\n" + r"\end{document}")
        result = self.check(paper)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_stale_literal_in_supplement_is_rejected(self):
        paper = self.fixture()
        self.replace(paper, "supplement-content.tex", r"\EqualPeerTime{}", "9.99")
        result = self.check(paper)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no live main/supplement timing use of EqualPeerTime", result.stderr)

    def test_commented_out_macro_does_not_rescue_stale_literal(self):
        paper = self.fixture()
        self.replace(paper, "supplement-content.tex", TIMINGS, "9.99, 8.88, 7.77")
        self.replace(paper, "main.tex", r"\end{document}", "% " + TIMINGS + "\n" + r"\end{document}")
        self.assertNotEqual(self.check(paper).returncode, 0)

    def test_detached_supplement_content_is_not_a_live_consumer(self):
        paper = self.fixture()
        self.replace(paper, "supplement.tex", r"\input{supplement-content.tex}", "% detached")
        result = self.check(paper)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no live main/supplement timing use", result.stderr)

    def test_consumer_must_import_generated_macros(self):
        paper = self.fixture()
        self.replace(paper, "supplement.tex", r"\input{tables/measured-values.tex}", "% detached")
        result = self.check(paper)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("without generated measured-values input", result.stderr)

    def test_local_macro_override_cannot_hide_stale_prose(self):
        paper = self.fixture()
        self.replace(paper, "supplement-content.tex", TIMINGS,
                     r"\renewcommand{\EqualPeerTime}{9.99}" + "\n" + TIMINGS)
        result = self.check(paper)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("redefines generated timing macro EqualPeerTime", result.stderr)

    def test_numeric_macro_validation_still_rejects_stale_value(self):
        paper = self.fixture()
        self.replace(paper, "tables/measured-values.tex",
                     r"\newcommand{\EqualPeerTime}{2.55}",
                     r"\newcommand{\EqualPeerTime}{9.99}")
        result = self.check(paper)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("measured macro differs for EqualPeerTime", result.stderr)


class PortableTimingConsumerTests(unittest.TestCase):
    """Exercise the source gate in artifact-only CI with tiny owned fixtures."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.paper = Path(temporary.name)
        self.write("main.tex", r"\input{tables/measured-values.tex}")
        self.write("supplement.tex", r"\input{tables/measured-values.tex}" + "\n"
                   + r"\input{supplement-content.tex}")
        self.write("supplement-content.tex", TIMINGS)

    def write(self, name, text):
        (self.paper / name).write_text(text, encoding="utf-8")

    def test_live_supplement_timing_use(self):
        gate.validate_timing_consumers(self.paper)

    def test_timing_use_can_move_to_main(self):
        self.write("main.tex", r"\input{tables/measured-values.tex}" + "\n" + TIMINGS)
        self.write("supplement-content.tex", "")
        gate.validate_timing_consumers(self.paper)

    def test_each_stale_literal_is_rejected(self):
        for macro in ("EqualPeerTime", "EqualQuorumTime", "EqualCentralTime"):
            self.write("supplement-content.tex", TIMINGS.replace("\\" + macro + "{}", "9.99"))
            with self.subTest(macro=macro), self.assertRaisesRegex(ValueError, "no live.*" + macro):
                gate.validate_timing_consumers(self.paper)

    def test_comments_do_not_supply_timing_uses(self):
        self.write("supplement-content.tex", "% " + TIMINGS + "\n9.99, 8.88, 7.77")
        with self.assertRaisesRegex(ValueError, "no live"):
            gate.validate_timing_consumers(self.paper)

    def test_detached_content_is_not_live(self):
        self.write("supplement.tex", r"\input{tables/measured-values.tex}")
        with self.assertRaisesRegex(ValueError, "no live"):
            gate.validate_timing_consumers(self.paper)

    def test_generated_macro_import_is_required(self):
        self.write("supplement.tex", r"\input{supplement-content.tex}")
        with self.assertRaisesRegex(ValueError, "without generated"):
            gate.validate_timing_consumers(self.paper)

    def test_local_timing_override_is_rejected(self):
        self.write("supplement-content.tex", r"\renewcommand{\EqualPeerTime}{9.99}" + "\n" + TIMINGS)
        with self.assertRaisesRegex(ValueError, "redefines generated"):
            gate.validate_timing_consumers(self.paper)


if __name__ == "__main__":
    unittest.main()
