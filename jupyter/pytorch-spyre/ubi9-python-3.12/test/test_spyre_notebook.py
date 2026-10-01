import os
os.environ["HF_HUB_OFFLINE"]="0"
from torch import LongTensor
import torch
from transformers import AutoTokenizer, RobertaForQuestionAnswering

from torch_sendnn import torch_sendnn  # noqa: F401

# --- Load model and tokenizer ---
tokenizer = AutoTokenizer.from_pretrained("deepset/roberta-base-squad2")
model = RobertaForQuestionAnswering.from_pretrained("deepset/roberta-base-squad2")

# Set to eval mode before compile — disables dropout, ensures deterministic output
model.eval()

# Compile once, outside the inference block.
# Use "sendnn_debug" for Spyre or "inductor" for CPU/CUDA.
model = torch.compile(model, backend="sendnn")

# --- Tokenize ---
question, text = "Who was Miss Piggy?", "Miss Piggy was a muppet"

inputs = tokenizer(
    question,
    text,
    return_tensors="pt",
    max_length=384,
    padding="max_length",
    truncation=True,          # required when max_length is set
)

# --- Inference ---
with torch.no_grad():
    outputs = model(**inputs)

# --- Decode answer ---
answer_start_index = outputs.start_logits.argmax().item()
answer_end_index = outputs.end_logits.argmax().item()

# Guard against inverted span (end predicted before start)
if answer_end_index < answer_start_index:
    answer_end_index = answer_start_index

predict_answer_tokens = inputs.input_ids[0, answer_start_index : answer_end_index + 1]
answer = tokenizer.decode(predict_answer_tokens, skip_special_tokens=True)

print("-" * 50)
print(f'Answer: "{answer}"')
print("=" * 50)
