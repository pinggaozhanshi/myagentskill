"""歌词核对：把谱面初稿每个音的歌词（Vocal to MIDI 识别）和官方歌词的读音逐音节对齐，列出不一致的地方。

用法：python -I lyric_check.py <score.json> <lyrics_page_url> <out_aligned.json>
- 官方歌词取自 UtaTen 歌词页（带假名注音）：只在内存里解析 `.hiragana` 块（汉字换成注音），不存网页。
- 读音切成音节（拍）：拗音小字并进前一拍，「っ」「ん」单独一拍，「ー」换成前一拍的元音。
- 谱面一音一拍；「-」等 ASCII 歌词当作延长音。用半全局对齐（官方序列两端的空隙不计分），
  找出这一段对应官方歌词的哪几行。
- 输出（含歌词，只放 work/）：每个音对上的官方音节序号 j 与音节、不一致的位置。
  终端只打印序号和“音类”（mclass：V 元音、U 清辅音、D 浊塞/塞擦、N 鼻音、L 流音/半元音、Q 促音、P を，后接元音），不打印歌词。
助词「は」「へ」「を」唱作 わ、え、お：官方注音不区分，这类不一致要人工看上下文决定。
"""
import html
import html.parser
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401

SMALL = set("ゃゅょぁぃぅぇぉゎ")
VOWEL_ROWS = {
    "a": "あかさたなはまやらわがざだばぱぁゃゎ",
    "i": "いきしちにひみりぎじぢびぴぃ",
    "u": "うくすつぬふむゆるぐずづぶぷぅゅゔ",
    "e": "えけせてねへめれげぜでべぺぇ",
    "o": "おこそとのほもよろをごぞどぼぽぉょ",
}
VOWEL_KANA = {"a": "あ", "i": "い", "u": "う", "e": "え", "o": "お"}


def mclass(m):
    """音节的音类 + 元音（不暴露歌词，供人工核对）：V/U/D/N/L/Q/P/X。"""
    if m is None:
        return "X"
    f = m[0]
    if m == "っ":
        return "Q"
    if m == "ん":
        return "N"
    v = vowel_of(m) or ""
    if f == "を":
        return "P" + v
    for c, row in (("V", "あいうえお"), ("U", "かきくけこさしすせそたちつてとはひふへほぱぴぷぺぽ"),
                   ("D", "がぎぐげござじずぜぞだぢづでどばびぶべぼゔ"), ("N", "なにぬねのまみむめも"), ("L", "やゆよらりるれろわ")):
        if f in row:
            return c + v
    return "?"


def to_hira(s):
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def vowel_of(mora):
    last = mora[-1]
    for v, row in VOWEL_ROWS.items():
        if last in row:
            return v
    return None


def morae(text):
    out = []
    for c in to_hira(text):
        if c in SMALL and out and out[-1] not in ("っ", "ん", "ー"):
            out[-1] += c
        elif c == "ー":
            v = vowel_of(out[-1]) if out else None
            out.append(VOWEL_KANA[v] if v else "ー")
        elif "ぁ" <= c <= "ゖ":
            out.append(c)
    return out


class HiraganaBlock(html.parser.HTMLParser):
    """收集 <div class="hiragana"> 里的文字：ruby 只取 rt（注音），<br> 换行。"""

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.inside = False
        self.skip_rb = 0
        self.span_stack = []
        self.lines = [""]

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class", "") or ""
        if tag == "div" and "hiragana" in cls.split() and not self.inside:
            self.inside, self.depth = True, 1
            return
        if not self.inside:
            return
        if tag == "div":
            self.depth += 1
        if tag == "br":
            self.lines.append("")
        if tag == "span":
            self.span_stack.append(cls)

    def handle_endtag(self, tag):
        if not self.inside:
            return
        if tag == "div":
            self.depth -= 1
            if self.depth == 0:
                self.inside = False
        if tag == "span" and self.span_stack:
            self.span_stack.pop()

    def handle_data(self, data):
        if self.inside and "rb" not in self.span_stack:
            self.lines[-1] += data


