"""规则抽取：从原始评论里判出「哪一维被提到、正还是负、有多大把握」。

三条设计原则：
1. **子句作用域**——极性线索只在提及该维度的那个分句里找。跨句取词会把
   "环境不错，但服务太差" 里的"不错"错记到服务上。
2. **距离定置信**——线索离维度词越近、越像直接修饰，置信度越高。够不着的
   一律不出结论，交给下游标"待查"。
3. **中性留白**——"一般""还行"这类不表态度的话记为中性，不硬掰成正或负。
"""

import re
from dataclasses import dataclass, field
from .aspects import (DIMENSIONS, POS_CUES, NEG_CUES, NEU_CUES, DIM_CUES, NEGATORS,
                      INTENSIFIERS, POS, NEU, NEG)

CLAUSE_SEP = re.compile(r"[，。！？；、\n\r~…\t]")
MAX_DIST = 22


@dataclass
class Finding:
    dim: str
    polarity: int
    confidence: int          # 2 高 / 1 中 / 0 低
    evidence: str
    cues: list = field(default_factory=list)
    dist: int = 99


def _table(dim=None):
    """通用线索 + 该维度的专属线索，长的排前面，保证「不贵」先于「贵」。"""
    t = [(c, POS) for c in POS_CUES] + [(c, NEG) for c in NEG_CUES] + [(c, NEU) for c in NEU_CUES]
    extra = DIM_CUES.get(dim or "", {})
    t += [(c, POS) for c in extra.get(POS, [])] + [(c, NEG) for c in extra.get(NEG, [])]
    t.sort(key=lambda x: -len(x[0]))
    return t


CUES = _table()
_TABLE_CACHE = {}


def _cues_for(dim):
    if dim not in _TABLE_CACHE:
        _TABLE_CACHE[dim] = _table(dim)
    return _TABLE_CACHE[dim]


def clauses(text: str) -> list:
    """按标点切分句，返回 [(start, end)]。"""
    out, start = [], 0
    for m in CLAUSE_SEP.finditer(text):
        if m.start() > start:
            out.append((start, m.start()))
        start = m.end()
    if start < len(text):
        out.append((start, len(text)))
    return out


def _negated(text: str, i: int, cue: str) -> bool:
    if cue[:1] in "不没无别未":
        return False
    head = text[max(0, i - 3):i]
    return any(head.endswith(n) for n in NEGATORS)


def _scan(seg: str, table=None):
    """在一段（子句级）文本里扫描线索，返回 [(pos, polarity, cue)]，已处理否定与重叠。"""
    used = [False] * len(seg)
    hits = []
    for cue, pol in (table or CUES):
        start = 0
        while True:
            i = seg.find(cue, start)
            if i < 0:
                break
            end = i + len(cue)
            if any(used[i:end]):
                start = i + 1
                continue
            for k in range(i, end):
                used[k] = True
            eff = pol
            if pol == POS and _negated(seg, i, cue):
                eff = NEG
            hits.append((i, eff, cue, i + len(cue)))
            start = end
    return hits


def polarity_at(text: str, kw_start: int, kw_end: int, dim: str = None):
    """以维度词为中心，在同一分句内找线索，返回 (极性, 置信度, 证据, 线索)。"""
    cs = clauses(text)
    ci = next((k for k, (a, b) in enumerate(cs) if a <= kw_start < b), None)
    if ci is None:
        return NEU, 0, text[max(0, kw_start - 12):kw_end + 12], [], 99
    a, b = cs[ci]
    a0, b0 = a, b                      # 证据只留本分句，给读者看的是原话，不掺别的
    # 扫描时可以往后多看一眼（分句太短时，如"很好吃"）
    if b - a < 6:
        b = min(b + 4, len(text))
    seg = text[a:b]
    quote_seg = text[a0:b0]
    hits = _scan(seg, _cues_for(dim))
    if not hits:
        return NEU, 0, quote_seg, [], 99
    kwc = kw_start - a

    def dist(h):
        p, _, _, e = h
        if e <= kwc:
            return kwc - e
        if p >= kwc:
            return p - kwc
        return 0

    nearest = sorted(hits, key=dist)
    pos = [h for h in nearest if h[1] == POS]
    neg = [h for h in nearest if h[1] == NEG]
    neu = [h for h in nearest if h[1] == NEU]
    dmin = dist(nearest[0])
    if dmin > MAX_DIST:
        return NEU, 0, quote_seg, [h[2] for h in nearest[:3]], dmin

    if len(neu) > len(pos) + len(neg):
        pol, conf = NEU, (2 if dist(neu[0]) <= 6 else 1)
    elif len(pos) > len(neg):
        pol = POS
        conf = 2 if (dist(pos[0]) <= 5 and not neg) or (len(pos) >= 2 and len(neg) == 0) else 1
    elif len(neg) > len(pos):
        pol = NEG
        conf = 2 if (dist(neg[0]) <= 5 and not pos) or (len(neg) >= 2 and len(pos) == 0) else 1
    else:
        # 正负各一：距离更近的赢，但一律降为中等置信
        if dist(pos[0]) < dist(neg[0]):
            pol, conf = POS, 1
        elif dist(neg[0]) < dist(pos[0]):
            pol, conf = NEG, 1
        else:
            pol, conf = NEU, 0
    if pol != NEU and conf < 2:
        head = seg[max(0, nearest[0][0] - 2):nearest[0][0]]
        if any(head.endswith(w) for w in INTENSIFIERS):
            conf = 2
    return pol, conf, quote_seg, [("-" if h[1] == NEG else ("+" if h[1] == POS else "o")) + h[2]
                                  for h in nearest[:3]], dmin


def extract(review: str) -> list:
    """对一条评论抽取维度级判定；同维多次出现取最可信的一次。"""
    review = (review or "").strip()
    if not review:
        return []
    best = {}
    for dim, meta in DIMENSIONS.items():
        for kw in meta["keywords"]:
            start = 0
            while True:
                i = review.find(kw, start)
                if i < 0:
                    break
                start = i + len(kw)
                pol, conf, seg, cues, dd = polarity_at(review, i, i + len(kw), dim)
                f = Finding(dim=dim, polarity=pol, confidence=conf,
                            evidence=seg.replace("\n", " "), cues=cues, dist=dd)
                prev = best.get(dim)
                if prev is None or (f.confidence, len(f.cues)) > (prev.confidence, len(prev.cues)):
                    best[dim] = f
    return list(best.values())


def total_vs_detail(review: str, star: float) -> dict:
    """星级与维度判定是否互相打架：高分里藏着负向，或低分却全是好话。"""
    fs = extract(review)
    negs = [f.dim for f in fs if f.polarity == NEG and f.confidence == 2]
    poss = [f.dim for f in fs if f.polarity == POS and f.confidence == 2]
    conflict = (star >= 4 and bool(negs)) or (star <= 2 and not negs and bool(poss))
    return {"conflict": conflict, "neg": negs, "pos": poss}
