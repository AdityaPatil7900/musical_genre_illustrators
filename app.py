"""
PHASE 5: Full pipeline, connected.
Genre classification is always LOCAL. Image generation can be toggled
between LOCAL (tiny-sd) and REMOTE (LLM prompt-writer + Qwen-Image API).

PHASE 6 (extra credit): The prompt-writing LLM step has adaptive
failover between the REMOTE hosted LLM and a LOCAL LLM — see the
"ADAPTIVE LLM FAILOVER" section below and README.md for details.

Run: python app.py
"""

import os
import time
import torch
from datetime import datetime

import gradio as gr
import spaces
from transformers import pipeline
from huggingface_hub import InferenceClient
from diffusers import DiffusionPipeline

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
GENRE_MODEL_ID = "dima806/music_genres_classification"
LOCAL_IMAGE_MODEL_ID = "segmind/tiny-sd"
TEXT_MODEL_ID = "meta-llama/Llama-3.1-8B-Instruct"
LOCAL_TEXT_MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
REMOTE_IMAGE_MODEL_ID = "Qwen/Qwen-Image"

REMOTE_TIMEOUT_SECONDS = 15
REMOTE_COOLDOWN_SECONDS = 60

HF_TOKEN = os.environ.get("HF_TOKEN")

OUTPUT_DIR = "generated_images"
os.makedirs(OUTPUT_DIR, exist_ok=True)

FALLBACK_PROMPTS = {
    "rock": "a gritty, high-energy illustration with electric guitars, sparks, bold red and black tones",
    "pop": "a bright, glossy, colorful pop-art style illustration full of energy and glitter",
    "jazz": "a moody, smoky illustration of a jazz club with warm amber lighting and saxophones",
    "classical": "an elegant illustration of an orchestra hall with soft golden light and violins",
    "hiphop": "an urban street-art style illustration with bold graffiti colors and city skyline",
    "country": "a warm, rustic illustration of open fields, a guitar, and a sunset",
    "disco": "a vibrant retro illustration with disco balls, neon lights, and 70s colors",
    "metal": "a dark, intense illustration with jagged shapes, fire, and heavy shadows",
    "reggae": "a relaxed, sun-drenched illustration in green-yellow-red tones with palm trees",
    "blues": "a melancholic blue-toned illustration of a lone guitarist under a streetlamp",
}

# ---------------------------------------------------------------------------
# LOAD MODELS ONCE AT STARTUP
# ---------------------------------------------------------------------------
print("Loading local genre classifier...")
classifier = pipeline("audio-classification", model=GENRE_MODEL_ID)

print("Loading local image generator (tiny-sd)...")
local_image_pipe = DiffusionPipeline.from_pretrained(
    LOCAL_IMAGE_MODEL_ID, torch_dtype=torch.float32
)
# NOTE: do NOT call .to("cuda") here. Under ZeroGPU, CUDA can only be
# touched inside a function decorated with @spaces.GPU (see generate_image_local).

def get_client(hf_token: gr.OAuthToken = None):
    token = getattr(hf_token, "token", None)

    if not token:
        print("Login required.")
        return None

    client = InferenceClient(token=token, timeout=REMOTE_TIMEOUT_SECONDS)
    print("API model ready.")
    return client


# ---------------------------------------------------------------------------
# ADAPTIVE LLM FAILOVER (Phase 6, extra credit)
#
# `create_visual_prompt` normally calls the REMOTE hosted LLM
# (TEXT_MODEL_ID via the HF Inference API). If that call fails —
# connection error, timeout, or an HTTP 429 rate-limit — the app
# automatically routes the same request to a small LOCAL LLM
# (LOCAL_TEXT_MODEL_ID, run on-device with transformers) instead of
# surfacing an error to the user. No manual model selection is needed.
#
# A lightweight circuit breaker avoids retrying a known-bad remote API
# on every single request: after a failure, remote calls are skipped
# for REMOTE_COOLDOWN_SECONDS and local is used directly. Once the
# cooldown expires, the next request automatically tries remote again,
# so the app "heals" back to the remote model without any user action.
# ---------------------------------------------------------------------------
_local_text_pipe = None


