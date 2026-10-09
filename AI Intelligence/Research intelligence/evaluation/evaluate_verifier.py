import json, asyncio, sys
from pathlib import Path
from datetime import datetime, timezone
from document_processing.verifier import EvidenceVerifier

LABELS = ["supported", "contradicted", "not_mentioned"]

def macro_f1(per_label):
    f1s = []
    for lb in LABELS:
        tp = per_label[lb]["tp"]; fp = per_label[lb]["fp"]; fn = per_label[lb]["fn"]
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if (prec + rec) else 0.0)
    return sum(f1s) / len(f1s)

async def evaluate_verifier():
    dataset_path = Path("output/docdm_dataset/docdm_evidence_test.jsonl")
    if not dataset_path.exists():
        print(f"FATAL: test dataset missing at {dataset_path}. Run scripts/build_docdm_dataset_v2.py first.")
        raise SystemExit(2)
    examples = []
    with open(dataset_path, 'r', encoding='utf-8-sig') as f:
        for line in f:
            if line.strip():
                examples.append(json.loads(line))
    if not examples:
        print(f"FATAL: test dataset at {dataset_path} is EMPTY. Refuse to report meaningless accuracy. "
              "Re-run the builder so every split contains at least one document.")
        raise SystemExit(2)

    verifier = EvidenceVerifier()
    per_label = {lb: {"tp": 0, "fp": 0, "fn": 0} for lb in LABELS}
    correct = 0
    print(f"Evaluating {len(examples)} test examples...")
    for i, ex in enumerate(examples, 1):
        expected = ex['label']
        try:
            result = await verifier.verify_claim(ex['text'], ex['claim'])
            got = str(result.get('label', '')).lower()
        except Exception as e:
            got = f"error: {e}"
        ok = got == expected
        correct += int(ok)
        for lb in LABELS:
            if lb == expected and ok: per_label[lb]["tp"] += 1
            elif lb == expected and not ok: per_label[lb]["fn"] += 1
            elif lb == got and not ok: per_label[lb]["fp"] += 1
        print(f"[{i}/{len(examples)}] expected={expected} got={got} ok={ok}")

    accuracy = correct / len(examples)
    mf1 = macro_f1(per_label)
    results = {"timestamp": datetime.now(timezone.utc).isoformat(), "n": len(examples),
               "accuracy": accuracy, "macro_f1": mf1, "per_label": per_label}
    Path("output").mkdir(exist_ok=True)
    with open("output/evaluation_results.json", 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    with open("EVALUATION_LOG.md", 'a', encoding='utf-8') as f:
        f.write(f"\n- {results['timestamp']} | verifier=LLM | n={len(examples)} | acc={accuracy:.3f} | macro_f1={mf1:.3f}")
    print(f"Evaluation complete: accuracy={accuracy:.3f} macro_f1={mf1:.3f}")
    if accuracy == 0.0:
        raise SystemExit(1)

if __name__ == "__main__":
    asyncio.run(evaluate_verifier())
