"""Quantise the generator to 4-bit AWQ (needs a GPU; ~15 min for a 7B model on a T4/L4).

    pip install autoawq transformers
    python optimization/quantize_awq.py --model Qwen/Qwen2.5-7B-Instruct --out models/qwen2.5-7b-awq

Then serve it with vLLM (docker compose --profile gpu up) and compare before/after with
    qanun-eval --mode ragas --out reports/eval_fp16.json   (QANUN_LLM_MODEL = the fp16 model)
    qanun-eval --mode ragas --out reports/eval_awq.json    (QANUN_LLM_MODEL = the AWQ model)
    python optimization/compare.py reports/eval_fp16.json reports/eval_awq.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def calibration_texts(corpus: Path, n: int = 128) -> list[str]:
    """Calibrate on the real domain (Arabic + English legal text), not on generic web text."""
    recs = json.loads(corpus.read_text(encoding="utf-8"))
    texts = [r["text_ar"] for r in recs if not r["is_repealed"]][: n // 2] + [r["text_en"] for r in recs if not r["is_repealed"]][: n // 2]
    return [t for t in texts if len(t) > 80]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--corpus", type=Path, default=Path("data/processed/civil_code.json"))
    args = ap.parse_args()
    from awq import AutoAWQForCausalLM
    from transformers import AutoTokenizer

    model = AutoAWQForCausalLM.from_pretrained(args.model, safetensors=True)
    tok = AutoTokenizer.from_pretrained(args.model)
    cfg = {"zero_point": True, "q_group_size": 128, "w_bit": 4, "version": "GEMM"}
    model.quantize(tok, quant_config=cfg, calib_data=calibration_texts(args.corpus))
    model.save_quantized(args.out)
    tok.save_pretrained(args.out)
    print("saved", args.out)


if __name__ == "__main__":
    main()
