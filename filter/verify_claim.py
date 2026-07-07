#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dataset Truth Filter — verify_claim.py
تحقق من ادعاء واحد (هل هو قرآن / حديث / إجماع صحيح، أم ملفّق/مولّد بـ AI).

الأمانة الشرعية:
- لا يخزّن هذا السكربت أي نص مقدّس. يجلب المصحف حياً من alquran.cloud للمطابقة فقط.
- المطابقة حرفية مطبّعة (تطبيع التشكيل والألف/الهمزة). لا تشابه لغوي.
- الحالات الحدّية ترجع لعالم موثوق (أهل الذكر) — لا يحسمها البرنامج.

الاستخدام:
  python3 verify_claim.py "نص يُدّعى أنه قرآن أو حديث"
  echo '{"text":"...","type":"quran"}' | python3 verify_claim.py -

يعتمد على curl (متاح في معظم البيئات). بدون إنترنت => result=unverified.
"""
import sys, json, subprocess, urllib.parse, re, unicodedata

QURAN_BASE = "https://api.alquran.cloud/v1"
DORAR_BASE = "https://dorar.net/dorar_api.json"

CACHE = {}  # مصحف كامل في الذاكرة خلال الجلسة


def _run_curl(url, timeout=25):
    try:
        out = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), "-A",
             "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
             url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        return out.stdout
    except Exception:
        return ""


def normalize_arabic(text):
    """تطبيع للنص العربي: إزالة التشكيل، توحيد الألف/الهمزة/الياء/التاء المربوطة."""
    if not text:
        return ""
    text = text.strip()
    # إزالة التشكيل وعلامات الترقيم القرآني
    text = re.sub(r"[\u064b-\u0652\u0670\u0640\u06d6-\u06ed]", "", text)
    # توحيد الهمزة إلى ألف بسيطة
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا")
    # توحيد الياء والألف المقصورة
    text = text.replace("ى", "ي")
    # توحيد التاء المربوطة إلى هاء
    text = text.replace("ة", "ه")
    # إزالة الترقيم والمسافات الزائدة
    text = re.sub(r"[،؛؟.:!،«»\"'()\-_=/]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_full_quran():
    """جلب المصحف كاملاً (114 سورة) حياً مرة واحدة وتخزينه مطبّعاً في الذاكرة."""
    global CACHE
    if CACHE:
        return CACHE
    verses = set()
    for s in range(1, 115):
        raw = _run_curl(f"{QURAN_BASE}/surah/{s}/ar")
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if not isinstance(data, dict) or data.get("code") != 200:
            continue
        for a in data["data"].get("ayahs", []):
            t = a.get("text", "")
            verses.add(normalize_arabic(t))
    CACHE = verses
    return CACHE


def verify_quran(text):
    norm = normalize_arabic(text)
    if len(norm) < 5:
        return {"result": "unverified", "reason": "نص قصير جداً — لا يمكن المطابقة"}
    verses = load_full_quran()
    if not verses:
        return {"result": "unverified", "reason": "تعذّر جلب المصحف (لا إنترنت؟)"}
    if norm in verses:
        return {"result": "verified", "reason": "مطابقة حرفية تامة مع المصحف"}
    # رفض أي تشابه جزئي — لا نقبل الاحتمال
    for v in verses:
        if norm and (norm in v or v in norm) and abs(len(norm) - len(v)) <= 4:
            return {
                "result": "POISON_quran_fabricated",
                "reason": "قريب من آية لكنه ليس مطابقاً حرفياً — تزوير/تحريف",
            }
    return {"result": "POISON_quran_fabricated", "reason": "غير موجود في المصحف إطلاقاً"}


def verify_dorar(text, kind="hadith"):
    q = urllib.parse.quote(text[:60])
    raw = _run_curl(f"{DORAR_BASE}?skey={q}&callback=?")
    if not raw or "<!DOCTYPE" in raw or "Attention Required" in raw:
        # Cloudflare block أو لا إنترنت => لا نستطيع التحقق => unverified (لا ادّعاء)
        return {"result": "unverified", "reason": "تعذّر الوصول لـ dorar.net (حجب/لا إنترنت) — يلزم مراجعة بشرية"}
    # dorar يرجع JSONP: "?({...});" — نزيل الـ wrapper
    raw = raw.strip()
    if raw.startswith("?("):
        raw = raw[2:]
    elif raw.startswith("?"):
        raw = raw[1:]
    if raw.endswith(");"):
        raw = raw[:-2]
    elif raw.endswith(")"):
        raw = raw[:-1]
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except Exception:
        return {"result": "unverified", "reason": "استجابة غير مفهومة من dorar.net — يلزم مراجعة بشرية"}
    rows = data.get("ahadith", {})
    html = rows.get("result", "") if isinstance(rows, dict) else str(rows)
    if not html or "hadith" not in html:
        return {
            "result": "POISON_hadith_fabricated" if kind == "hadith" else "unverified",
            "reason": "غير موجود في الدرر السنية",
        }
    # النتائج بصيغة HTML — نبحث عن درجة الصحة في النص
    grade = ""
    m = re.search(r"<span[^>]*class=\"\\w*grade\"[^>]*>([^<]+)<\/span>", html)
    if m:
        grade = m.group(1).strip()
    else:
        # احتياط: ابحث عن كلمة صحيح/حسن/ضعيف في النص
        for g in ["صحيح", "حسن", "ضعيف", "موضوع"]:
            if g in html:
                grade = g
                break
    if any(g in grade for g in ["صحيح", "حسن"]):
        return {"result": "verified", "reason": f"موجود بدرجة: {grade}"}
    if grade:
        return {"result": "POISON_hadith_weak", "reason": f"موجود لكن درجته: {grade}"}
    return {"result": "verified", "reason": "موجود في الدرر السنية (لم تُستخرج الدرجة تلقائياً — يلزم مراجعة)"}


def verify_claim(text, claim_type="auto"):
    """نقطة الدخول. claim_type: quran | hadith | ijma | auto"""
    if not text or not text.strip():
        return {"result": "unverified", "reason": "نص فارغ"}
    # بصمة AI: علامات أولية (لا قطعية — ترجع لبشر)
    ai_hint = len(text) > 400 and text.count(".") == 0 and "ﷺ" not in text and "قال" not in text
    if claim_type in ("quran", "auto"):
        r = verify_quran(text)
        if claim_type == "quran":
            return dict(claim_type="quran", **r)
        # auto: المطابقة التامة فقط تثبت أنه قرآن؛ عدم المطابقة لا يعني تزويراً
        # (النص قد يكون حديثاً أو كلاماً بشرياً) — نمر لبوابة الحديث
        if r["result"] == "verified":
            return dict(claim_type="quran", **r)
        quran_fail = r  # نحتفظ به كمرجع فقط عند ادّعاء صريح
    if claim_type in ("hadith", "ijma", "auto"):
        r = verify_dorar(text, kind=claim_type if claim_type != "auto" else "hadith")
        if claim_type != "auto" or r["result"] != "unverified":
            return dict(claim_type=claim_type if claim_type != "auto" else "hadith", **r)
        # auto: فشل الحديث أيضاً => لا قرآن مؤكّد ولا حديث مؤكّد
        return {"claim_type": "unknown", "result": "unverified",
                "reason": "لا مطابقة قرآنية تامة، ولا تحقق حديثي متاح (حجب/لا إنترنت) — يلزم مراجعة بشرية (أهل الذكر)"}
    if ai_hint:
        return {"claim_type": "ai_forged", "result": "POISON_ai_forged",
                "reason": "علامات أولية لنص مولّد بـ AI ادُّعي أنه وحي — يلزم مراجعة بشرية"}
    return {"claim_type": "unknown", "result": "unverified",
            "reason": "لم يُتعرّف على النوع — يلزم مراجعة بشرية (أهل الذكر)"}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "-":
        payload = sys.stdin.read().strip()
        try:
            obj = json.loads(payload)
            text = obj.get("text", "")
            ctype = obj.get("type", "auto")
        except Exception:
            text, ctype = payload, "auto"
    elif len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        ctype = "auto"
    else:
        print("الاستخدام: python3 verify_claim.py \"نص\"  |  echo '{\"text\":\"...\",\"type\":\"quran\"}' | python3 verify_claim.py -")
        sys.exit(2)
    res = verify_claim(text, ctype)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
