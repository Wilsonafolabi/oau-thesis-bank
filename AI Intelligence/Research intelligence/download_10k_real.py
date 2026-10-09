from datasets import load_dataset
import json
import random
import os

print("Downloading 10,000 REAL human-annotated examples from Stanford NLP...")

# Use the CORRECT namespace this time
dataset = load_dataset("stanfordnlp/snli", split="train[:10000]")

real_data = []
label_map = {0: "supported", 1: "not_mentioned", 2: "contradicted"}

for i, item in enumerate(dataset):
    if item['label'] == -1: 
        continue
        
    real_data.append({
        "document_id": f"snli_real_{i}", 
        "chunk_id": f"snli_real_{i}_c1",
        "source_file": "snli_real_corpus.pdf", 
        "page_number": 1,
        "text": item["premise"], 
        "claim": item["hypothesis"],
        "label": label_map[item["label"]]
    })

random.shuffle(real_data)
os.makedirs("output/docdm_dataset", exist_ok=True)

def save_jsonl(data, filename):
    with open(f"output/docdm_dataset/{filename}", "w", encoding="utf-8") as f:
        for item in data: 
            f.write(json.dumps(item) + "\n")

total = len(real_data)
save_jsonl(real_data[:int(total*0.8)], "docdm_evidence_train.jsonl")
save_jsonl(real_data[int(total*0.8):int(total*0.9)], "docdm_evidence_val.jsonl")
save_jsonl(real_data[int(total*0.9):], "docdm_evidence_test.jsonl")
save_jsonl(real_data, "docdm_evidence_raw.jsonl")

print(f"✅ SUCCESS! Downloaded and formatted {total} REAL training examples.")
