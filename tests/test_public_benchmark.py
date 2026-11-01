import csv
from dataclasses import replace
from pathlib import Path
import unittest

from cie.model import Vote
from cie.public_benchmark import (
    Observation,
    conservative_vote,
    endpoint_only_vote,
    load_observations,
    pair_decisions,
    summarize,
    wilson_interval,
)

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "external_inputs" / "ooni_dual_vantage_targets.csv"


class PublicTargetBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observations = load_observations(INPUT)

    def test_frozen_dimensions_and_vantage_pairs(self):
        self.assertEqual(len(self.observations), 24)
        self.assertEqual(len({row.case_id for row in self.observations}), 12)
        self.assertEqual(len({row.target_id for row in self.observations}), 11)
        for case in {row.case_id for row in self.observations}:
            selected = [row for row in self.observations if row.case_id == case]
            self.assertEqual(len(selected), 2)
            self.assertEqual({row.vantage for row in selected}, {"probe", "control"})

    def test_minimized_extraction_does_not_infer_missing_side_fields(self):
        by_id = {row.observation_id: row for row in self.observations}
        feminist_control = by_id["au-feminist:control"]
        self.assertIn("content-encoding", feminist_control.headers)
        self.assertTrue(feminist_control.title.startswith("feminist majority foundation"))

        facebook_control = by_id["ir-facebook:control"]
        self.assertEqual(facebook_control.endpoints, frozenset({"10.10.34.36:443"}))
        self.assertFalse(facebook_control.tcp_success)

        for case in ("my-religioustolerance", "us-collegehumor", "es-postmaster"):
            self.assertEqual(by_id[f"{case}:probe"].title, "")
            self.assertNotEqual(by_id[f"{case}:control"].title, "")

        wikispaces_probe = by_id["sk-wikispaces:probe"]
        wikispaces_control = by_id["sk-wikispaces:control"]
        self.assertEqual(wikispaces_probe.endpoints, frozenset())
        self.assertEqual(wikispaces_control.endpoints, frozenset())
        self.assertFalse(wikispaces_probe.tcp_success)
        self.assertFalse(wikispaces_control.tcp_success)

        fa_records = [row for row in self.observations if row.target_id == "https://fa.wikipedia.org"]
        self.assertEqual(len(fa_records), 4)

    def test_conservative_predicate_abstains_without_supported_error(self):
        summary = summarize(pair_decisions(self.observations))
        self.assertEqual(summary.false_same, 0)
        self.assertEqual(summary.false_different, 0)
        self.assertGreater(summary.predicted_unknown, 0)
        self.assertGreater(summary.predicted_same, 0)
        self.assertGreater(summary.predicted_different, 0)

    def test_current_predictions_match_retained_pairs_without_relabeling(self):
        with (ROOT / "results/public_target_pairs.csv").open(newline="", encoding="utf-8") as stream:
            retained = list(csv.DictReader(stream))
        current = [
            {"left": row.left.observation_id, "right": row.right.observation_id,
             "truth": row.truth.value, "prediction": row.prediction.value, "reason": row.reason}
            for row in pair_decisions(self.observations)
        ]
        self.assertEqual(current, retained)

    def test_endpoint_only_control_exposes_both_error_types(self):
        summary = summarize(pair_decisions(self.observations, predicate=endpoint_only_vote))
        self.assertGreater(summary.false_same, 0)
        self.assertGreater(summary.false_different, 0)

    def test_predicate_does_not_use_target_label(self):
        by_id = {row.observation_id: row for row in self.observations}
        probe = by_id["my-religioustolerance:probe"]
        control = by_id["my-religioustolerance:control"]
        vote, _ = conservative_vote(probe, control)
        self.assertEqual(vote, Vote.SAME)
        changed = type(control)(
            case_id=control.case_id,
            target_id="independent-label-not-read-by-predicate",
            vantage=control.vantage,
            probe_cc=control.probe_cc,
            probe_asn=control.probe_asn,
            endpoints=control.endpoints,
            tcp_success=control.tcp_success,
            status=control.status,
            headers=control.headers,
            title=control.title,
            failure=control.failure,
        )
        changed_vote, _ = conservative_vote(probe, changed)
        self.assertEqual(changed_vote, vote)

    def test_wilson_interval_is_bounded(self):
        low, high = wilson_interval(7, 7)
        self.assertGreater(low, 0.6)
        self.assertEqual(high, 1.0)


class SuccessfulHTTPPredicateTests(unittest.TestCase):
    def setUp(self):
        self.left = Observation(
            "owned-left", "owned-target", "probe", "", "",
            frozenset({"192.0.2.1:443"}), True, 200,
            frozenset({"server", "content-type"}), "owned title", ""
        )
        self.right = replace(self.left, case_id="owned-right", vantage="control")

    def test_normal_200_signature_authorizes_same(self):
        self.assertEqual(conservative_vote(self.left, self.right),
                         (Vote.SAME, "successful-endpoint-and-http-signature"))

    def test_matching_2xx_including_class_boundaries_can_authorize_same(self):
        for status in (200, 201, 204, 206, 226, 299):
            with self.subTest(status=status):
                self.assertEqual(conservative_vote(
                    replace(self.left, status=status), replace(self.right, status=status)
                )[0], Vote.SAME)

    def test_shared_503_error_page_and_other_non_2xx_responses_are_unknown(self):
        for status in (None, 100, 199, 300, 301, 399, 400, 404, 499, 500, 503, 599, 600):
            with self.subTest(status=status):
                self.assertEqual(conservative_vote(
                    replace(self.left, status=status), replace(self.right, status=status)
                )[0], Vote.UNKNOWN)
                # A single unsuccessful side must not authorize SAME either.
                self.assertEqual(conservative_vote(
                    self.left, replace(self.right, status=status)
                )[0], Vote.UNKNOWN)

    def test_any_recorded_failure_blocks_same_even_with_matching_200(self):
        for failure in ("http-error", "timeout", "connection-reset"):
            for left_failed, right_failed in ((True, False), (False, True), (True, True)):
                with self.subTest(failure=failure, left=left_failed, right=right_failed):
                    self.assertEqual(conservative_vote(
                        replace(self.left, failure=failure if left_failed else ""),
                        replace(self.right, failure=failure if right_failed else "")
                    )[0], Vote.UNKNOWN)

    def test_both_2xx_still_requires_matching_status(self):
        self.assertEqual(conservative_vote(self.left, replace(self.right, status=201))[0], Vote.UNKNOWN)

    def test_error_responses_can_still_support_original_different_branch(self):
        for right_status in (200, 503):
            with self.subTest(right_status=right_status):
                left = replace(self.left, status=503)
                right = replace(self.right, status=right_status,
                                endpoints=frozenset({"192.0.2.2:443"}),
                                headers=frozenset({"location", "cache-control"}), title="other title")
                self.assertEqual(conservative_vote(left, right),
                                 (Vote.DIFFERENT, "disjoint-endpoints-and-two-http-conflicts"))

    def test_success_does_not_replace_endpoint_transport_or_signature_checks(self):
        variants = (
            replace(self.right, tcp_success=False),
            replace(self.right, endpoints=frozenset()),
            replace(self.right, title="other title", headers=frozenset({"location"})),
        )
        for right in variants:
            with self.subTest(right=right):
                self.assertEqual(conservative_vote(self.left, right)[0], Vote.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
