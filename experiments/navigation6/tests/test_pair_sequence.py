"""pair_sequence：成对内状态链、对内方式直方图与分桶测试。"""
import random
import unittest

from experiments.navigation6.app.practice.practice.pair_sequence import (
    PARTICIPANT_CONDITION_CODE,
    PairCondition,
    assign_pool_with_pair_chaining,
    bucket_and_index_pool,
    bucket_pool_by_rdc,
    build_mode_sequence_disjoint_pairs,
    build_sequenced_pools,
    edge_histograms_from_modes_disjoint,
    parse_pair_condition,
)
from experiments.navigation6.app.practice.practice.transit_practice_modes import pool_item_to_rdc


def _item(code: int, line_idx: int, next_code: int = 99):
    qid = f"m|{code}|instant_transit_next|{line_idx}|{next_code}"
    return (qid, code, "x", "instant_transit_next", line_idx, next_code)


class TestPairSequence(unittest.TestCase):
    def test_parse_pair_condition(self):
        self.assertEqual(parse_pair_condition("uniform"), PairCondition.UNIFORM)
        self.assertEqual(parse_pair_condition("4"), PairCondition.UNIFORM)
        self.assertEqual(parse_pair_condition("1"), PairCondition.SAME_HEAVY)
        self.assertEqual(parse_pair_condition("dcr"), PairCondition.UNIFORM)
        self.assertEqual(parse_pair_condition("DD"), PairCondition.SAME_HEAVY)
        self.assertEqual(PARTICIPANT_CONDITION_CODE[PairCondition.C_HEAVY], "DC")

    def test_pool_item_to_rdc(self):
        modes = ["bus", "metro", "light_rail"]
        self.assertEqual(pool_item_to_rdc(_item(1, 0), modes), "R")
        self.assertEqual(pool_item_to_rdc(_item(1, 1), modes), "C")
        self.assertEqual(pool_item_to_rdc(_item(1, 2), modes), "D")

    def test_build_mode_sequence_disjoint_pairs_length(self):
        rng = random.Random(0)
        seq, trail = build_mode_sequence_disjoint_pairs(20, PairCondition.UNIFORM, rng)
        self.assertEqual(len(seq), 20)
        self.assertFalse(trail)
        self.assertTrue(all(x in ("R", "D", "C") for x in seq))

    def test_build_mode_sequence_trailing_singleton(self):
        seq, trail = build_mode_sequence_disjoint_pairs(5, PairCondition.UNIFORM, random.Random(1))
        self.assertEqual(len(seq), 5)
        self.assertTrue(trail)

    def test_edge_histogram_disjoint_one_internal_edge(self):
        modes = ["R", "C", "D"]
        h = edge_histograms_from_modes_disjoint(modes)
        self.assertEqual(h["num_internal_edges"], 1)
        self.assertEqual(h["histogram_scope"], "disjoint_pairs_only")

    def test_pair_chain_assign(self):
        transit = ["bus", "metro", "light_rail"]
        pool = [_item(1, 0, 2), _item(2, 1, 3)]
        buckets, by_sm, by_s, _ = bucket_and_index_pool(pool, transit)
        out, w = assign_pool_with_pair_chaining(
            ["R", "C"], buckets, by_sm, by_s, random.Random(0)
        )
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0][5], out[1][1])
        self.assertEqual(pool_item_to_rdc(out[0], transit), "R")
        self.assertEqual(pool_item_to_rdc(out[1], transit), "C")
        self.assertEqual(len(w), 0)

    def test_length_three_no_cross_pair_state_constraint(self):
        transit = ["bus", "metro", "light_rail"]
        pool = [
            _item(1, 0, 2),
            _item(2, 1, 3),
            _item(5, 2, 7),
        ]
        buckets, by_sm, by_s, _ = bucket_and_index_pool(pool, transit)
        out, _ = assign_pool_with_pair_chaining(
            ["R", "C", "D"], buckets, by_sm, by_s, random.Random(0)
        )
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0][5], out[1][1])
        self.assertNotEqual(out[1][5], out[2][1])

    def test_sequenced_pools_shape(self):
        transit_modes = ["bus", "metro", "light_rail"]
        pool = []
        for c in range(1, 8):
            for li in (0, 1, 2):
                pool.append(_item(c, li, min(c + 1, 8)))
        rng = random.Random(42)
        lp, tp, diag = build_sequenced_pools(
            pool, transit_modes, learning_length=6, test_length=3, condition=PairCondition.UNIFORM, rng=rng
        )
        self.assertEqual(len(lp), 6)
        self.assertEqual(len(tp), 3)
        self.assertIn("edge_histogram_learning", diag)
        self.assertEqual(diag["pair_chain_spec"], "disjoint_pairs_2k_2k1")
        self.assertIn("pair_assignment_warnings", diag)
        h = diag["edge_histogram_learning"]
        self.assertEqual(h["num_internal_edges"], 3)
        for k in range(3):
            self.assertEqual(lp[2 * k][5], lp[2 * k + 1][1])
        self.assertEqual(diag["test_mode_sequence"], diag["learning_mode_sequence"][: len(tp)])
        self.assertEqual(diag["test_mode_sequence_source"], "learning_prefix")

    def test_test_modes_prefix_matches_learning(self):
        transit = ["bus", "metro", "light_rail"]
        pool = []
        for c in range(1, 8):
            for li in (0, 1, 2):
                pool.append(_item(c, li, min(c + 1, 8)))
        rng = random.Random(11)
        _, tp, diag = build_sequenced_pools(
            pool, transit, learning_length=14, test_length=5, condition=PairCondition.SAME_HEAVY, rng=rng
        )
        self.assertEqual(diag["test_mode_sequence"], diag["learning_mode_sequence"][:5])
        self.assertEqual(len(tp), 5)
        cov = diag["test_instant_transit_coverage"]
        self.assertIn("uncovered_count", cov)
        self.assertEqual(cov["test_question_count"], 5)

    def test_bucket_pool_by_rdc(self):
        modes = ["bus", "bus"]
        pool = [_item(1, 0, 2), _item(2, 1, 3)]
        buckets, w = bucket_pool_by_rdc(pool, modes)
        self.assertEqual(len(buckets["R"]), 2)
        _, by_sm, by_s, _ = bucket_and_index_pool(pool, modes)
        out, aw = assign_pool_with_pair_chaining(
            ["R", "C"], buckets, by_sm, by_s, random.Random(0)
        )
        self.assertEqual(len(out), 2)
        self.assertTrue(any("fallback" in x for x in aw) or len(aw) == 0)


if __name__ == "__main__":
    unittest.main()
