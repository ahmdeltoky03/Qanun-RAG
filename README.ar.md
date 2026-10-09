# قانون — Qanun-RAG: اسأل عن القانون المدني المصري

خدمة **Qanun-RAG** تجيب عن الأسئلة المتعلقة بـ **القانون المدني المصري** (1149 مادة، عربي + إنجليزي) وتذكر **أرقام المواد** التي اعتمدت عليها.
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

بدون `make` (ويندوز)؟ شغّل الأوامر دي بالترتيب: `qanun-build-corpus` ثم `qanun-ingest` ثم
`uvicorn qanun.api.main:get_app --factory --port 8000`.

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
qanun-eval --api http://localhost:8000 --out reports/latest_eval.json
```

## 3) استخدام موديلات حقيقية

انسخ `.env.example` إلى `.env` وعدّل القيم. **لازم تعيد `make index` بعد أي تغيير في موديل الـ embedding.**

**خيار أ — مجاني ومحلي بـ Ollama:**
```bash
ollama pull bge-m3 && ollama pull qwen2.5:7b-instruct
```
```ini
QANUN_EMBEDDING_PROVIDER=openai
QANUN_EMBEDDING_BASE_URL=http://localhost:11434/v1
QANUN_EMBEDDING_MODEL=bge-m3
QANUN_EMBEDDING_API_KEY=ollama
QANUN_LLM_PROVIDER=openai
QANUN_LLM_BASE_URL=http://localhost:11434/v1
QANUN_LLM_MODEL=qwen2.5:7b-instruct
```

**لو الموديلات على كولاب (Colab GPU) — الطريقة المستخدمة هنا — نفق ngrok:**

على كولاب، النوتبوك بيشغّل Ollama على **بورت 8000** ويعمل نفق بـ pyngrok:
```bash
!curl -fsSL https://ollama.com/install.sh | sh
!nohup bash -c "OLLAMA_HOST=0.0.0.0:8000 OLLAMA_ORIGIN=* ollama serve" &
!ollama pull qwen2.5:7b-instruct && !ollama pull bge-m3:latest
```
```python
from google.colab import userdata
from pyngrok import ngrok, conf
conf.get_default().auth_token = userdata.get('colab-ngrok')
print(ngrok.connect("8000").public_url)   # → https://XXXX-....ngrok-free.app
```
انسخ الرابط ده وحطّه في `QANUN_EMBEDDING_BASE_URL` و`QANUN_LLM_BASE_URL` **مع `/v1` في الآخر**،
بعدين **أعد `make index`** (أو `qanun-ingest`). ⚠️ روابط ngrok المجانية بتتغير كل ما النفق يعيد
(وكولاب بيفصل بعد شوية) — لو الرابط اتغير، عدّل `.env` وأعد بناء الـ index.

> Ollama على **كولاب:8000** (ورا ngrok)، والـ API بتاعك على **جهازك:8000** — جهازين مختلفين، مفيش تعارض بورتات.
**خيار ب — خدمات مدفوعة:** `QANUN_EMBEDDING_PROVIDER=cohere` (أو `openai`)، و`QANUN_LLM_PROVIDER=openai` مع
`QANUN_LLM_BASE_URL=https://api.openai.com/v1` و`QANUN_LLM_MODEL=gpt-4o-mini`.

**خيار ج — vLLM على GPU:** `docker compose --profile gpu up`.

بعد التبديل، اضبط `QANUN_MIN_SCORE` و`QANUN_MIN_COVERAGE` (حساسية رفض الأسئلة الخارجة عن القانون) بمتابعة `oos_accuracy` و`hit_at_k` من `make eval`.
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

**حلقة مراقبة الجودة:** شغّل `qanun-eval --api http://localhost:8080 --out reports/latest_eval.json` ← الـ API بيعرض النتيجة كـ metrics
← Prometheus بيطلّق تنبيه **FaithfulnessLow** لو أقل من 0.80. تنبيه **QueryDrift** بيطلع لو نوع الأسئلة ابتعد عن مجموعة التقييم.
اختبار الحمل: `make loadtest HOST=http://localhost:8080`.

## 5) حدود معروفة

- الوضع التجريبي ضعيف، وأرقام الموديلات الحقيقية لم تُقَس بعد.
- المادة 1022 ليس لها نص عربي في الـ PDF المصدر؛ مسجّلة كعيب معروف في المصدر ولم يُخترع لها نص.
- معلومات عامة وليست استشارة قانونية.
- لم يُنفَّذ فعليًا: Docker وGrafana وLangfuse الحقيقي وvLLM وAWQ وتقطير الـ reranker. التفاصيل في [reports/STATUS.md](reports/STATUS.md).