def _get_local_text_pipe():
    """Lazy-load the local text-generation model on first use, so a
    working remote API never pays the cost of loading it."""
    global _local_text_pipe
    if _local_text_pipe is None:
        print(f"Loading local LLM ({LOCAL_TEXT_MODEL_ID}) for failover...")
        _local_text_pipe = pipeline(
            "text-generation", model=LOCAL_TEXT_MODEL_ID, torch_dtype=torch.float32
        )
    return _local_text_pipe


@spaces.GPU
def generate_prompt_local(instruction):
    """Run the same prompt-writing instruction through the local LLM."""
    pipe = _get_local_text_pipe()
    pipe.model.to("cuda" if torch.cuda.is_available() else "cpu")
    output = pipe(
        [{"role": "user", "content": instruction}],
        max_new_tokens=100,
        do_sample=True,
        temperature=0.8,
    )
    return output[0]["generated_text"][-1]["content"].strip()


class _RemoteLLMCircuitBreaker:
    """Tracks whether the remote LLM is currently considered down."""

    def __init__(self):
        self.unavailable_until = 0.0
        self.last_reason = None

    def is_down(self):
        return time.time() < self.unavailable_until

    def mark_down(self, reason):
        self.unavailable_until = time.time() + REMOTE_COOLDOWN_SECONDS
        self.last_reason = reason
        print(
            f"[FAILOVER] Remote LLM marked unavailable for "
            f"{REMOTE_COOLDOWN_SECONDS}s ({reason}); routing to local LLM."
        )


_remote_breaker = _RemoteLLMCircuitBreaker()


def _classify_remote_failure(exc):
    """Best-effort classification of *why* the remote call failed, for
    logging/UI purposes. Detects timeouts and HTTP 429 rate limits as
    distinct cases; anything else is reported as 'unavailable'."""
    msg = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timed out" in msg or "timeout" in msg:
        return "timeout"
    if "429" in msg or "rate limit" in msg or "too many requests" in msg:
        return "rate limited"
    return "unavailable"

# ---------------------------------------------------------------------------
# STEP 1: Genre classification (LOCAL)
# ---------------------------------------------------------------------------
@spaces.GPU
def classify_audio(audio_file):
    if audio_file is None:
        return "unknown", 0.0
    result = classifier(audio_file)
    genre = result[0]["label"]
    confidence = result[0]["score"]
    return genre, confidence


# ---------------------------------------------------------------------------
# STEP 2: Genre -> creative prompt (REMOTE LLM)
# ---------------------------------------------------------------------------
def create_visual_prompt(genre, hf_token, simulate_remote_failure=False):
    """Turns a genre into an image-generation prompt, preferring the
    remote LLM and automatically failing over to the local LLM (and, as
    a last resort, a static template) when the remote API is down.

    Returns (prompt_text, source_label) where source_label states which
    model actually produced the prompt, e.g. "Remote LLM (...)" or
    "Local LLM (... ) — automatic failover".

    `simulate_remote_failure` lets the UI force a remote failure on
    demand, to demonstrate the failover behavior without needing to
    wait for a real outage or rate limit.
    """
    instruction = f"""
    The uploaded music has been classified as {genre}.

    Create a detailed artistic prompt for an image generator.
    Capture the mood, atmosphere, instruments, colors,
    energy, and visual identity associated with {genre}.

    Return only the image generation prompt, nothing else.
    """

    if not _remote_breaker.is_down():
        try:
            if simulate_remote_failure:
                raise RuntimeError("Simulated remote outage (demo mode)")

            client = get_client(hf_token)
            if client is None:
                raise RuntimeError("Please log in with Hugging Face.")
            response = client.chat_completion(
                model=TEXT_MODEL_ID,
                messages=[{"role": "user", "content": instruction}],
                max_tokens=100,
            )
            return response.choices[0].message.content.strip(), f"Remote LLM ({TEXT_MODEL_ID})"
        except Exception as e:
            _remote_breaker.mark_down(_classify_remote_failure(e))
            print(f"[FAILOVER] Remote LLM call failed: {e}")
    else:
        print(
            f"[FAILOVER] Remote LLM still in cooldown "
            f"({_remote_breaker.last_reason}); using local LLM."
        )

    try:
        prompt = generate_prompt_local(instruction)
        return prompt, f"Local LLM ({LOCAL_TEXT_MODEL_ID}) — automatic failover"
    except Exception as e:
        print(f"[WARN] Local LLM also failed, using static fallback prompt: {e}")
        fallback = FALLBACK_PROMPTS.get(
            genre.lower(), f"a colorful abstract illustration representing {genre} music"
        )
        return fallback, "Static fallback template (remote and local LLM both unavailable)"