def align(a, b):
    """a = 谱面音节序列（None 表示延长音），b = 官方音节序列。半全局：b 两端的空隙免费。返回 (i, j) 对，缺的一边为 None。"""
    n, m = len(a), len(b)
    INF = 10 ** 9
    D = [[INF] * (m + 1) for _ in range(n + 1)]
    P = [[None] * (m + 1) for _ in range(n + 1)]
    for j in range(m + 1):
        D[0][j] = 0
    for i in range(1, n + 1):
        D[i][0] = D[i - 1][0] + 1
        P[i][0] = "up"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub = 0 if a[i - 1] == b[j - 1] else (0.6 if a[i - 1] is None and b[j - 1] in "あいうえお" else 1)
            cands = [(D[i - 1][j - 1] + sub, "diag"), (D[i - 1][j] + 1, "up"), (D[i][j - 1] + 1, "left")]
            D[i][j], P[i][j] = min(cands)
    j = min(range(m + 1), key=lambda k: D[n][k])
    end_j, i, pairs = j, n, []
    while i > 0:
        p = P[i][j]
        if p == "diag":
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif p == "up":
            pairs.append((i - 1, None))
            i -= 1
        else:
            pairs.append((None, j - 1))
            j -= 1
    return pairs[::-1], j, end_j, D[n][end_j]


def main():
    score_p, url, out = sys.argv[1:4]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    page = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="replace")
    p = HiraganaBlock()
    p.feed(page)
    lines = [html.unescape(s).strip() for s in p.lines]
    lines = [s for s in lines if s]
    seq, line_of = [], []
    for li, s in enumerate(lines):
        mm = morae(s)
        seq += mm
        line_of += [li] * len(mm)
    nonkana = sum(1 for s in lines for c in s if c.isascii() and c.isalnum())
    print(f"official: {len(lines)} lines, {len(seq)} morae, ascii alnum chars {nonkana}")
    notes = json.load(open(score_p, encoding="utf-8"))["notes"]
    a = [None if n["lyric"].isascii() else (morae(n["lyric"]) or [None])[0] for n in notes]
    multi = [n["idx"] for n in notes if len(morae(n["lyric"])) > 1]
    pairs, j0, j1, cost = align(a, seq)
    print(f"score notes {len(notes)}; aligned to official morae {j0}–{j1 - 1} (lines {line_of[j0] + 1}–{line_of[j1 - 1] + 1}), cost {cost}")
    print("notes whose lyric has >1 mora:", multi)
    rows, subs, ins, dels = [], [], [], []
    for i, j in pairs:
        if i is not None and j is not None:
            n = notes[i]
            rows.append({"note": n["idx"], "v2m": n["lyric"], "official": seq[j], "j": j, "line": line_of[j] + 1})
            if a[i] != seq[j]:
                subs.append((n["idx"], mclass(a[i]), mclass(seq[j]), line_of[j] + 1, j))
        elif i is not None:
            rows.append({"note": notes[i]["idx"], "v2m": notes[i]["lyric"], "official": None, "line": None})
            dels.append((notes[i]["idx"], mclass(a[i])))
        else:
            prev_note = rows[-1]["note"] if rows else None
            rows.append({"note": None, "after_note": prev_note, "v2m": None, "official": seq[j], "j": j, "line": line_of[j] + 1})
            ins.append((prev_note, mclass(seq[j]), line_of[j] + 1, j))
    print(f"matched {sum(1 for r in rows if r['note'] is not None and r['official'] is not None) - len(subs)}, "
          f"substituted {len(subs)}, note without official mora {len(dels)}, official mora without note {len(ins)}")
    for s in subs:
        print(f"  sub  #{s[0]:>3}: v2m {s[1]:<3} -> official {s[2]:<3} (line {s[3]}, j {s[4]})")
    for d in dels:
        print(f"  del  #{d[0]:>3}: v2m {d[1]} (no official mora)")
    for x in ins:
        print(f"  ins  after #{x[0]}: official {x[1]:<3} (line {x[2]}, j {x[3]})")
    json.dump({"url": url, "official_lines_used": [line_of[j0] + 1, line_of[j1 - 1] + 1], "official": seq, "line_of": line_of,
               "rows": rows},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
