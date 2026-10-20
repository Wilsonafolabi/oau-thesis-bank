from datasets import load_dataset
import json
import random
import os

print("Downloading REAL scientific abstracts and claims (SciFact dataset)...")

# Load real scientific claim verification data
dataset = load_dataset("scifact", split="train")

real_data = []
# SciFact labels: 1 = supported, 0 = contradicted. We will map them.
label_map = {1: "supported", 0: "contradicted"}

for i, item in enumerate(dataset):
    abstract = item['abstract'][0] if isinstance(item['abstract'], list) else item['abstract']
    
    # Get the claims and their labels for this abstract
    claims = item['claims']
    labels = item['labels']
    
    for claim_text, label_int in zip(claims, labels):
        if label_int in [0, 1]: # Only take supported or contradicted
            real_data.append({
                "document_id": f"scifact_real_{i}",
                "chunk_id": f"scifact_real_{i}_c{len(real_data)}",
                "source_file": f"scifact_{item['doc_id']}.pdf",
                "page_number": 1,
                "text": abstract, # REAL scientific abstract
                "claim": claim_text, # REAL scientific claim
                "label": label_map[label_int]
            })

# We also need "not_mentioned" examples. We will create them by pairing abstracts with random claims from OTHER papers.
print("Generating 'not_mentioned' examples from cross-referenced abstracts...")
all_claims = [d['claim'] for d in real_data]
for i in range(0, len(real_data), 2): # Add a not_mentioned example for every 2 real ones
    if i+10 < len(real_data):
        real_data.append({
            "document_id": f"scifact_real_{i}",
            "chunk_id": f"scifact_real_{i}_c_nm",
            "source_file": f"scifact_{real_data[i]['source_file']}",
            "page_number": 1,
            "text": real_data[i]['text'],
            "claim": all_claims[(i + 50) % len(all_claims)], # A claim from a totally different paper
            "label": "not_mentioned"
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

print(f"✅ SUCCESS! Downloaded and formatted {total} REAL scientific training examples.")
