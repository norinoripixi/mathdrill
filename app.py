# app.py
# ------------------------------------------------------------
# 中学受験向け「計算問題」練習プリント自動生成アプリ（Streamlit）
# ・学年：小3〜小6（暫定）
# ・分野：学年別の代表的な「計算系」分野を収録
# ・難度：1〜5 段階で出題レンジや項数・入れ子を制御
# ・1回の生成：10問固定（要件に合わせて実装）
# ・PDF：A4・2ページ（表：問題／裏：模範解答）としてダウンロード
#
# 必要ライブラリ（requirements.txt 例）
#   streamlit==1.37.0
#   reportlab==4.2.2
#   numpy==2.0.1
#
# 日本語フォントについて：
#  - PDFに日本語を確実に埋め込むには IPAexGothic 等のTTFを同梱し、
#    assets/IPAexGothic.ttf を配置して FONT_PATH に指定すること。
#  - フォント未配置の場合は英数字のみの体裁となる。
# ------------------------------------------------------------

from __future__ import annotations
import io
import math
import random
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from typing import Callable, List, Tuple

import numpy as np
import streamlit as st

# PDF 出力（reportlab）
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm

# ====== フォント設定 ======
FONT_PATH = "assets/IPAexGothic.ttf"  # 置けない場合は英数字フォールバック
BASE_FONT_NAME = "IPAexGothic"

try:
    pdfmetrics.registerFont(TTFont(BASE_FONT_NAME, FONT_PATH))
    JP_FONT_OK = True
except Exception:
    # フォールバック（英数字のみ）
    JP_FONT_OK = False
    BASE_FONT_NAME = "Helvetica"

# ====== モデル ======
@dataclass
class Problem:
    text: str
    answer: str
    unit: str  # 分野
    difficulty: int

# ====== 学年と分野の定義（暫定・計算分野に限定） ======
GRADE_LABELS = ["小3", "小4", "小5", "小6"]

GRADE_UNITS = {
    "小3": [
        "整数のたし算・ひき算",
        "かけ算の筆算",
        "わり算（あまりあり）",
    ],
    "小4": [
        "大きな数と筆算",
        "小数の四則",
        "約数・倍数（計算）",
        "分数のたし算・ひき算",
    ],
    "小5": [
        "分数の四則混合",
        "小数×分数・分数×分数",
        "割合の基本計算",
        "比の基本計算",
    ],
    "小6": [
        "分数・小数の複合計算",
        "逆算（□を求める）",
        "最大公約数・最小公倍数",
        "比例・反比例の基本計算",
    ],
}

# ====== 汎用ユーティリティ ======

def rnd_int(rng: random.Random, low: int, high: int) -> int:
    return rng.randint(low, high)


def reduce_fraction(fr: Fraction) -> Fraction:
    # Fraction は自動で既約にするためラッパのみ
    return Fraction(fr.numerator, fr.denominator)


def frac_to_str(fr: Fraction) -> str:
    fr = reduce_fraction(fr)
    if fr.denominator == 1:
        return f"{fr.numerator}"
    # 帯分数化はしない（計算練習のため）
    return f"{fr.numerator}/{fr.denominator}"


# ====== 出題ジェネレータ群 ======
# 難度は 1..5：数字レンジ、項数、入れ子、混合度で調整

Generator = Callable[[random.Random, int], Problem]


def gen_int_add_sub(rng: random.Random, diff: int) -> Problem:
    # 整数のたし引き（桁増／項数増）
    digits = {1: 2, 2: 3, 3: 3, 4: 4, 5: 5}[diff]
    terms = {1: 2, 2: 3, 3: 4, 4: 4, 5: 5}[diff]
    max_n = 10 ** digits - 1
    nums = [rnd_int(rng, 0, max_n) for _ in range(terms)]
    ops = [rng.choice(["+", "-"]) for _ in range(terms - 1)]
    expr = " ".join(str(nums[i]) + (" " + ops[i] + " " if i < len(ops) else "") for i in range(terms))
    ans = str(eval(expr))
    return Problem(text=expr, answer=ans, unit="整数のたし算・ひき算", difficulty=diff)


