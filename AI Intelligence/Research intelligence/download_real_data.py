from datasets import load_dataset
import json

print('Downloading real academic dataset from arXiv...')
dataset = load_dataset('arxiv', split='train', streaming=True)

real_theses = []
count = 0

for item in dataset:
    # Only take Computer Science papers with abstracts
    categories = item.get('categories', '')
    abstract = item.get('abstract', '')
    paper_id = item.get('id', 'unknown')
    
    if 'cs' in categories.lower() and abstract:
        real_theses.append({
            'document_id': f'arxiv_{count}',
            'chunk_id': f'arxiv_{count}_c1',
            'source_file': f'arxiv_{paper_id}.pdf',
            'page_number': 1,
            'text': abstract
        })
        count += 1
        if count >= 20:  # Download 20 real papers for our dataset
            break

with open('real_theses.json', 'w', encoding='utf-8') as f:
    json.dump(real_theses, f, indent=2)

print(f'✅ SUCCESS! Downloaded {count} real academic abstracts to real_theses.json')
