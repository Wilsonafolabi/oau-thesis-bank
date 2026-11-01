---
language:
- en
license: apache-2.0
library_name: transformers
pipeline_tag: text-classification
datasets:
- rasbt/human-vs-ai-50k
base_model: answerdotai/ModernBERT-base
base_model_relation: finetune
metrics:
- accuracy
tags:
- ai-text-detection
- binary-classification
---

# ModernBERT AI-Text Detector

This is a fully fine-tuned ModernBERT-base classifier for distinguishing human-written and AI-generated text. It was trained on [`rasbt/human-vs-ai-50k`](https://huggingface.co/datasets/rasbt/human-vs-ai-50k). Human-written text has label 0 and AI-generated text has label 1.

The model supports sequences up to 8,192 tokens. Temperature scaling is applied during inference. The recorded best validation accuracy was 99.71%.

&nbsp;
## Download and use

```bash
hf download rasbt/ai-text-detector-modernbert \
  --local-dir models/ai-text-detector-modernbert
```

```python
import json
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


model_dir = Path("models/ai-text-detector-modernbert")
metadata = json.loads(
    (model_dir / "detector-config.json").read_text(encoding="utf-8")
)
tokenizer = AutoTokenizer.from_pretrained(model_dir)
model = AutoModelForSequenceClassification.from_pretrained(model_dir)
model.eval()

text = "Paste the text to classify here."
inputs = tokenizer(
    text,
    truncation=True,
    max_length=metadata["max_length"],
    return_tensors="pt",
)

with torch.inference_mode():
    logits = model(**inputs).logits / metadata["temperature"]
    probabilities = logits.float().softmax(dim=-1)

ai_index = metadata["label_mapping"]["ai"]
ai_probability = probabilities[0, ai_index].item()
print({"score": round(100 * ai_probability, 4)})
```

&nbsp;
## Test-set confusion matrix

![ModernBERT test-set confusion matrix](figures/confusion-matrix.svg)

`detector-config.json` contains the calibration temperature and training metadata. The recommended inference implementation is provided in the [`rasbt/ai-detector`](https://github.com/rasbt/ai-detector) repository.

&nbsp;
## Related models

- [TF-IDF logistic regression](https://huggingface.co/rasbt/ai-text-detector-logreg)
- [DistilBERT](https://huggingface.co/rasbt/ai-text-detector-distilbert)
- [DistilBERT with LoRA](https://huggingface.co/rasbt/ai-text-detector-distilbert-lora)
- [DistilBERT with MiCA](https://huggingface.co/rasbt/ai-text-detector-distilbert-mica)
- [GPT-2 with a fixed-position readout](https://huggingface.co/rasbt/ai-text-detector-gpt2-fixed)
- [GPT-2 with a variable-position readout](https://huggingface.co/rasbt/ai-text-detector-gpt2-variable)
- [Qwen3 0.6B with a fixed-position readout](https://huggingface.co/rasbt/ai-text-detector-qwen3-0.6b-fixed)
- [Qwen3 0.6B with a variable-position readout](https://huggingface.co/rasbt/ai-text-detector-qwen3-0.6b-variable)

&nbsp;
## Limitations

Performance may change for text from generators, domains, languages, and editing workflows not represented in the training set. Short or partly AI-assisted text may also be harder to classify. The score should not be treated as definitive evidence that a person did or did not write a text.
