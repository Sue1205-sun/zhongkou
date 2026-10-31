"""审计：引擎的判定与人工标注逐条比对。

这不是自测。标注来自数据集作者雇佣的标注员，与引擎无任何关系。
比对口径写死在这里，谁都能重跑：
- 维度识别：引擎判出的维度集合 vs 人工标注为「被提及」的维度集合；
- 极性判断：两边都指向同一维度时，正/负/中是否一致；
- 高置信：只统计引擎置信度为 2 的那部分，看"敢下结论时"的准确率。
"""

from .extract import extract
from .load import GOLD_KEYS, load_asap


def dump(rows):
    out = []
    for rid, text, star, gold in rows:
        out.append((rid, text, star, {k: int(gold[k]) for k in GOLD_KEYS if k in gold}))
    return out


def evaluate(rows, verbose=False):
    tp = fp = fn = 0
    pol_ok = pol_all = 0
    hc_ok = hc_all = 0
    per_dim = {k: [0, 0] for k in GOLD_KEYS}
    for rid, text, star, gold in rows:
        pred = {f.dim: f for f in extract(text)}
        gold_men = {k for k, v in gold.items() if v != -2}
        tp += len(gold_men & set(pred))
        fn += len(gold_men - set(pred))
        fp += len(set(pred) - gold_men)
        for d, f in pred.items():
            if d in gold_men and gold[d] in (1, 0, -1) and f.confidence >= 1:
                pol_all += 1
                ok = f.polarity == gold[d]
                pol_ok += ok
                per_dim[d][0] += ok
                per_dim[d][1] += 1
                if f.confidence == 2:
                    hc_all += 1
                    hc_ok += ok
    P = tp / (tp + fp) if tp + fp else 0
    R = tp / (tp + fn) if tp + fn else 0
    F = 2 * P * R / (P + R) if P + R else 0
    res = {
        "precision": P, "recall": R, "f1": F,
        "polarity_n": pol_all,
        "polarity_acc": pol_ok / pol_all if pol_all else 0,
        "high_n": hc_all,
        "high_acc": hc_ok / hc_all if hc_all else 0,
        "high_cov": hc_all / pol_all if pol_all else 0,
        "per_dim": per_dim,
    }
    if verbose:
        print(f"维度识别  P={P:.3f} R={R:.3f} F1={F:.3f}")
        print(f"极性判断  已判 {pol_all} 条，准确率 {res['polarity_acc']:.3f}")
        print(f"高置信    覆盖 {hc_all}/{pol_all}（{res['high_cov']*100:.1f}%），"
              f"准确率 {res['high_acc']:.3f}")
        for k, (a, b) in sorted(per_dim.items(), key=lambda x: -(x[1][0] / x[1][1] if x[1][1] else 0)):
            if b:
                print(f"  {k:26s} {a:5d}/{b:5d} = {a/b*100:5.1f}%")
    return res


if __name__ == "__main__":
    import sys
    split = sys.argv[1] if len(sys.argv) > 1 else "test"
    evaluate(dump(load_asap(split)), verbose=True)
