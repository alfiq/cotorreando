"""Writes short reading panels that contain the user's difficult words, with Qwen3.

Runs inside the optional training environment. Reads {"words": [...], "language": "es"}
from stdin and prints one ``PANEL {"word": ..., "text": ...}`` line for each panel that
passed both checks: the word is really there, and Qwen agrees that the text reads well.
"""

import json
import os
import re
import sys

MODEL = "Qwen/Qwen3-0.6B"     # the only model allowed here, pinned to one exact revision
REVISION = "c1899de289a04d12100db370d81485cdf75e47ca"
ATTEMPTS = 4
MIN_WORDS, MAX_WORDS = 12, 30
ASK = {
    "es": "Escribe una sola oración natural de unas 20 palabras, en español, que incluya exactamente "
          "la palabra «{word}». Responde únicamente con la oración.",
    "en": "Write one natural sentence of about 20 words, in English, that includes exactly the word "
          "\"{word}\". Answer only with the sentence.",
}
CHECK = {
    "es": "Oración: «{text}»\n¿Está bien escrita y usa la palabra «{word}» con sentido? Responde solo SI o NO.",
    "en": "Sentence: \"{text}\"\nIs it well written and does it use the word \"{word}\" sensibly? "
          "Answer only YES or NO.",
}


def has_word(text: str, word: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.IGNORECASE) is not None


def well_sized(text: str) -> bool:
    return MIN_WORDS <= len(text.split()) <= MAX_WORDS


def main() -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    job = json.loads(sys.stdin.readline())
    language = job["language"] if job["language"] in ASK else "es"
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
    quantization = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                      bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(MODEL, revision=REVISION, device_map="auto",
                                                 quantization_config=quantization)

    def complete(prompt: str, sample: bool) -> str:
        chat = tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=False,
                                             add_generation_prompt=True, enable_thinking=False)
        inputs = tokenizer(chat, return_tensors="pt").to(model.device)
        options = {"do_sample": True, "temperature": 0.8, "top_p": 0.9} if sample else {"do_sample": False}
        output = model.generate(**inputs, max_new_tokens=80, **options)
        text = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip().strip("\"«»“”")

    for word in job["words"]:
        for _ in range(ATTEMPTS):
            text = " ".join(complete(ASK[language].format(word=word), True).split())
            if not has_word(text, word) or not well_sized(text):
                continue
            verdict = complete(CHECK[language].format(text=text, word=word), False).upper()
            if verdict.startswith(("SI", "SÍ", "YES")):
                print("PANEL " + json.dumps({"word": word, "text": text}, ensure_ascii=False), flush=True)
                break


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)
