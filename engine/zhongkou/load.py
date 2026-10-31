"""数据读取：支持 ASAP 官方切分，也支持任意「评论 + 星级」两列的 CSV。"""

import csv
import os

# ASAP 的 18 个维度列，顺序与数据集一致
GOLD_KEYS = ["Location#Transportation", "Location#Downtown", "Location#Easy_to_find",
             "Service#Queue", "Service#Hospitality", "Service#Parking", "Service#Timely",
             "Price#Level", "Price#Cost_effective", "Price#Discount",
             "Ambience#Decoration", "Ambience#Noise", "Ambience#Space", "Ambience#Sanitary",
             "Food#Portion", "Food#Taste", "Food#Appearance", "Food#Recommend"]

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data")


def load_asap(split="test", limit=None):
    """返回 [(id, review, star, gold_dict)]。gold 为 None 时表示没有人工标注。"""
    path = os.path.join(DATA_DIR, f"asap_{split}.csv")
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    if limit:
        rows = rows[:limit]
    out = []
    for r in rows:
        gold = {k: int(r[k]) for k in GOLD_KEYS if k in r}
        out.append((r["id"], r["review"], float(r["star"]), gold or None))
    return out


def load_generic(path):
    """兼容自家导出的评论表：列名含 评论/内容/review/text 与 星级/评分/star 即可。"""
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    if not rows:
        return []
    cols = {c.lower(): c for c in rows[0]}
    text_col = next((cols[c] for c in ("review", "评论", "内容", "text", "评论内容") if c in cols), None)
    star_col = next((cols[c] for c in ("star", "星级", "评分", "rating") if c in cols), None)
    id_col = next((cols[c] for c in ("id", "编号", "评论id") if c in cols), None)
    if text_col is None:
        raise ValueError("找不到评论文本列")
    out = []
    for i, r in enumerate(rows):
        try:
            star = float(r[star_col]) if star_col else 0.0
        except (TypeError, ValueError):
            star = 0.0
        out.append((r[id_col] if id_col else str(i), r[text_col], star, None))
    return out
