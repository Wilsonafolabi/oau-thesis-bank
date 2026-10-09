import os, json, hashlib, logging, time, random, argparse
import httpx
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

GEN_MODEL = os.getenv("DOCDM_GEN_MODEL", "patataaliena/qwen2.5-vl-7b-instruct")
JUDGE_MODEL = os.getenv("DOCDM_JUDGE_MODEL", "patataaliena/qwen2.5-vl-7b-instruct")
OLLAMA_URL = os.getenv("DOCDM_OLLAMA_URL", "http://127.0.0.1:1234")
API_KEY = os.getenv("DOCDM_API_KEY", "lm-studio")

class LLMClient:
    def __init__(self):
        self.base_url = OLLAMA_URL.rstrip('/')
        self.cache = {}
        try:
            httpx.get(f"{self.base_url}/v1/models", timeout=5.0, headers={"Authorization": f"Bearer {API_KEY}"})
        except Exception as e:
            raise RuntimeError(f"Cannot connect to LLM API at {self.base_url}: {e}")

    def _call_api(self, prompt: str, system_prompt: str, model: str) -> str:
        cache_key = hashlib.md5(f"{prompt}{model}".encode()).hexdigest()
        if cache_key in self.cache:
            return self.cache[cache_key]
        for attempt in range(5):
            try:
                resp = httpx.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={"model": model,
                          "messages": [{"role": "system", "content": system_prompt},
                                       {"role": "user", "content": prompt}],
                          "temperature": 0.3},
                    headers={"Authorization": f"Bearer {API_KEY}"}, timeout=120.0)
                resp.raise_for_status()
                text = resp.json()['choices'][0]['message']['content'].strip()
                text = text.replace("```json", "").replace("```", "").strip()
                self.cache[cache_key] = text
                return text
            except Exception as e:
                wait_time = 2 ** attempt
                logging.warning(f"LLM call failed (attempt {attempt+1}): {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
        raise RuntimeError("LLM call failed after 5 retries.")

class DocDMBuilder:
    def __init__(self, chunks_file: str, output_dir: str):
        self.client = LLMClient()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with open(chunks_file, 'r', encoding='utf-8-sig') as f:
            self.all_chunks = json.load(f)
        self.doc_chunks = defaultdict(list)
        for chunk in self.all_chunks:
            self.doc_chunks[chunk['document_id']].append(chunk)
        self.doc_ids = list(self.doc_chunks.keys())
        self.checkpoint_file = self.output_dir / "builder_checkpoint.json"
        self.processed_docs = set()
        if self.checkpoint_file.exists():
            with open(self.checkpoint_file, 'r', encoding='utf-8-sig') as f:
                self.processed_docs = set(json.load(f).get("processed_docs", []))
            logging.info(f"Resuming builder. {len(self.processed_docs)} documents already processed.")
        self.existing = self._load_existing()

    def _load_existing(self) -> Dict[str, Dict]:
        raw = self.output_dir / "docdm_evidence_raw.jsonl"
        out = {}
        if raw.exists():
            with open(raw, 'r', encoding='utf-8-sig') as f:
                for line in f:
                    if line.strip():
                        ex = json.loads(line)
                        out[ex['example_id']] = ex
        return out

    def split_documents(self):
        random.seed(42)
        random.shuffle(self.doc_ids)
        n = len(self.doc_ids)
        if n >= 3:
            self.train_docs = set(self.doc_ids[:n-2])
            self.val_docs = {self.doc_ids[n-2]}
            self.test_docs = {self.doc_ids[n-1]}
        elif n == 2:
            self.train_docs = {self.doc_ids[0]}
            self.val_docs = set()
            self.test_docs = {self.doc_ids[1]}
        else:
            self.train_docs = set(self.doc_ids)
            self.val_docs = set()
            self.test_docs = set()
        logging.info(f"Split: Train={len(self.train_docs)}, Val={len(self.val_docs)}, Test={len(self.test_docs)}")

    def _get_split(self, doc_id: str) -> str:
        if doc_id in self.train_docs: return "train"
        if doc_id in self.val_docs: return "val"
        return "test"

    def generate_claim(self, text: str, claim_type: str) -> Dict[str, Any]:
        if claim_type == "supported":
            prompt = f"Read this academic passage and generate exactly ONE factual claim DIRECTLY supported by it. Output JSON: {{\"claim\": \"string\"}}\n\nPassage: {text}"
        elif claim_type == "contradicted":
            prompt = f"Read this academic passage and generate exactly ONE factual claim that DIRECTLY CONTRADICTS a fact in it. Output JSON: {{\"claim\": \"string\"}}\n\nPassage: {text}"
        else:
            prompt = f"Read this academic passage and generate exactly ONE plausible academic claim GENUINELY ABSENT from it. Output JSON: {{\"claim\": \"string\"}}\n\nPassage: {text}"
        try:
            return json.loads(self.client._call_api(prompt, "You are an expert academic data generator. Output ONLY valid JSON.", GEN_MODEL))
        except Exception as e:
            logging.error(f"Generator failed for {claim_type}: {e}")
            return {"claim": "", "error": str(e)}

    def judge_claim(self, passage: str, claim: str) -> Dict[str, Any]:
        prompt = f"Is the claim 'supported', 'contradicted', or 'not_mentioned' by the passage? Output JSON: {{\"label\": \"string\", \"reason\": \"string\"}}\n\nPassage: {passage}\nClaim: {claim}"
        try:
            return json.loads(self.client._call_api(prompt, "You are a strict academic fact-checker. Output ONLY valid JSON.", JUDGE_MODEL))
        except Exception as e:
            logging.error(f"Judge failed: {e}")
            return {"label": "error", "reason": str(e)}

    def build_dataset(self, max_docs: Optional[int] = None):
        self.split_documents()
        stats = {"gen_fail": 0, "judge_fail": 0, "rejected": 0, "duplicates": 0}
        seen_claims = set(ex['claim'] for ex in self.existing.values())
        new_examples = []
        remaining = [d for d in self.doc_ids if d not in self.processed_docs]
        if max_docs is not None:
            remaining = remaining[:max_docs]
        for doc_id in remaining:
            split = self._get_split(doc_id)
            for chunk in self.doc_chunks[doc_id]:
                text = chunk['text']
                candidates = [("supported", doc_id), ("contradicted", doc_id)]
                same_split = [d for d in self.doc_ids if self._get_split(d) == split and d != doc_id]
                if same_split:
                    candidates.append(("not_mentioned", random.choice(same_split)))
                for ctype, claim_src in candidates:
                    src_text = text if ctype != "not_mentioned" else random.choice(self.doc_chunks[claim_src])['text']
                    gen_res = self.generate_claim(src_text, ctype)
                    if not gen_res.get("claim"):
                        stats["gen_fail"] += 1; continue
                    claim = gen_res["claim"]
                    judge_res = self.judge_claim(text, claim)
                    if judge_res.get("label", "").lower() != ctype:
                        stats["rejected"] += 1; continue
                    ex_id = hashlib.md5(f"{doc_id}_{chunk['chunk_id']}_{claim}".encode()).hexdigest()
                    if ex_id in self.existing or claim in seen_claims:
                        stats["duplicates"] += 1; continue
                    seen_claims.add(claim)
                    new_examples.append({
                        "example_id": ex_id, "document_id": doc_id, "chunk_id": chunk['chunk_id'],
                        "source_file": chunk.get("source_file", "unknown"), "page_number": chunk.get("page_number", 1),
                        "text": text, "claim": claim, "label": ctype,
                        "generation_model": GEN_MODEL, "judge_model": JUDGE_MODEL,
                        "validation_status": "passed", "validation_reason": judge_res.get("reason", ""),
                        "split": split, "candidate_type": ctype,
                        "source_document_id": doc_id, "claim_source_document_id": claim_src})
            self.processed_docs.add(doc_id)
            self._save_checkpoint()
        merged = dict(self.existing)
        for ex in new_examples:
            merged[ex['example_id']] = ex
        self._save_outputs(list(merged.values()), stats)

    def _save_checkpoint(self):
        with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump({"processed_docs": list(self.processed_docs)}, f)

    def _save_outputs(self, examples: List[Dict], stats: Dict):
        def write_jsonl(data, filename):
            with open(self.output_dir / filename, 'w', encoding='utf-8') as f:
                for item in data: f.write(json.dumps(item) + '\n')
        write_jsonl(examples, "docdm_evidence_raw.jsonl")
        write_jsonl([e for e in examples if e['split'] == 'train'], "docdm_evidence_train.jsonl")
        write_jsonl([e for e in examples if e['split'] == 'val'], "docdm_evidence_val.jsonl")
        write_jsonl([e for e in examples if e['split'] == 'test'], "docdm_evidence_test.jsonl")
        write_jsonl([{ "total_documents": len(self.doc_ids), "train_documents": len(self.train_docs),
                       "val_documents": len(self.val_docs), "test_documents": len(self.test_docs),
                       "total_examples": len(examples), "gen_model": GEN_MODEL, "judge_model": JUDGE_MODEL }],
                    "docdm_manifest.jsonl")
        total = len(examples) or 1
        stats_out = {
            "examples_per_label": {lb: sum(1 for e in examples if e['label'] == lb) for lb in ["supported", "contradicted", "not_mentioned"]},
            "documents_per_split": {"train": len(self.train_docs), "val": len(self.val_docs), "test": len(self.test_docs)},
            "examples_per_document": {d: sum(1 for e in examples if e['document_id'] == d) for d in self.doc_ids},
            "average_passage_length": sum(len(e['text']) for e in examples) / total,
            "average_claim_length": sum(len(e['claim']) for e in examples) / total,
            "validation_rejection_rate": stats["rejected"] / total,
            "generator_failure_rate": stats["gen_fail"] / total,
            "judge_failure_rate": stats["judge_fail"] / total,
            "duplicate_rate": stats["duplicates"] / total}
        with open(self.output_dir / "docdm_dataset_stats.json", 'w', encoding='utf-8') as f:
            json.dump(stats_out, f, indent=2)
        logging.info(f"Builder complete. {len(examples)} total examples saved to {self.output_dir}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--chunks-file", default="ingested_chunks_sample.json")
    p.add_argument("--output-dir", default="output/docdm_dataset")
    p.add_argument("--max-docs", type=int, default=None)
    args = p.parse_args()
    DocDMBuilder(args.chunks_file, args.output_dir).build_dataset(max_docs=args.max_docs)
