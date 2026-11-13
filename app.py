import json
import os
import re
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader

load_dotenv()

st.set_page_config(page_title="StudyGen", page_icon="📚", layout="wide")

st.title("📚 StudyGen")
st.caption("حوّل دروسك إلى أسئلة وتمارين وصحّح إجاباتك.")

def extract_pdf_text(file):
    reader = PdfReader(file)
    pages = []
    for i, page in enumerate(reader.pages, 1):
        txt = page.extract_text() or ""
        if txt.strip():
            pages.append(f"\n--- الصفحة {i} ---\n{txt}")
    return "\n".join(pages)

def clean_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)

def make_prompt(lesson, kind, difficulty, count):
    return f"""
أنت أستاذ جامعي وخبير في إعداد الاختبارات.
أنشئ {count} سؤالاً اعتماداً على الدرس المرفق فقط.

اللغة: العربية.
نوع الأسئلة: {kind}.
الصعوبة: {difficulty}.

قواعد مهمة:
1) لا تضف معلومة غير موجودة في الدرس إلا إذا كانت ضرورية جداً لصياغة السؤال.
2) لا تكرر نفس الفكرة بصيغ مختلفة.
3) اجعل الأسئلة مناسبة لطالب جامعي سنة أولى.
4) في QCM اجعل هناك إجابة صحيحة واحدة فقط.
5) في التمارين الحسابية ضع معطيات واضحة ومطلوباً واضحاً.
6) لا تعرض الحل في السؤال نفسه.
7) أعد النتيجة JSON صالحاً فقط بالشكل التالي:

{{
  "title": "عنوان الاختبار",
  "questions": [
    {{
      "id": 1,
      "type": "qcm",
      "question": "نص السؤال",
      "options": ["أ", "ب", "ج", "د"],
      "answer": "أ",
      "explanation": "شرح مختصر للحل"
    }}
  ]
}}

للأسئلة غير QCM اجعل options قائمة فارغة، واكتب answer كإجابة نموذجية.
عند إنشاء تمرين حسابي، يجب أن تكون answer حلاً واضحاً خطوة بخطوة.

الدرس:
{lesson}
"""

def call_ai(lesson, kind, difficulty, count):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("لم يتم العثور على OPENAI_API_KEY في ملف .env")

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-6.1-sol")
    prompt = make_prompt(lesson, kind, difficulty, count)

    response = client.responses.create(
        model=model,
        input=prompt,
    )
    return clean_json(response.output_text)

if "quiz" not in st.session_state:
    st.session_state.quiz = None
if "lesson" not in st.session_state:
    st.session_state.lesson = ""

with st.sidebar:
    st.header("⚙️ إعدادات")
    kind = st.selectbox(
        "نوع الأسئلة",
        ["QCM", "أسئلة مباشرة", "صح أو خطأ", "تمارين", "اختبار مختلط"],
    )
    difficulty = st.selectbox(
        "الصعوبة", ["سهل", "متوسط", "صعب", "مستوى امتحان الجامعة"]
    )
    count = st.slider("عدد الأسئلة", 5, 50, 20)
    st.divider()
    st.write("النموذج:", os.getenv("OPENAI_MODEL", "gpt-6.1-sol"))

uploaded = st.file_uploader(
    "📎 ارفع ملف الدرس",
    type=["pdf", "txt"],
    help="ابدأ بملف PDF نصي. سنضيف OCR للملفات المصورة في النسخة التالية."
)

if uploaded:
    if uploaded.type == "application/pdf":
        try:
            text = extract_pdf_text(uploaded)
        except Exception as e:
            st.error(f"تعذر قراءة PDF: {e}")
            text = ""
    else:
        text = uploaded.read().decode("utf-8", errors="ignore")

    if text:
        st.session_state.lesson = text
        st.success(f"تم استخراج الدرس: {len(text):,} حرف")
        with st.expander("معاينة محتوى الدرس"):
            st.text(text[:12000])
    else:
        st.warning("لم أستطع استخراج نص من الملف. إذا كان PDF عبارة عن صور ممسوحة، سنضيف OCR لاحقاً.")

if st.session_state.lesson:
    if st.button("🚀 إنشاء الأسئلة", type="primary", use_container_width=True):
        with st.spinner("يتم تحليل الدرس وإنشاء الأسئلة..."):
            try:
                st.session_state.quiz = call_ai(
                    st.session_state.lesson, kind, difficulty, count
                )
            except Exception as e:
                st.error(f"حدث خطأ: {e}")

quiz = st.session_state.quiz

if quiz:
    st.divider()
    st.subheader(f"📝 {quiz.get('title', 'اختبار')}")
    st.caption(f"عدد الأسئلة: {len(quiz.get('questions', []))}")

    answers = {}
    for q in quiz.get("questions", []):
        st.markdown(f"### {q['id']}. {q['question']}")
        if q["type"] == "qcm":
            answers[q["id"]] = st.radio(
                "اختر إجابة:",
                q.get("options", []),
                key=f"q_{q['id']}",
            )
        elif q["type"] == "true_false":
            answers[q["id"]] = st.radio(
                "اختر:",
                ["صح", "خطأ"],
                key=f"q_{q['id']}",
            )
        else:
            answers[q["id"]] = st.text_area(
                "إجابتك:",
                key=f"q_{q['id']}",
                height=100,
            )

    if st.button("✅ تصحيح الاختبار", use_container_width=True):
        score = 0
        total = len(quiz.get("questions", []))
        st.subheader("📊 النتيجة")

        for q in quiz.get("questions", []):
            user = str(answers.get(q["id"], "")).strip()
            correct = str(q.get("answer", "")).strip()

            if q["type"] in ("qcm", "true_false"):
                ok = user.lower() == correct.lower()
            else:
                # لا نحاول الحكم آلياً على الإجابات الطويلة.
                # نعرض الإجابة النموذجية للمقارنة.
                ok = False

            if ok:
                score += 1
                st.success(f"السؤال {q['id']}: صحيح ✓")
            else:
                st.error(f"السؤال {q['id']}: راجع إجابتك")
                st.write("**الإجابة النموذجية:**", correct)
                st.write("**الشرح:**", q.get("explanation", ""))

        st.metric("النتيجة", f"{score}/{total}")

        if total:
            percentage = score / total * 100
            if percentage >= 80:
                st.success("مستوى ممتاز. جرّب الآن مستوى أصعب.")
            elif percentage >= 60:
                st.info("مستوى جيد، لكن لديك نقاط تحتاج إلى مراجعة.")
            else:
                st.warning("أنصحك بمراجعة الدرس ثم إعادة الاختبار.")

st.divider()
st.caption("StudyGen — النسخة الأولى | يعمل محلياً على جهازك")
