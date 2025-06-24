# streamlit_drill_app.py

import streamlit as st
import random
import pandas as pd
import time
from datetime import datetime
import os
import fitz  # PyMuPDF
import matplotlib.pyplot as plt

# --- 定数 ---
NUM_QUESTIONS = 10
SAVE_FILE = "drill_history.csv"
WRONG_FILE = "mistake_history.csv"

# --- セッション初期化 ---
if "current_q" not in st.session_state:
    st.session_state.current_q = 0
    st.session_state.score = 0
    st.session_state.questions = []
    st.session_state.answers = []
    st.session_state.start_time = time.time()
    st.session_state.user_answers = [""] * NUM_QUESTIONS

# --- 類題テンプレート抽出 ---
def extract_templates_from_pdf(uploaded_file):
    text_templates = []
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    for page in doc:
        blocks = page.get_text("blocks")
        for b in blocks:
            line = b[4].strip()
            if any(op in line for op in ["+", "-", "×", "÷"]):
                if "□" in line or "?" in line:
                    text_templates.append(line)
    return text_templates[:NUM_QUESTIONS]

# --- 問題テンプレートから類題生成 ---
def generate_similar_question(template):
    try:
        if "+" in template:
            a, b = random.randint(10, 99), random.randint(10, 99)
            return f"{a} + {b} = ?", str(a + b)
        elif "-" in template:
            a, b = sorted([random.randint(10, 99), random.randint(10, 99)], reverse=True)
            return f"{a} - {b} = ?", str(a - b)
        elif "×" in template:
            a, b = random.randint(2, 9), random.randint(2, 9)
            return f"{a} × {b} = ?", str(a * b)
        elif "÷" in template:
            b = random.randint(2, 9)
            a = b * random.randint(2, 9)
            if "余り" in template:
                a += random.randint(1, b - 1)
                return f"{a} ÷ {b} = 商 ?, 余り ?", (str(a // b), str(a % b))
            else:
                return f"{a} ÷ {b} = ?", str(a // b)
    except:
        return "1 + 1 = ?", "2"

# --- PDFアップロード ---
uploaded_file = st.sidebar.file_uploader("📄 問題PDFをアップロード", type="pdf")
if uploaded_file and st.session_state.current_q == 0 and not st.session_state.questions:
    templates = extract_templates_from_pdf(uploaded_file)
    for template in templates:
        q, ans = generate_similar_question(template)
        st.session_state.questions.append(q)
        st.session_state.answers.append(ans)
    st.session_state.start_time = time.time()

# --- 問題がないときは自動生成 ---
if not st.session_state.questions:
    for _ in range(NUM_QUESTIONS):
        a, b = random.randint(10, 99), random.randint(10, 99)
        q = f"{a} + {b} = ?"
        st.session_state.questions.append(q)
        st.session_state.answers.append(str(a + b))

# --- ヘッダー ---
st.title("計算トレーニング 1日10問")
st.markdown(f"**問題 {st.session_state.current_q + 1} / {NUM_QUESTIONS}**")

# --- 問題表示 ---
current_question = st.session_state.questions[st.session_state.current_q]
user_input = st.text_input("問題:", value=st.session_state.user_answers[st.session_state.current_q], key=f"q{st.session_state.current_q}")

# --- 次へボタン ---
if st.button("次へ"):
    st.session_state.user_answers[st.session_state.current_q] = user_input
    st.session_state.current_q += 1

    if st.session_state.current_q >= NUM_QUESTIONS:
        # 採点
        correct = 0
        results = []
        wrong_rows = []
        for i in range(NUM_QUESTIONS):
            q = st.session_state.questions[i]
            ua = st.session_state.user_answers[i]
            ans = st.session_state.answers[i]

            if isinstance(ans, tuple):
                parts = ua.replace(" ", "").split(",")
                if len(parts) == 2 and parts[0] == ans[0] and parts[1] == ans[1]:
                    correct += 1
                    result = "◯"
                else:
                    result = "×"
            else:
                if ua.strip() == ans:
                    correct += 1
                    result = "◯"
                else:
                    result = "×"

            results.append((q, ua, ans, result))
            if result == "×":
                wrong_rows.append({"日時": datetime.now().strftime("%Y-%m-%d %H:%M"), "問題": q, "あなたの答え": ua, "正解": ans})

        elapsed = int(time.time() - st.session_state.start_time)

        # 履歴保存
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_row = pd.DataFrame({
            "日時": [now],
            "正解数": [correct],
            "時間（秒）": [elapsed]
        })
        if os.path.exists(SAVE_FILE):
            df = pd.read_csv(SAVE_FILE)
            df = pd.concat([df, new_row], ignore_index=True)
        else:
            df = new_row
        df.to_csv(SAVE_FILE, index=False)

        # 間違い保存
        if wrong_rows:
            wrong_df = pd.DataFrame(wrong_rows)
            if os.path.exists("mistake_history.csv"):
                existing = pd.read_csv("mistake_history.csv")
                wrong_df = pd.concat([existing, wrong_df], ignore_index=True)
            wrong_df.to_csv("mistake_history.csv", index=False)

        # 結果表示
        st.success(f"正解数: {correct} / {NUM_QUESTIONS}")
        st.info(f"所要時間: {elapsed} 秒")

        for q, ua, ans, r in results:
            st.write(f"{q} あなたの答え: {ua} / 正解: {ans} [{r}]")

        # 間違い抽出
        st.subheader("間違い直し")
        for i, (q, ua, ans, r) in enumerate(results):
            if r == "×":
                retry = st.text_input(f"復習: {q}", key=f"retry_{i}")

        # リセットボタン
        if st.button("もう一度挑戦"):
            st.session_state.clear()
            st.experimental_rerun()

        st.stop()

# --- 履歴表示 ---
st.sidebar.title("📊 成績履歴")
if os.path.exists(SAVE_FILE):
    hist = pd.read_csv(SAVE_FILE)
    st.sidebar.dataframe(hist.tail(10))

    st.sidebar.subheader("📈 推移グラフ")
    fig, ax = plt.subplots()
    ax.plot(hist["日時"], hist["正解数"], marker="o", label="正解数")
    ax.set_xticklabels(hist["日時"], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("正解数")
    ax.set_ylim(0, NUM_QUESTIONS + 1)
    ax.grid(True)
    st.sidebar.pyplot(fig)

    # 間違い履歴表示
    st.sidebar.subheader("❌ 間違い履歴")
    if os.path.exists("mistake_history.csv"):
        wrong_hist = pd.read_csv("mistake_history.csv")
        st.sidebar.dataframe(wrong_hist.tail(5))
else:
    st.sidebar.write("履歴はまだありません。")
