import urllib.request
import json
import random
import os
import re

print("Fetching REAL academic abstracts directly from arXiv API...")
# Query for 300 real Computer Science / Machine Learning papers
url = "http://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.LG&start=0&max_results=300"
req = urllib.request.Request(url, headers={'User-Agent': 'OAU-ThesisBank (wilsonafolabi2@gmail.com)'})

try:
    with urllib.request.urlopen(req) as response:
        xml_data = response.read().decode('utf-8')
    
    # Extract entries from XML
    entries = re.findall(r'<entry>(.*?)</entry>', xml_data, re.DOTALL)
    
    real_data = []
    for i, entry in enumerate(entries):
        title_match = re.search(r'<title>(.*?)</title>', entry, re.DOTALL)
        summary_match = re.search(r'<summary>(.*?)</summary>', entry, re.DOTALL)
        
        if title_match and summary_match:
            # Clean XML tags
            title = re.sub(r'<[^>]+>', '', title_match.group(1)).replace('\n', ' ').strip()
            summary = re.sub(r'<[^>]+>', '', summary_match.group(1)).replace('\n', ' ').strip()
            
            if len(summary) < 100:
                continue # Skip overly short abstracts
                
            # 1. SUPPORTED: A claim directly derived from the title/topic
            real_data.append({
                "document_id": f"arxiv_real_{i}",
                "chunk_id": f"arxiv_real_{i}_c1",
                "source_file": f"arxiv_{i}.pdf",
                "page_number": 1,
                "text": summary,
                "claim": f"This research paper focuses on the topic of {title.lower()}.",
                "label": "supported"
            })
            
            # 2. CONTRADICTED: A claim that is obviously false for a research paper
            real_data.append({
                "document_id": f"arxiv_real_{i}",
                "chunk_id": f"arxiv_real_{i}_c2",
                "source_file": f"arxiv_{i}.pdf",
                "page_number": 1,
                "text": summary,
                "claim": "This document contains no abstract, no methodology, and no scientific data.",
                "label": "contradicted"
            })
            
            # 3. NOT_MENTIONED: A plausible academic claim, but unrelated to this specific paper
            real_data.append({
                "document_id": f"arxiv_real_{i}",
                "chunk_id": f"arxiv_real_{i}_c3",
                "source_file": f"arxiv_{i}.pdf",
                "page_number": 1,
                "text": summary,
                "claim": "The authors conducted a randomized controlled trial with 10,000 human participants in a clinical setting.",
                "label": "not_mentioned"
            })

    random.shuffle(real_data)
    os.makedirs("output/docdm_dataset", exist_ok=True)
    
    total = len(real_data)
    with open("output/docdm_dataset/docdm_evidence_train.jsonl", "w", encoding="utf-8") as f:
        for item in real_data[:int(total*0.8)]: f.write(json.dumps(item) + "\n")
    with open("output/docdm_dataset/docdm_evidence_val.jsonl", "w", encoding="utf-8") as f:
        for item in real_data[int(total*0.8):int(total*0.9)]: f.write(json.dumps(item) + "\n")
    with open("output/docdm_dataset/docdm_evidence_test.jsonl", "w", encoding="utf-8") as f:
        for item in real_data[int(total*0.9):]: f.write(json.dumps(item) + "\n")
        
    print(f"✅ SUCCESS! Formatted {total} REAL academic training examples from arXiv.")
except Exception as e:
    print(f"❌ Failed to fetch data: {e}")
