#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dataset Truth Filter — purify_dataset.py
تنقية داتاست تدريب كامل من النصوص المسمومة (كلام بشري/AI ادُّعي أنه قرآن/حديث).

الأمانة الشرعية:
- لا يخزّن النص المقدّس. المطابقة حية عبر API.
- النص الذي يفشل أي بوابة => حجر صحي، لا تدريب.

الاستخدام:
  python3 purify_dataset.py dataset.jsonl --out clean.jsonl --quarantine poison.jsonl
  python3 purify_dataset.py dataset.json   # JSON array

صيغ الداتاست المدعومة:
  - JSONL: سطر واحد {"text": "...", "label": "...", ...} لكل سطر
  - JSON:  مصفوفة [{"text": "..."}, ...]
يدعم حقل النص بأسماء: text, content, input, prompt, completion, output
"""
import sys, json, argparse, os
from verify_claim import verify_claim

TEXT_KEYS = ["text", "content", "input", "prompt", "completion", "output", "response"]


def extract_text(obj):
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        for k in TEXT_KEYS:
            if k in obj and isinstance(obj[k], str):
                return obj[k]
    return ""


def load_records(path):
    recs = []
    if path.endswith(".jsonl"):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except Exception:
                    continue
    else:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            recs = data
        elif isinstance(data, dict) and "data" in data:
            recs = data["data"]
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--out", default="clean.jsonl")
    ap.add_argument("--quarantine", default="poison.jsonl")
    ap.add_argument("--type", default="auto", help="quran|hadith|ijma|auto")
    args = ap.parse_args()

    recs = load_records(args.dataset)
    total = len(recs)
    clean, poison = [], []
    stats = {"verified": 0, "POISON_quran_fabricated": 0, "POISON_hadith_fabricated": 0,
             "POISON_hadith_weak": 0, "POISON_ai_forged": 0, "unverified": 0}

    print(f"[{total}] سجلاً — جارٍ التنقية...\n")
    for i, rec in enumerate(recs, 1):
        text = extract_text(rec)
        res = verify_claim(text, args.type) if text else {"result": "unverified", "reason": "بلا نص"}
        rtype = res.get("result", "unverified")
        stats[rtype] = stats.get(rtype, 0) + 1
        if rtype == "verified":
            clean.append(rec)
        else:
            rec["_verdict"] = res
            poison.append(rec)
        if i % 25 == 0:
            print(f"  ... {i}/{total}")

    with open(args.out, "w", encoding="utf-8") as f:
        for rec in clean:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with open(args.quarantine, "w", encoding="utf-8") as f:
        for rec in poison:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    poison_n = len(poison)
    pct = (poison_n / total * 100) if total else 0
    print("\n" + "=" * 50)
    print("تقرير تنقية البيانات (Dataset Truth Filter)")
    print("=" * 50)
    print(f"الإجمالي:           {total}")
    print(f"نظيف (اجتاز):       {len(clean)}")
    print(f"سام (محجور):        {poison_n}  ({pct:.1f}%)")
    print("-" * 50)
    for k, v in stats.items():
        if v:
            print(f"  {k:<28} {v}")
    print("-" * 50)
    if pct >= 5:
        print("⚠️ نسبة تسمم عالية — لا تدرّب على هذه البيانات قبل المراجعة البشرية.")
    elif pct > 0:
        print("⚠️ تسمم جزئي — نظّف الحجر الصحي قبل التدريب.")
    else:
        print("✅ لا تسمم مكتشف في العيّنة المفحوصة.")
    print(f"\nالنظيف:  {args.out}")
    print(f"المحجور:  {args.quarantine}")
    print("\n* الفضل لله. هذه أداة ضوابط لا مُفتٍ؛ الحالات الحدّية للعلماء الموثوقين.")


if __name__ == "__main__":
    main()
