"""
PHASE 3: Turn a genre into a rich image-generation prompt using a
REMOTE hosted LLM (this is your "remote API LLM" deliverable's core step).
Run: python phase3_test_llm.py
Requires: HF_TOKEN environment variable set to your Hugging Face access token.
"""

import os
from huggingface_hub import InferenceClient

HF_TOKEN = os.environ.get("HF_TOKEN")
TEXT_MODEL_ID = "meta-llama/Llama-3.1-8B-Instruct"

client = InferenceClient(token=HF_TOKEN)


def create_visual_prompt(genre):
    """Sends the genre to a remote LLM, gets back an image-generation prompt."""
    instruction = f"""
    The uploaded music has been classified as {genre}.

    Create a detailed artistic prompt for an image generator.
    Capture the mood, atmosphere, instruments, colors,
    energy, and visual identity associated with {genre}.

    Return only the image generation prompt, nothing else.
    """

    response = client.chat_completion(
        model=TEXT_MODEL_ID,
        messages=[{"role": "user", "content": instruction}],
        max_tokens=100,
    )
    return response.choices[0].message.content.strip()


if __name__ == "__main__":
    test_genre = "jazz"
    prompt = create_visual_prompt(test_genre)
    print(f"Genre: {test_genre}")
    print(f"Generated prompt:\n{prompt}")
