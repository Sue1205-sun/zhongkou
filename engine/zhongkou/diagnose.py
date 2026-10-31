"""诊断：把一堆评论压成一张能开会的表。

只做四件事：数、排、查、留证。
1. 数——18 维各被提到多少次、正负各多少；
2. 排——按"负向条数 × 提及广度"算改善优先级，先改哪一维；
3. 查——星级和细项是否打架、有没有重复文案；
4. 留证——每条结论都能回到具体评论编号。
"""

import re
import collections
from dataclasses import dataclass, field
from .aspects import DIMENSIONS, POS, NEG, NEU, NA, dim_cn, group_of
from .extract import extract

PUNCT = re.compile(r"[\s，。！？；、,.!?;:~…\-—\d]+")


@dataclass
class DimStat:
    dim: str
    mention: int = 0
    pos: int = 0
    neg: int = 0
    neu: int = 0
    evidence_ids: list = field(default_factory=list)   # 负向评论的编号，最多留 5 条

    @property
    def judged(self):
        return self.pos + self.neg + self.neu

    @property
    def neg_rate(self):
        return self.neg / self.judged if self.judged else 0.0

    @property
    def pos_rate(self):
        return self.pos / self.judged if self.judged else 0.0

    def per100(self, total):
        """每 100 条评论里，有多少条在抱怨这一维。给经营者看的口径。"""
        return self.neg / total * 100 if total else 0.0


class Diagnosis:
    def __init__(self):
        self.dims = {k: DimStat(k) for k in DIMENSIONS}
        self.total = 0
        self.judged_reviews = 0
        self.star_conflict = 0
        self.dup_groups = {}

    # ---------- 统计 ----------
    def add(self, rid, text, star, min_conf=1):
        self.total += 1
        fs = extract(text)
        hit = False
        for f in fs:
            if f.confidence < min_conf:
                continue
            st = self.dims[f.dim]
            st.mention += 1
            hit = True
            if f.polarity == POS:
                st.pos += 1
            elif f.polarity == NEG:
                st.neg += 1
                if len(st.evidence_ids) < 5:
                    st.evidence_ids.append({"id": rid, "quote": f.evidence[:60], "star": star})
            else:
                st.neu += 1
        if hit:
            self.judged_reviews += 1
        negs = [f for f in fs if f.polarity == NEG and f.confidence == 2]
        if star >= 4 and negs:
            self.star_conflict += 1
        key = PUNCT.sub("", text)[:24]
        if len(key) >= 8:
            self.dup_groups.setdefault(key, []).append(rid)

    # ---------- 排序 ----------
    def ranked(self, top=None):
        """按「每 100 条评论里的抱怨条数」排序。

        这个口径比负向率更适合排优先级：负向率高的维度可能只被提到几十次，
        改了也没多少人感知；而每百条评论的抱怨条数，直接等于"多少顾客带着
        这个不满离开"。
        """
        rows = [s for s in self.dims.values() if s.judged > 0]
        rows.sort(key=lambda s: s.per100(self.total), reverse=True)
        return rows[:top] if top else rows

    # ---------- 对外指标 ----------
    def summary(self):
        judged = sum(s.judged for s in self.dims.values())
        return {
            "reviews": self.total,
            "reviews_with_finding": self.judged_reviews,
            "mentions": judged,
            "star_conflict": self.star_conflict,
            "star_conflict_rate": self.star_conflict / self.total if self.total else 0.0,
            "dup_clusters": sum(1 for v in self.dup_groups.values() if len(v) > 1),
            "dup_reviews": sum(len(v) for v in self.dup_groups.values() if len(v) > 1),
        }

    def claim_stats(self):
        return {k: {"pos": s.pos, "neg": s.neg} for k, s in self.dims.items()}

    # ---------- 报告 ----------
    def top_line(self, k=3):
        rows = self.ranked(k)
        return "；".join(f"{dim_cn(s.dim)} 每百条 {s.per100(self.total):.1f} 条抱怨"
                        f"（负向率 {s.neg_rate*100:.0f}%）" for s in rows)

    def markdown(self, k=6):
        s = self.summary()
        out = []
        out.append(f"# 体验诊断（样本 {s['reviews']} 条）\n")
        out.append(f"- 有明确判定的评论：{s['reviews_with_finding']} 条"
                   f"（{s['reviews_with_finding']/s['reviews']*100:.1f}%）")
        out.append(f"- 维度判定总数：{s['mentions']} 条")
        out.append(f"- 星级掩盖细项：4–5 星评论中含明确负向维度 {s['star_conflict']} 条"
                   f"（{s['star_conflict_rate']*100:.1f}%）")
        out.append(f"- 重复/同源文案：{s['dup_reviews']} 条，集中在 {s['dup_clusters']} 个簇\n")
        out.append("| 优先级 | 维度 | 提及 | 正向 | 负向 | 每百条抱怨 | 负向率 |")
        out.append("|---|---|---|---|---|---|---|")
        for i, st in enumerate(self.ranked(k), 1):
            out.append(f"| {i} | {dim_cn(st.dim)} | {st.mention} | {st.pos} | {st.neg} | "
                       f"{st.per100(self.total):.1f} | {st.neg_rate*100:.1f}% |")
        return "\n".join(out)


def build(rows, min_conf=1) -> Diagnosis:
    d = Diagnosis()
    for rid, text, star, _gold in rows:
        d.add(rid, text, star, min_conf)
    return d