# ---------------------------------------------------------------------------
# STEP 3: Prompt -> image, LOCAL or REMOTE
# ---------------------------------------------------------------------------
@spaces.GPU
def generate_image_local(prompt):
    local_image_pipe.to("cuda" if torch.cuda.is_available() else "cpu")
    image = local_image_pipe(prompt, num_inference_steps=15).images[0]
    return image


def generate_image_remote(prompt, hf_token):
    try:
        client = get_client(hf_token)

        if client is None:
            raise Exception("Please log in with Hugging Face.")
        return client.text_to_image(prompt, model=REMOTE_IMAGE_MODEL_ID)
    except Exception as e:
        print(f"[ERROR] Remote image generation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# FULL PIPELINE
# ---------------------------------------------------------------------------
def analyze_music(
    audio_file, use_local_image_gen, simulate_remote_failure, hf_token: gr.OAuthToken = None
):
    if audio_file is None:
        return "No file uploaded", "N/A", "N/A", "N/A", None, None

    # STEP 1
    genre, confidence = classify_audio(audio_file)

    # STEP 2: prompt-writing LLM, with automatic remote -> local failover
    visual_prompt, prompt_source = create_visual_prompt(
        genre, hf_token, simulate_remote_failure=simulate_remote_failure
    )

    # STEP 3
    if use_local_image_gen:
        image = generate_image_local(visual_prompt)
    else:
        image = generate_image_remote(visual_prompt, hf_token)

    saved_path = None
    if image is not None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_path = os.path.join(OUTPUT_DIR, f"{genre}_{timestamp}.png")
        image.save(saved_path)

    return genre, f"{confidence:.2f}", prompt_source, visual_prompt, image, saved_path


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
with gr.Blocks(title="Music-to-Art Generator") as demo:
    gr.Markdown("# 🎵 Music-to-Art Generator")
    gr.Markdown(
        "Upload audio. A local model detects the genre. Toggle below to "
        "generate the artwork **locally (tiny-sd)** or **remotely (LLM + Qwen-Image API)**."
    )

    audio_input = gr.Audio(type="filepath", label="Upload Audio")
    gr.LoginButton()
    use_local_toggle = gr.Checkbox(label="Use Local Model for image generation", value=False)
    simulate_failure_toggle = gr.Checkbox(
        label="Simulate remote LLM outage (demo: forces failover to the local LLM)",
        value=False,
    )
    analyze_btn = gr.Button("Analyze Music", variant="primary")

    with gr.Row():
        genre_output = gr.Textbox(label="Genre")
        confidence_output = gr.Textbox(label="Confidence")

    prompt_source_output = gr.Textbox(label="Prompt written by")
    prompt_output = gr.Textbox(label="AI Interpretation", lines=3)
    image_output = gr.Image(label="Generated Artwork")
    file_output = gr.File(label="Saved image file")

    analyze_btn.click(
        fn=analyze_music,
        inputs=[audio_input, use_local_toggle, simulate_failure_toggle],
        outputs=[
            genre_output,
            confidence_output,
            prompt_source_output,
            prompt_output,
            image_output,
            file_output,
        ],
    )

if __name__ == "__main__":
    demo.launch()
