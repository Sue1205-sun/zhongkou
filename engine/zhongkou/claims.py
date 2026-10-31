"""卖点取证：一句话能不能说、说了要挂多少条证据。

判定分三档：
- 违规：命中广告法第九条的绝对化用语，或承诺了不确定的收益/功效；
- 有据：同一维度上正面证据足够多，且反例占比低；
- 无据：证据条数不够，或反例占比过高（说了会被评论打脸）。
"""

from dataclasses import dataclass
from .aspects import DIMENSIONS, POS, NEG, NEU

# 《广告法》第九条列举的绝对化用语（餐饮场景常见部分）
ABSOLUTE_WORDS = [
    "最好", "最佳", "最优", "最棒", "最强", "最正宗", "最地道", "最便宜", "最实惠", "第一",
    "国家级", "顶级", "极致", "唯一", "首家", "独家", "万能", "永久", "终身", "绝对",
    "100%", "百分百", "零添加", "纯天然", "无添加", "根治", "包治", "稳赚", "保证", "包好",
    "全城最", "全市最", "销量第一", "排名第一", "史上最",
]

# 卖点措辞 → 维度：用于把一句文案落到具体的体验维度上
CLAIM_HINTS = {
    "Food#Taste": ["好吃", "美味", "口味", "正宗", "地道", "入味", "鲜"],
    "Food#Portion": ["分量", "量大", "份量", "足量", "吃得饱", "划算的份量"],
    "Food#Appearance": ["卖相", "摆盘", "颜值", "好看", "精致"],
    "Food#Recommend": ["推荐", "必点", "回头客", "会再来", "口碑"],
    "Service#Hospitality": ["服务", "态度", "热情", "周到", "贴心"],
    "Service#Timely": ["上菜快", "上菜速度", "出餐快", "不用等太久", "及时"],
    "Service#Queue": ["不用排队", "不排队", "免等位", "随到随吃"],
    "Service#Parking": ["停车", "车位", "好停车", "免费停车"],
    "Price#Level": ["便宜", "平价", "实惠", "不贵", "价格亲民"],
    "Price#Cost_effective": ["性价比", "物有所值", "划算", "超值"],
    "Price#Discount": ["优惠", "折扣", "团购", "打折", "套餐价"],
    "Ambience#Decoration": ["环境", "装修", "氛围", "格调", "拍照"],
    "Ambience#Noise": ["安静", "不吵", "清静", "适合聊天"],
    "Ambience#Space": ["宽敞", "空间大", "包间", "不拥挤"],
    "Ambience#Sanitary": ["干净", "卫生", "整洁"],
    "Location#Transportation": ["交通方便", "地铁", "好停车方便", "交通便利"],
    "Location#Downtown": ["市中心", "商圈", "地段好", "繁华"],
    "Location#Easy_to_find": ["好找", "位置好找", "招牌明显", "导航直达"],
}

# 判定阈值（写在代码里，不藏在模型脑子里，任何人可改可复核）
MIN_EVIDENCE = 30          # 少于此条数，不足以支撑一句对外宣传
GOOD_RATIO = 0.80          # 正面占比达到此线才算"有据"
BAD_RATIO = 0.60           # 正面占比低于此线，视为有反证


@dataclass
class ClaimVerdict:
    sentence: str
    dim: str
    dim_cn: str
    pos: int
    neg: int
    ratio: float
    forbidden: list
    verdict: str            # 违规 / 有据 / 无据 / 证据不足 / 无法归位
    reason: str


def _cn(dim):
    return DIMENSIONS.get(dim, {}).get("cn", dim)


def locate_dim(sentence: str):
    """把一句话落到体验维度上；一句话可能同时踩多个维度，取措辞匹配最长的那个。"""
    best, best_len = None, 0
    for dim, words in CLAIM_HINTS.items():
        for w in words:
            if w in sentence and len(w) > best_len:
                best, best_len = dim, len(w)
    return best


def check(sentence: str, stats: dict) -> ClaimVerdict:
    """stats: {dim: {'pos': n, 'neg': n}}，由 diagnose.Diagnosis 产出。"""
    forbidden = [w for w in ABSOLUTE_WORDS if w in sentence]
    dim = locate_dim(sentence)
    if dim is None:
        return ClaimVerdict(sentence, "-", "-", 0, 0, 0.0, forbidden,
                            "无法归位", "这句话没有落到任何一个可核验的体验维度上，引擎不判")
    s = stats.get(dim, {"pos": 0, "neg": 0})
    pos, neg = s["pos"], s["neg"]
    total = pos + neg
    ratio = pos / total if total else 0.0
    if forbidden:
        return ClaimVerdict(sentence, dim, _cn(dim), pos, neg, ratio, forbidden,
                            "违规", f"命中绝对化用语 {('、'.join(forbidden))}，广告法第九条禁止")
    if total < MIN_EVIDENCE:
        return ClaimVerdict(sentence, dim, _cn(dim), pos, neg, ratio, forbidden,
                            "证据不足", f"{_cn(dim)}仅有 {total} 条相关评论，低于 {MIN_EVIDENCE} 条下限")
    if ratio < BAD_RATIO:
        return ClaimVerdict(sentence, dim, _cn(dim), pos, neg, ratio, forbidden,
                            "无据", f"{_cn(dim)}正面仅占 {ratio*100:.1f}%，另有 {neg} 条反例")
    if ratio < GOOD_RATIO:
        return ClaimVerdict(sentence, dim, _cn(dim), pos, neg, ratio, forbidden,
                            "无据", f"正面占 {ratio*100:.1f}%，未达 {GOOD_RATIO*100:.0f}% 证据线，属勉强可说")
    return ClaimVerdict(sentence, dim, _cn(dim), pos, neg, ratio, forbidden,
                        "有据", f"{_cn(dim)}正面 {pos} 条、反例 {neg} 条，正面占 {ratio*100:.1f}%")
