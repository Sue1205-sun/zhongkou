"""与人工标注逐条比对：引擎到底有多准。

用法：
    python eval.py dev      # 调参用，允许我看
    python eval.py test     # 对外报告用，只跑一次

输出四个数：维度识别的 P/R/F1、已判维度的极性准确率、
高置信子集的准确率与覆盖率。高置信子集是引擎"敢下结论"的那部分。
"""

import csv, sys, os
from zhongkou.extract import extract

GOLD_KEYS = ["Location#Transportation", "Location#Downtown", "Location#Easy_to_find",
             "Service#Queue", "Service#Hospitality", "Service#Parking", "Service#Timely",
             "Price#Level", "Price#Cost_effective", "Price#Discount",
             "Ambience#Decoration", "Ambience#Noise", "Ambience#Space", "Ambience#Sanitary",
             "Food#Portion", "Food#Taste", "Food#Appearance", "Food#Recommend"]


def load(split):
    path = os.path.join(os.path.dirname(__file__), "..", "data", f"asap_{split}.csv")
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    out = []
    for r in rows:
        gold = {k: int(r[k]) for k in GOLD_KEYS}
        out.append((r["id"], r["review"], float(r["star"]), gold))
    return out


def evaluate(rows, verbose=False):
    tp = fp = fn = 0
    pol_ok = pol_all = 0
    hc_ok = hc_all = 0
    gold_total = 0
    per_dim = {k: [0, 0] for k in GOLD_KEYS}
    for rid, text, star, gold in rows:
        pred = {f.dim: f for f in extract(text)}
        gold_men = {k for k, v in gold.items() if v != -2}
        gold_total += len(gold_men)
        for d in gold_men:
            if d in pred:
                tp += 1
            else:
                fn += 1
        for d in pred:
            if d not in gold_men:
                fp += 1
        for d, f in pred.items():
            if d in gold_men and gold[d] in (1, 0, -1) and f.confidence >= 1:
                pol_all += 1
                if f.polarity == gold[d]:
                    pol_ok += 1
                    per_dim[d][0] += 1
                per_dim[d][1] += 1
                if f.confidence == 2:
                    hc_all += 1
                    hc_ok += 1 if f.polarity == gold[d] else 0
    P = tp / (tp + fp) if tp + fp else 0
    R = tp / (tp + fn) if tp + fn else 0
    F = 2 * P * R / (P + R) if P + R else 0
    print(f"维度识别  P={P:.3f} R={R:.3f} F1={F:.3f}  (提及维度共 {gold_total})")
    print(f"极性判断  已判 {pol_all} 条，准确率 {pol_ok/pol_all:.3f}" if pol_all else "")
    if hc_all:
        print(f"高置信    覆盖 {hc_all}/{pol_all} ({hc_all/pol_all*100:.1f}%)，准确率 {hc_ok/hc_all:.3f}")
    if verbose:
        for k, (a, b) in sorted(per_dim.items(), key=lambda x: -(x[1][0]/x[1][1] if x[1][1] else 0)):
            if b:
                print(f"  {k:26s} {a:5d}/{b:5d} = {a/b*100:5.1f}%")
    return dict(P=P, R=R, F1=F, acc=pol_ok / pol_all if pol_all else 0)


if __name__ == "__main__":
    split = sys.argv[1] if len(sys.argv) > 1 else "dev"
    evaluate(load(split), verbose=("-v" in sys.argv))