def gen_mul_div(rng: random.Random, diff: int) -> Problem:
    # かけ算・わり算混合（整数）
    max_a = {1: 9, 2: 19, 3: 99, 4: 199, 5: 999}[diff]
    a = rnd_int(rng, 2, max_a)
    b = rnd_int(rng, 2, max_a)
    if rng.random() < 0.5:
        expr = f"{a} × {b}"
        ans = str(a * b)
    else:
        # わり切れるように調整
        ans_val = rnd_int(rng, 2, max(2, max_a // 2))
        expr = f"{a * ans_val} ÷ {ans_val}"
        ans = str(a)
    return Problem(text=expr, answer=ans, unit="かけ算の筆算", difficulty=diff)


def gen_div_remainder(rng: random.Random, diff: int) -> Problem:
    # あまりのあるわり算
    max_a = {1: 50, 2: 100, 3: 500, 4: 1000, 5: 5000}[diff]
    b = rnd_int(rng, 2, 9 + 3 * diff)
    a = rnd_int(rng, b + 1, max_a)
    q, r = divmod(a, b)
    if r == 0:
        # 強制的に余りが出るように
        a += 1
        q, r = divmod(a, b)
    expr = f"{a} ÷ {b}（あまりは？）"
    ans = f"商 {q}、あまり {r}"
    return Problem(text=expr, answer=ans, unit="わり算（あまりあり）", difficulty=diff)


def gen_decimal_mixed(rng: random.Random, diff: int) -> Problem:
    # 小数の四則（桁数増、項数増）
    places = {1: 1, 2: 1, 3: 2, 4: 3, 5: 3}[diff]
    terms = {1: 2, 2: 2, 3: 3, 4: 3, 5: 4}[diff]
    nums = [round(rng.uniform(0, 10 ** (1 + (diff // 2))), places) for _ in range(terms)]
    ops = [rng.choice(["+", "-", "×"]) for _ in range(terms - 1)]
    # × は最終的に eval 用に * に変換
    expr_disp = " ".join(f"{nums[i]}" + (" " + ops[i] + " " if i < len(ops) else "") for i in range(terms))
    expr_eval = expr_disp.replace("×", "*")
    ans = str(round(eval(expr_eval), max(2, places)))
    return Problem(text=expr_disp, answer=ans, unit="小数の四則", difficulty=diff)


def gen_frac_add_sub(rng: random.Random, diff: int) -> Problem:
    # 分数の足し引き
    max_d = {1: 5, 2: 7, 3: 9, 4: 12, 5: 15}[diff]
    a = Fraction(rnd_int(rng, 1, max_d - 1), rnd_int(rng, 2, max_d))
    b = Fraction(rnd_int(rng, 1, max_d - 1), rnd_int(rng, 2, max_d))
    op = rng.choice(["+", "-"])
    expr = f"{frac_to_str(a)} {op} {frac_to_str(b)}"
    ans = frac_to_str(a + b) if op == "+" else frac_to_str(a - b)
    return Problem(text=expr, answer=ans, unit="分数のたし算・ひき算", difficulty=diff)


def gen_frac_mixed(rng: random.Random, diff: int) -> Problem:
    # 分数の四則混合（2〜3項）
    max_d = {1: 6, 2: 9, 3: 12, 4: 15, 5: 18}[diff]
    terms = 2 if diff <= 2 else 3
    frs = [Fraction(rnd_int(rng, 1, max_d - 1), rnd_int(rng, 2, max_d)) for _ in range(terms)]
    ops = [rng.choice(["+", "-", "×", "÷"]) for _ in range(terms - 1)]
    expr = " ".join(frac_to_str(frs[i]) + (" " + ops[i] + " " if i < len(ops) else "") for i in range(terms))
    # 評価
    val = frs[0]
    for i, op in enumerate(ops):
        if op == "+":
            val = val + frs[i + 1]
        elif op == "-":
            val = val - frs[i + 1]
        elif op == "×":
            val = val * frs[i + 1]
        else:
            val = val / frs[i + 1]
    ans = frac_to_str(val)
    return Problem(text=expr, answer=ans, unit="分数の四則混合", difficulty=diff)


def gen_percent_basic(rng: random.Random, diff: int) -> Problem:
    # 割合の基本計算：○％の値や増減
    base = rnd_int(rng, 20, 500 * diff)
    p = rnd_int(rng, 5, 90)
    mode = rng.choice(["of", "up", "down"]) if diff >= 2 else "of"
    if mode == "of":
        expr = f"{p}% の {base} は？"
        ans = str(round(base * p / 100, 2))
    elif mode == "up":
        expr = f"{base} を {p}% 増やすと？"
        ans = str(round(base * (1 + p / 100), 2))
    else:
        expr = f"{base} を {p}% 減らすと？"
        ans = str(round(base * (1 - p / 100), 2))
    return Problem(text=expr, answer=ans, unit="割合の基本計算", difficulty=diff)


def gen_ratio_basic(rng: random.Random, diff: int) -> Problem:
    # 比の基本（等価比・内項外項）
    a = rnd_int(rng, 2, 9 + 2 * diff)
    b = rnd_int(rng, 2, 9 + 2 * diff)
    k = rnd_int(rng, 2, 5 + diff)
    mode = rng.choice(["等価比", "内項外項"]) if diff >= 2 else "等価比"
    if mode == "等価比":
        expr = f"a:b={a}:{b} のとき、{k*a}:{k*b} と等しい比を書け。"
        ans = f"{a}:{b}"
    else:
        # a:b = c:x で x
        c = rnd_int(rng, 2, 9 + 2 * diff)
        expr = f"{a}:{b} = {c}:x のとき x を求めよ。"
        # x = b*c/a
        x = Fraction(b * c, a)
        ans = frac_to_str(x)
    return Problem(text=expr, answer=ans, unit="比の基本計算", difficulty=diff)


def gen_gcd_lcm(rng: random.Random, diff: int) -> Problem:
    # 最大公約数・最小公倍数
    hi = {1: 40, 2: 60, 3: 90, 4: 120, 5: 200}[diff]
    x = rnd_int(rng, 6, hi)
    y = rnd_int(rng, 6, hi)
    mode = rng.choice(["gcd", "lcm"]) if diff >= 2 else "gcd"
    expr = f"{x} と {y} の{'最大公約数' if mode=='gcd' else '最小公倍数'}を求めよ。"
    g = math.gcd(x, y)
    l = x * y // g
    ans = str(g if mode == "gcd" else l)
    return Problem(text=expr, answer=ans, unit="最大公約数・最小公倍数", difficulty=diff)


def gen_inverse_box(rng: random.Random, diff: int) -> Problem:
    # 逆算（□）
    # 例： 36 ÷ □ = 4,  □ を求めよ
    op = rng.choice(["+", "-", "×", "÷"])
    a = rnd_int(rng, 2, 9 + 10 * diff)
    b = rnd_int(rng, 2, 9 + 10 * diff)
    if op == "+":
        expr = f"□ + {b} = {a + b}  のとき □ を求めよ。"
        ans = str(a)
    elif op == "-":
        expr = f"{a + b} - □ = {a}  のとき □ を求めよ。"
        ans = str(b)
    elif op == "×":
        expr = f"□ × {b} = {a * b}  のとき □ を求めよ。"
        ans = str(a)
    else:
        expr = f"{a * b} ÷ □ = {a}  のとき □ を求めよ。"
        ans = str(b)
    return Problem(text=expr, answer=ans, unit="逆算（□を求める）", difficulty=diff)

# 分野→ジェネレータ対応
UNIT_GENERATORS: dict[str, List[Generator]] = {
    "整数のたし算・ひき算": [gen_int_add_sub],
    "かけ算の筆算": [gen_mul_div],
    "わり算（あまりあり）": [gen_div_remainder],
    "大きな数と筆算": [gen_int_add_sub, gen_mul_div],
    "小数の四則": [gen_decimal_mixed],
    "約数・倍数（計算)": [gen_gcd_lcm],
    "分数のたし算・ひき算": [gen_frac_add_sub],
    "分数の四則混合": [gen_frac_mixed],
    "小数×分数・分数×分数": [gen_frac_mixed],
    "割合の基本計算": [gen_percent_basic],
    "比の基本計算": [gen_ratio_basic],
    "分数・小数の複合計算": [gen_frac_mixed, gen_decimal_mixed],
    "逆算（□を求める）": [gen_inverse_box],
    "最大公約数・最小公倍数": [gen_gcd_lcm],
    "比例・反比例の基本計算": [gen_ratio_basic],
}

# タイポ修正（キー統一）
UNIT_KEY_FIX = {
    "約数・倍数（計算）": "約数・倍数（計算)",
}


def pick_generators(units: List[str]) -> List[Generator]:
    gens: List[Generator] = []
    for u in units:
        key = UNIT_KEY_FIX.get(u, u)
        gens.extend(UNIT_GENERATORS.get(key, []))
    # 空ならデフォルト（安全策）
    return gens or [gen_int_add_sub]


def generate_set(seed: int, grade: str, units: List[str], difficulty: int, n: int = 10) -> List[Problem]:
    rng = random.Random(seed)
    gens = pick_generators(units)
    problems: List[Problem] = []
    for _ in range(n):
        g = rng.choice(gens)
        p = g(rng, difficulty)
        # 表示上の分野名を選択集合から推定
        p_unit = None
        for u in units:
            key = UNIT_KEY_FIX.get(u, u)
            if any(g is gg for gg in UNIT_GENERATORS.get(key, [])):
                p_unit = u
                break
        problems.append(Problem(text=p.text, answer=p.answer, unit=p_unit or p.unit, difficulty=difficulty))
    return problems


# ====== PDF 出力 ======

a4w, a4h = A4
MARGIN_X = 18 * mm
MARGIN_Y = 18 * mm
LINE_SPACING = 10 * mm


def draw_header(c: pdf_canvas.Canvas, title: str, subtitle: str = "") -> None:
    c.setFont(BASE_FONT_NAME, 14)
    c.drawString(MARGIN_X, a4h - MARGIN_Y, title)
    c.setFont(BASE_FONT_NAME, 10)
    c.drawRightString(a4w - MARGIN_X, a4h - MARGIN_Y, subtitle)


def draw_list(c: pdf_canvas.Canvas, items: List[str], start_no: int = 1) -> None:
    y = a4h - MARGIN_Y - 15 * mm
    c.setFont(BASE_FONT_NAME, 12)
    for idx, s in enumerate(items, start=start_no):
        if y < MARGIN_Y + 10 * mm:
            c.showPage()
            draw_header(c, "続き", "")
            c.setFont(BASE_FONT_NAME, 12)
            y = a4h - MARGIN_Y - 15 * mm
        c.drawString(MARGIN_X, y, f"{idx}. {s}")
        y -= LINE_SPACING


def make_pdf(problems: List[Problem], meta_title: str, meta_sub: str) -> bytes:
    buf = io.BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=A4)
    c.setTitle(meta_title)

    # --- 表：問題 ---
    draw_header(c, meta_title + "（問題）", meta_sub)
    q_texts = [p.text for p in problems]
    draw_list(c, q_texts, 1)
    c.showPage()

    # --- 裏：模範解答 ---
    draw_header(c, meta_title + "（模範解答）", meta_sub)
    a_texts = [f"{i+1}. {p.answer}" for i, p in enumerate(problems)]
    draw_list(c, a_texts, 1)

    c.save()
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


# ====== Streamlit UI ======
st.set_page_config(page_title="中学受験 算数・計算プリントメーカー", page_icon="🧮", layout="centered")

st.title("中学受験 算数・計算プリントメーカー（計算特化・v0.1）")

col1, col2 = st.columns(2)
with col1:
    grade = st.selectbox("学年", options=GRADE_LABELS, index=1)
with col2:
    difficulty = st.slider("難度（1=基礎〜5=発展）", min_value=1, max_value=5, value=3)

default_units = GRADE_UNITS.get(grade, [])
units = st.multiselect("分野（学年の推奨から選択・複数可）", options=sorted({u for us in GRADE_UNITS.values() for u in us}), default=default_units)

seed = st.number_input("シード（再現用）", min_value=0, max_value=10_000_000, value=random.randint(0, 999999), step=1, help="同じ条件で同じ問題を再現するための番号")

st.markdown("---")

if st.button("10問を作成", type="primary"):
    problems = generate_set(seed=int(seed), grade=grade, units=units or default_units, difficulty=int(difficulty), n=10)

    st.subheader("プレビュー（問題）")
    for i, p in enumerate(problems, 1):
        st.markdown(f"**{i}.** {p.text}  ")

    st.subheader("プレビュー（模範解答）")
    for i, p in enumerate(problems, 1):
        st.markdown(f"**{i}.** {p.answer}")

    # PDF 生成
    title = f"{grade} 計算プリント"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    subtitle = f"難度:{difficulty} / 分野:{'、'.join(units or default_units)} / 生成:{now}"

    pdf_bytes = make_pdf(problems, title, subtitle)
    st.download_button(
        label="A4・2ページPDFをダウンロード（表：問題／裏：模範解答）",
        data=pdf_bytes,
        file_name=f"{grade}_計算プリント_{now.replace(' ', '_').replace(':', '')}.pdf",
        mime="application/pdf",
    )

    if not JP_FONT_OK:
        st.info("PDFの日本語埋め込みフォントが見つからないため、英数字中心の体裁になっている。assets/IPAexGothic.ttf を同梱して再実行すると日本語も綺麗に出力できる。")

else:
    st.info("上の条件を選び、「10問を作成」を押すとプレビューとPDFダウンロードが表示される。")


# ====== 今後の拡張 TODO（メモ） ======
# - 問題フォーマット（四則のカッコ入れ・項数増・多段分数など）を難度でさらに精密化
# - 分野ごとの出題比率をUIで制御（例：分数6・小数2・割合2など）
# - レイアウト：2段組・方眼罫・解答欄（□）の描画
# - 問題IDと解答IDをCSV出力し、誤答分析に連携
# - 学年カバレッジの見直し（小1・小2の基礎計算版、受験ハイレベル拡張など）
# - 文章題の計算抽出（今回は対象外）
