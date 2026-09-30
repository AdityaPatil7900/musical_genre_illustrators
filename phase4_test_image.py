"""
PHASE 4: Image generation, tested standalone - both paths.
Run: python phase4_test_image.py
"""

import os
import torch
from diffusers import DiffusionPipeline
from huggingface_hub import InferenceClient

HF_TOKEN = os.environ.get("HF_TOKEN")

TEST_PROMPT = (
    "A soulful midnight jazz club with a saxophonist, warm amber lighting, "
    "expressive brush strokes, atmospheric cinematic illustration."
)

# ---------------------------------------------------------------------------
# LOCAL: tiny-sd runs on this machine
# ---------------------------------------------------------------------------
def generate_image_local(prompt):
    pipe = DiffusionPipeline.from_pretrained(
        "segmind/tiny-sd", torch_dtype=torch.float32
    )
    pipe.to("cuda" if torch.cuda.is_available() else "cpu")
    image = pipe(prompt, num_inference_steps=15).images[0]
    return image


# ---------------------------------------------------------------------------
# REMOTE: Qwen-Image runs on Hugging Face's servers
# ---------------------------------------------------------------------------
def generate_image_remote(prompt):
    client = InferenceClient(token=HF_TOKEN)
    image = client.text_to_image(prompt, model="Qwen/Qwen-Image")
    return image


if __name__ == "__main__":
    print("Testing LOCAL generation (tiny-sd)...")
    local_image = generate_image_local(TEST_PROMPT)
    local_image.save("test_local_output.png")
    print("Saved: test_local_output.png")

    print("\nTesting REMOTE generation (Qwen-Image)...")
    try:
        remote_image = generate_image_remote(TEST_PROMPT)
        remote_image.save("test_remote_output.png")
        print("Saved: test_remote_output.png")
    except Exception as e:
        print(f"Remote generation failed: {e}")
