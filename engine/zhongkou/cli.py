"""命令行入口。

    python -m zhongkou diagnose --split test
    python -m zhongkou claim "环境安静，适合聊天" --split test
    python -m zhongkou audit --split test
    python -m zhongkou quote --dim Ambience#Noise --limit 3
"""

import argparse
import sys

from .aspects import dim_cn
from .claims import check
from .diagnose import build
from .load import load_asap, load_generic


def _rows(args):
    if getattr(args, "csv", None):
        return load_generic(args.csv)
    return load_asap(args.split)


def cmd_diagnose(args):
    rows = _rows(args)
    d = build(rows)
    s = d.summary()
    print(f"样本 {s['reviews']} 条，有明确判定的 {s['reviews_with_finding']} 条"
          f"（{s['reviews_with_finding']/s['reviews']*100:.1f}%）")
    print(f"星级掩盖细项：4–5 星评论中含明确负向维度 {s['star_conflict']} 条"
          f"（{s['star_conflict_rate']*100:.1f}%）")
    print(f"重复/同源文案 {s['dup_reviews']} 条，集中在 {s['dup_clusters']} 个簇")
    print()
    print(f"{'优先级':<4}{'维度':<10}{'每百条抱怨':>10}{'负向率':>9}{'提及':>7}")
    for i, st in enumerate(d.ranked(args.top), 1):
        print(f"{i:<5}{dim_cn(st.dim):<11}{st.per100(d.total):>9.1f}{st.neg_rate*100:>8.1f}%{st.mention:>8}")
    if args.md:
        open(args.md, "w", encoding="utf-8").write(d.markdown(args.top))
        print(f"\n已写出 {args.md}")


def cmd_claim(args):
    rows = _rows(args)
    d = build(rows)
    v = check(args.sentence, d.claim_stats())
    print(f"判定：{v.verdict}")
    print(f"落点：{v.dim_cn}")
    print(f"证据：正面 {v.pos} 条 / 反例 {v.neg} 条 / 正面占比 {v.ratio*100:.1f}%")
    if v.forbidden:
        print(f"禁用词：{'、'.join(v.forbidden)}")
    print(f"理由：{v.reason}")


def cmd_audit(args):
    from .audit import dump, evaluate
    evaluate(dump(load_asap(args.split)), verbose=True)


def cmd_quote(args):
    rows = _rows(args)
    d = build(rows)
    st = d.dims[args.dim]
    print(f"{dim_cn(args.dim)}：提及 {st.mention} 条，正向 {st.pos}，负向 {st.neg}")
    for e in st.evidence_ids[:args.limit]:
        print(f"  #{e['id']}  {e['star']:.0f}星  {e['quote']}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="zhongkou", description="众口：评论证据链分析")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = dict()
    for name, fn, helptext in (("diagnose", cmd_diagnose, "18 维短板排序"),
                               ("claim", cmd_claim, "卖点取证"),
                               ("audit", cmd_audit, "与人工标注比对"),
                               ("quote", cmd_quote, "取证据原话")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--split", default="test", choices=["test", "dev"])
        if name != "audit":
            sp.add_argument("--csv", help="自定义评论表（列名含 评论/星级 即可）")
        if name == "diagnose":
            sp.add_argument("--top", type=int, default=8)
            sp.add_argument("--md", help="同时写出 Markdown")
        if name == "claim":
            sp.add_argument("sentence")
        if name == "quote":
            sp.add_argument("--dim", required=True)
            sp.add_argument("--limit", type=int, default=3)
        sp.set_defaults(func=fn)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
