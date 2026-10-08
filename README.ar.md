# القانون المدني المصري — اسأل (RAG)

خدمة تجيب عن الأسئلة المتعلقة بـ **القانون المدني المصري** (1149 مادة، عربي + إنجليزي) وتذكر **أرقام المواد** التي اعتمدت عليها.
ترفض الأسئلة الخارجة عن القانون، وتمنع الـ prompt injection، وتحذف البيانات الشخصية من السؤال.

[English README](README.md)

## 1) تشغيل سريع (دقيقتين، بدون إنترنت وبدون مفاتيح)

```bash
python -m venv .venv
source .venv/bin/activate            # ويندوز PowerShell:  .venv\Scripts\Activate.ps1
make setup                           # تثبيت الحزم
make corpus                          # تحويل الـ PDF إلى JSON (1149 مادة + فحص صحة)
make index                           # بناء الـ index (حوالي 10 ثواني)
make run                             # الـ API على http://localhost:8000  (وصفحة /docs)
```

**بتفضّل [uv](https://docs.astral.sh/uv/)؟** شغّال من غير أي تعديل (ملف `uv.lock` موجود فبتتثبّت نفس النسخ بالظبط):
```bash
uv sync --extra dev --extra ui       # بيعمل .venv ويثبّت كل حاجة
source .venv/bin/activate            # بعدها نفس أوامر make، أو: uv run make test
```

بدون `make` (ويندوز)؟ شغّل الأوامر دي بالترتيب: `prodml-build-corpus` ثم `prodml-ingest` ثم
`uvicorn prodml.api.main:get_app --factory --port 8000`.

جرّب سؤال (من terminal تاني):

```bash
curl -s -X POST localhost:8000/ask -H 'content-type: application/json' -d '{"question": "ماذا تقول المادة 805؟"}'
```

واجهة الشات: `make ui` ثم افتح http://localhost:8501 (والـ API لازم يكون شغال).

> **الوضع بدون مفاتيح تجريبي فقط.** بيستخدم embedder بسيط وLLM وهمي بينسخ نص أقرب مادة، فالنتائج متوسطة
> (مثلًا "ما هو عقد البيع؟" بيرجّع المادة 466 قبل المادة 418 اللي فيها التعريف). للنتائج الحقيقية استخدم موديلات حقيقية (القسم 3).

## 2) الاختبارات والتقييم

```bash
make test           # 48 اختبار
make lint           # فحص الكود
make eval           # تقييم 58 سؤال ← reports/latest_eval.json
make gate           # بوابة الجودة: تفشل (exit 1) لو الـ faithfulness أقل من 0.75
make experiments    # 12 تجربة (حجم الـ chunk / الـ embedding / الـ reranking)
```

**تنبيه مهم:** الـ index الافتراضي بيسمح بعملية واحدة بس. لو الـ API شغال، `make eval` و`make index` هيفشلوا برسالة واضحة.
إمّا توقف الـ API، أو تقيّم الـ API الشغال مباشرة:

```bash
prodml-eval --api http://localhost:8000 --out reports/latest_eval.json
```

## 3) استخدام موديلات حقيقية

انسخ `.env.example` إلى `.env` وعدّل القيم. **لازم تعيد `make index` بعد أي تغيير في موديل الـ embedding.**

**خيار أ — مجاني ومحلي بـ Ollama:**
```bash
ollama pull bge-m3 && ollama pull qwen2.5:7b
```
```ini
PRODML_EMBEDDING_PROVIDER=openai
PRODML_EMBEDDING_BASE_URL=http://localhost:11434/v1
PRODML_EMBEDDING_MODEL=bge-m3
PRODML_EMBEDDING_API_KEY=ollama
PRODML_LLM_PROVIDER=openai
PRODML_LLM_BASE_URL=http://localhost:11434/v1
PRODML_LLM_MODEL=qwen2.5:7b
```
**خيار ب — خدمات مدفوعة:** `PRODML_EMBEDDING_PROVIDER=cohere` (أو `openai`)، و`PRODML_LLM_PROVIDER=openai` مع
`PRODML_LLM_BASE_URL=https://api.openai.com/v1` و`PRODML_LLM_MODEL=gpt-4o-mini`.

**خيار ج — vLLM على GPU:** `docker compose --profile gpu up`.

بعد التبديل، اضبط `PRODML_MIN_SCORE` و`PRODML_MIN_COVERAGE` (حساسية رفض الأسئلة الخارجة عن القانون) بمتابعة `oos_accuracy` و`hit_at_k` من `make eval`.
الخيارات أ وب وج مكتوبة لكن **لم تُجرَّب end-to-end** بعد؛ الذي اتجرّب فعلًا هو الوضع التجريبي فقط.

## 4) تشغيل كل حاجة بـ Docker

```bash
cp .env.example .env
docker compose up --build -d
```

| الرابط | ماذا |
|---|---|
| http://localhost:8080 | الـ API من خلال nginx (stable + canary) — استخدم ده |
| http://localhost:9090 | Prometheus |
| http://localhost:9093 | Alertmanager (ضع الـ webhook في `monitoring/alertmanager.yml`) |
| http://localhost:3001 | Grafana (admin / admin) |

إضافات اختيارية: `--profile tracing` لـ Langfuse على :3000، و`--profile gpu` لـ vLLM.

الـ index بيتبنى جوه الـ image وقت الـ build، فنوع الـ embedding وقت الـ build لازم يطابق وقت التشغيل (الـ compose بيقراه من `.env`).
لو هتستخدم embedding مدفوع، ابنِ الـ image بالـ secret (القسم 4 في README الإنجليزي) ثم `docker compose up -d` بدون `--build`.

**الـ Canary:**
```bash
make canary PCT=10      # 10% من الطلبات للنسخة الجديدة
make canary PCT=0       # رجوع كامل للنسخة القديمة (rollback)
make canary PCT=100     # ترقية كاملة
```

**حلقة مراقبة الجودة:** شغّل `prodml-eval --api http://localhost:8080 --out reports/latest_eval.json` ← الـ API بيعرض النتيجة كـ metrics
← Prometheus بيطلّق تنبيه **FaithfulnessLow** لو أقل من 0.80. تنبيه **QueryDrift** بيطلع لو نوع الأسئلة ابتعد عن مجموعة التقييم.
اختبار الحمل: `make loadtest HOST=http://localhost:8080`.

## 5) حدود معروفة

- الوضع التجريبي ضعيف، وأرقام الموديلات الحقيقية لم تُقَس بعد.
- المادة 1022 ليس لها نص عربي في الـ PDF المصدر؛ مسجّلة كعيب معروف في المصدر ولم يُخترع لها نص.
- معلومات عامة وليست استشارة قانونية.
- لم يُنفَّذ فعليًا: Docker وGrafana وLangfuse الحقيقي وvLLM وAWQ وتقطير الـ reranker. التفاصيل في [reports/STATUS.md](reports/STATUS.md).
