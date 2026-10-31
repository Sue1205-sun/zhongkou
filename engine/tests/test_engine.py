"""引擎单测：跑 pytest 或直接 python -m unittest discover tests。

这些用例不是为了凑数，每一条都对应开发中真实踩过的坑：
跨句串味、"不贵"被判成贵、把"一般"当差评、把没提的维度算进去。
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zhongkou.aspects import POS, NEG, NEU  # noqa: E402
from zhongkou.claims import ABSOLUTE_WORDS, check, locate_dim  # noqa: E402
from zhongkou.diagnose import build  # noqa: E402
from zhongkou.extract import clauses, extract, polarity_at  # noqa: E402
from zhongkou.load import load_generic  # noqa: E402


def one(text, dim):
    for f in extract(text):
        if f.dim == dim:
            return f
    return None


class TestClause(unittest.TestCase):
    def test_split_on_punctuation(self):
        cs = clauses("环境不错，服务太差。下次不来了")
        self.assertEqual(len(cs), 3)

    def test_no_trailing_empty(self):
        cs = clauses("好吃。")
        self.assertEqual(len(cs), 1)


class TestExtract(unittest.TestCase):
    def test_positive(self):
        f = one("服务态度特别好，服务员很热情", "Service#Hospitality")
        self.assertIsNotNone(f)
        self.assertEqual(f.polarity, POS)

    def test_negated_positive_becomes_negative(self):
        f = one("服务态度不好", "Service#Hospitality")
        self.assertEqual(f.polarity, NEG)

    def test_cheap_is_not_expensive(self):
        """「不贵」必须判成正面，这是最容易错的一条。"""
        f = one("这家店价格不贵", "Price#Level")
        self.assertEqual(f.polarity, POS)

    def test_expensive(self):
        f = one("人均有点贵", "Price#Level")
        self.assertEqual(f.polarity, NEG)

    def test_neutral_word(self):
        f = one("味道一般般，没什么惊喜", "Food#Taste")
        self.assertEqual(f.polarity, NEU)

    def test_cross_clause_does_not_leak(self):
        """「环境不错」的好评不能记到服务上。"""
        f = one("环境很不错，但是服务太差了", "Service#Hospitality")
        self.assertEqual(f.polarity, NEG)

    def test_cross_clause_positive(self):
        f = one("服务太差了，环境很不错", "Ambience#Decoration")
        self.assertEqual(f.polarity, POS)

    def test_no_mention_returns_nothing(self):
        self.assertEqual(extract("今天天气不错，出门散步"), [])

    def test_empty_text(self):
        self.assertEqual(extract(""), [])
        self.assertEqual(extract(None), [])

    def test_evidence_is_substring_of_review(self):
        t = "上菜太慢了，等了一个小时"
        f = one(t, "Service#Timely")
        self.assertIn(f.evidence, t)

    def test_confidence_range(self):
        for f in extract("环境安静，服务周到，味道不错，价格便宜"):
            self.assertIn(f.confidence, (0, 1, 2))

    def test_queue_without_waiting_is_positive(self):
        f = one("去的时候不用排队，直接就坐下了", "Service#Queue")
        self.assertEqual(f.polarity, POS)

    def test_queue_waiting_is_negative(self):
        f = one("排队等了将近两个小时", "Service#Queue")
        self.assertEqual(f.polarity, NEG)

    def test_noise_quiet(self):
        f = one("环境很安静，适合聊天", "Ambience#Noise")
        self.assertEqual(f.polarity, POS)

    def test_polarity_at_returns_clause_only(self):
        t = "服务很好，上菜很快"
        pol, conf, seg, cues, dist = polarity_at(t, 0, 2, "Service#Hospitality")
        self.assertNotIn("上菜", seg)


class TestClaims(unittest.TestCase):
    stats = {
        "Food#Taste": {"pos": 900, "neg": 30},
        "Ambience#Noise": {"pos": 100, "neg": 140},
        "Service#Timely": {"pos": 200, "neg": 40},
        "Service#Parking": {"pos": 3, "neg": 1},
    }

    def test_absolute_word_blocks(self):
        v = check("我们的菜最好吃", self.stats)
        self.assertEqual(v.verdict, "违规")
        self.assertIn("最好", v.forbidden)

    def test_absolute_word_blocks_even_with_evidence(self):
        """证据再足，绝对化用语也不能用。"""
        v = check("口味最好，回头客最多", self.stats)
        self.assertEqual(v.verdict, "违规")

    def test_supported(self):
        v = check("口味地道，很多人回头", self.stats)
        self.assertEqual(v.verdict, "有据")

    def test_contradicted(self):
        v = check("环境安静，适合聊天", self.stats)
        self.assertEqual(v.verdict, "无据")

    def test_insufficient(self):
        v = check("停车很方便", self.stats)
        self.assertEqual(v.verdict, "证据不足")

    def test_unmappable(self):
        v = check("我们老板是本地人", self.stats)
        self.assertEqual(v.verdict, "无法归位")

    def test_locate_dim_picks_longest_hint(self):
        self.assertEqual(locate_dim("不用排队，随时都有座"), "Service#Queue")
        self.assertEqual(locate_dim("上菜快，翻台也快"), "Service#Timely")

    def test_forbidden_list_not_empty(self):
        self.assertGreater(len(ABSOLUTE_WORDS), 20)


class TestDiagnose(unittest.TestCase):
    def rows(self):
        return [
            ("1", "环境安静，服务周到", 5.0, None),
            ("2", "太吵了，根本没法聊天", 4.0, None),
            ("3", "服务态度很差", 1.0, None),
            ("4", "味道一般般", 3.0, None),
            ("5", "今天下雨了", 5.0, None),
        ]

    def test_counts(self):
        d = build(self.rows())
        self.assertEqual(d.total, 5)
        self.assertGreaterEqual(d.dims["Ambience#Noise"].neg, 1)
        self.assertGreaterEqual(d.dims["Service#Hospitality"].neg, 1)

    def test_star_conflict_detected(self):
        """4 星评论里说太吵，属于星级掩盖细项。"""
        d = build(self.rows())
        self.assertGreaterEqual(d.star_conflict, 1)

    def test_per100(self):
        d = build(self.rows())
        st = d.dims["Ambience#Noise"]
        self.assertAlmostEqual(st.per100(d.total), st.neg / 5 * 100)

    def test_ranked_sorted(self):
        d = build(self.rows())
        vals = [s.per100(d.total) for s in d.ranked()]
        self.assertEqual(vals, sorted(vals, reverse=True))

    def test_summary_keys(self):
        s = build(self.rows()).summary()
        for k in ("reviews", "mentions", "star_conflict", "dup_clusters"):
            self.assertIn(k, s)

    def test_duplicate_cluster(self):
        rows = [("1", "环境安静服务周到味道不错", 5.0, None),
                ("2", "环境安静服务周到味道不错", 5.0, None)]
        self.assertEqual(build(rows).summary()["dup_clusters"], 1)

    def test_markdown_contains_table(self):
        md = build(self.rows()).markdown(3)
        self.assertIn("| 优先级 |", md)


class TestLoad(unittest.TestCase):
    def test_generic_csv(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                         encoding="utf-8-sig", newline="") as fh:
            fh.write("编号,评论内容,星级\n")
            fh.write("a1,环境安静很好,5\n")
            fh.write("a2,太吵了,2\n")
            path = fh.name
        rows = load_generic(path)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][2], 5.0)
        os.unlink(path)

    def test_missing_text_column_raises(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                         encoding="utf-8-sig", newline="") as fh:
            fh.write("a,b\n1,2\n")
            path = fh.name
        with self.assertRaises(ValueError):
            load_generic(path)
        os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
