# دبلوي Qanun-RAG مجاناً (لينك عام)

ده الـ runbook اللي بمشي عليه عشان أحط التطبيق كله ورا لينكين عامين أقدر
أشاركهم مع أي حد — **صفر جنيه في الشهر**، من غير كارت فيزا. الـ API بيشتغل على
Render المجاني، والواجهة على Vercel المجاني (Hobby). الاتنين بيعملوا deploy
أوتوماتيك من الريبو ده مع كل push على `main`.

English: [DEPLOY.md](DEPLOY.md)

```
Render (مجاني)                          Vercel (مجاني)
  qanun-api  ◄── fetch /ask/stream ──── واجهة qanun-rag
  https://qanun-api.onrender.com        https://qanun-rag.vercel.app
```

## "مجاني" دي بتكلفك إيه فعلاً (اقرا ده الأول)

المقايضات الصريحة للاستضافة المجانية، عشان العرض مايفاجئكش:

- **Cold start وإعادة بناء الـ index مرة.** نسخة Render المجانية بتنام بعد ~15
  دقيقة سكون. أول طلب بيصحّيها، ولأن الـ vector index (`data/index/`، 68 ميجا)
  متضاف في gitignore، سكربت الإقلاع بيعيد بناءه من الكوربس المتعمله commit قبل
  ما يقدّم الخدمة — حوالي **دقيقتين**، ماشي متبطئ تحت سقف الـ rate limit بتاع
  Cohere التجريبي. بعد كده بيبقى دافي وسريع لحد ما ينام تاني. دي أكبر عقبة في
  المستوى المجاني.
- **512 ميجا رام.** الـ Qdrant المدمج مع الـ API بيسعوا، بس مفيش مساحة زيادة
  للضغط. كفاية لكام حد يجرب؛ مش مناسب لـ load test.
- **كوتة Cohere التجريبية.** لينك عام يعني أي حد غريب بيصرف من كوتة الـ
  embeddings والـ chat بتاعتك. الكاش جوه العملية بيمتص التكرار، و
  `QANUN_EMBEDDING_RPM=18` بيخلي الـ ingest تحت سقف 20 طلب/دقيقة.
- **مفيش Langfuse / Prometheus / Grafana على الاستضافة.** دول stack الـ
  observability المحلي (Docker). الـ API المستضاف بيتعامل مع الـ tracing بلطف —
  بيجسّ مرة واحدة عند الإقلاع، مايلقاش collector، ويكمل من غيره.

لو تحب يبقى عندك لينك دايماً صاحي والـ index مخبوز جواه من غير cold-start
ingest، ده مسار Railway المدفوع (`railway.toml` + `deploy.yml`) — حوالي 5$
لمرة واحدة. الدليل ده بتاع المسار المجاني.

## 1. الـ API → Render (مجاني)

1. اعمل push للفرع ده على GitHub وادمجه في `main` (Render بيعمل deploy لـ `main`).
2. داشبورد Render → **New +** → **Blueprint** → وصّل ريبو
   `ahmdeltoky03/Qanun-RAG`. Render بيقرا [`render.yaml`](render.yaml) وبيعمل
   خدمة الويب المجانية `qanun-api` أوتوماتيك.
3. في الخدمة → **Environment**، حط التلات secrets اللي عليها `sync:false`:
   - `COHERE_API_KEY` بيتستخدم للمفتاحين اللي تحت — حط نفس مفتاح Cohere في
     `QANUN_EMBEDDING_API_KEY` و`QANUN_LLM_API_KEY`.
   - `QANUN_CORS_ORIGINS` — سيبه لخطوة 3 (محتاج لينك Vercel الأول)؛ حطه على
     `https://<your-vercel-app>.vercel.app`.
4. **Deploy** (أو اعمل push). بص على اللوجز: هتشوف
   `[boot] no vector index … building from corpus`، بعدها إحصائيات الـ ingest،
   بعدها `[boot] starting API`. أول إقلاع ≈ دقيقتين.
5. اتأكد: افتح `https://qanun-api.onrender.com/health` →
   `{"status":"ok","documents_indexed":1149,…}`. (`status:degraded` مع
   `documents_indexed:0` يعني الـ ingest ماخلصش — راجع مفتاح Cohere واللوجز.)

> **ليه runtime أصلي مش Docker على المجاني؟** الـ Dockerfile بيخبز الـ index وقت
> البناء وده أنضف، بس مستوى Render المجاني بيبقى أسعد بالـ Python runtime الأصلي
> مع سكربت الإقلاع اللي بيعمل ingest عند الطلب. نفس النتيجة، من غير لف ودوران
> build-secret لمفتاح Cohere.

## 2. الواجهة → Vercel (مجاني)

1. داشبورد Vercel → **Add New** → **Project** → استورد `ahmdeltoky03/Qanun-RAG`.
2. حط **Root Directory** = `frontend` (Vercel غالباً بيكتشفها؛ اتأكد).
3. تحت **Environment Variables**، ضيف:
   - `NEXT_PUBLIC_API_URL` = `https://qanun-api.onrender.com` (لينك Render بتاعك).
   ده بيتحط وقت البناء، فلازم يتظبط **قبل** أول deploy.
4. **Deploy.** هياخدك `https://<project>.vercel.app`.

`frontend/vercel.json` أصلا مثبّت إطار الـ Next.js وأمر البناء، فمفيش حاجة تانية
تتظبط.

## 3. اقفل دايرة الـ CORS

الواجهة بتكلم الـ API من المتصفح، فلازم الـ API يسمح بـ origin بتاع Vercel.
ارجع لـ Render → `qanun-api` → **Environment** → حط:

```
QANUN_CORS_ORIGINS = https://<project>.vercel.app
```

(افصل بفاصلة لو ضفت domain مخصص بعدين). احفظ → Render هيعمل redeploy. من غير
ده الواجهة هتقول **Offline** حتى لو `/health` شغال في تاب المتصفح. دي أكتر
حاجة الناس بتنساها.

## 4. شارك واتأكد

افتح لينك Vercel، اسأل سؤال — مثلاً *"ماذا تقول المادة 147؟"* — ولازم تيجي
إجابة مستندة بمصادرها. شارك اللينك ده مع أي حد.

فحوصات end-to-end سريعة:

```bash
# الـ API دافي ومتفهرس
curl https://qanun-api.onrender.com/health

# سؤال حقيقي (العربي في ملف UTF-8 بيتجنب تشويه الـ shell)
echo '{"question":"ماذا تقول المادة 147؟"}' > /tmp/q.json
curl -s -X POST https://qanun-api.onrender.com/ask \
  -H 'content-type: application/json' --data-binary @/tmp/q.json
```

## حاجات هتعضك

| العَرَض | الحل |
|---|---|
| الواجهة بتقول **Offline**، و`/health` شغال في المتصفح | `QANUN_CORS_ORIGINS` على Render مفيهوش لينك Vercel بالظبط (الـ scheme + الـ host، من غير شرطة في الآخر) |
| `/health` → `degraded`، `documents_indexed: 0` | الـ ingest فشل عند الإقلاع — راجع `QANUN_EMBEDDING_API_KEY` / `QANUN_LLM_API_KEY` (الاتنين = مفتاح Cohere بتاعك) واللوجز |
| أول طلب بياخد ~دقيقتين وبعدها يشتغل | cold start طبيعي للمستوى المجاني: النسخة صحيت وبنت الـ index مرة |
| `429` من Cohere وقت ingest الإقلاع | سقف الـ rate limit التجريبي — `QANUN_EMBEDDING_RPM=18` المفروض يمنعها؛ لو حصلت، أعد الـ deploy |
| كل الإجابات رفض | الـ index اتبني بس تحت الحد — زي المحلي بالظبط؛ الكوربس/الموديل تمام، بس اسأل سؤال قانوني داخل النطاق |

## الملفات اللي اتضافت على الفرع ده

- [`scripts/start-api.sh`](scripts/start-api.sh) — entrypoint الإقلاع: اعمل ingest لو مش موجود، بعدها قدّم الخدمة على `$PORT`.
- [`render.yaml`](render.yaml) — blueprint مجاني لـ Render لـ `qanun-api`.
- [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) — شغلانات Railway/Vercel الـ CLI بتتخطى دلوقتي لو الـ tokens مش موجودة، عشان `main` يفضل أخضر على المسار المجاني.
- `DEPLOY.md` / `DEPLOY.ar.md` — الدليل ده.
