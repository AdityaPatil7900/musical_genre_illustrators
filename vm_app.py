"""
VM-deployable variant of app.py for Case Study 2.

Differences from app.py (which targets Hugging Face Spaces):
  - No dependency on the `spaces` package / ZeroGPU decorators (no-op'd if absent).
  - No HF OAuth login button (VM has no HF Spaces OAuth app registered) -- the
    HF token is read directly from the HF_TOKEN environment variable instead.
  - APP_MODE env var selects which product this process serves:
      APP_MODE=api    -> API-based product (remote LLM prompt-writer + remote
                          Qwen-Image text-to-image API). Requires HF_TOKEN.
      APP_MODE=local  -> Locally-executed product (local genre classifier +
                          local tiny-sd image generation, no network calls,
                          no HF_TOKEN required).
  - Binds to 0.0.0.0 and a configurable PORT so it can be reached externally
    and managed by systemd.

Run:
  APP_MODE=api   PORT=8012 HF_TOKEN=xxx python vm_app.py
  APP_MODE=local PORT=8013            python vm_app.py
"""

import os
from datetime import datetime

import gradio as gr
from transformers import pipeline

try:
    import torch
except ImportError:
    torch = None

APP_MODE = os.environ.get("APP_MODE", "local").lower()
PORT = int(os.environ.get("PORT", "7860"))
HF_TOKEN = os.environ.get("HF_TOKEN")

GENRE_MODEL_ID = "dima806/music_genres_classification"
LOCAL_IMAGE_MODEL_ID = "segmind/tiny-sd"
TEXT_MODEL_ID = "meta-llama/Llama-3.1-8B-Instruct"
REMOTE_IMAGE_MODEL_ID = "Qwen/Qwen-Image"

OUTPUT_DIR = "generated_images"
os.makedirs(OUTPUT_DIR, exist_ok=True)

WATCHDOG_STATE_DIR = os.environ.get("WATCHDOG_STATE_DIR", os.path.join(os.getcwd(), ".watchdog"))
DEGRADED_FLAG = os.path.join(WATCHDOG_STATE_DIR, "degraded_mode.flag")


def is_degraded():
    return os.path.exists(DEGRADED_FLAG)

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

print(f"[startup] APP_MODE={APP_MODE} PORT={PORT}")
print("[startup] Loading local genre classifier...")
classifier = pipeline("audio-classification", model=GENRE_MODEL_ID)

local_image_pipe = None
if APP_MODE == "local":
    from diffusers import DiffusionPipeline

    print("[startup] Loading local image generator (tiny-sd)...")
    local_image_pipe = DiffusionPipeline.from_pretrained(
        LOCAL_IMAGE_MODEL_ID, torch_dtype=torch.float32 if torch else None
    )
    device = "cuda" if torch and torch.cuda.is_available() else "cpu"
    local_image_pipe.to(device)
    print(f"[startup] tiny-sd on device: {device}")

remote_client = None
if APP_MODE == "api":
    from huggingface_hub import InferenceClient

    if not HF_TOKEN:
        raise RuntimeError("APP_MODE=api requires the HF_TOKEN environment variable to be set.")
    remote_client = InferenceClient(token=HF_TOKEN)
    print("[startup] Remote HF InferenceClient ready.")


def classify_audio(audio_file):
    if audio_file is None:
        return "unknown", 0.0
    result = classifier(audio_file)
    return result[0]["label"], result[0]["score"]


def create_visual_prompt_remote(genre):
    instruction = f"""
    The uploaded music has been classified as {genre}.

    Create a detailed artistic prompt for an image generator.
    Capture the mood, atmosphere, instruments, colors,
    energy, and visual identity associated with {genre}.

    Return only the image generation prompt, nothing else.
    """
    try:
        response = remote_client.chat_completion(
            model=TEXT_MODEL_ID,
            messages=[{"role": "user", "content": instruction}],
            max_tokens=100,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[WARN] Remote LLM failed, using fallback prompt: {e}")
        return FALLBACK_PROMPTS.get(genre.lower(), f"a colorful abstract illustration representing {genre} music")


def generate_image_local(prompt):
    image = local_image_pipe(prompt, num_inference_steps=15).images[0]
    return image


def generate_image_remote(prompt):
    try:
        return remote_client.text_to_image(prompt, model=REMOTE_IMAGE_MODEL_ID)
    except Exception as e:
        print(f"[ERROR] Remote image generation failed: {e}")
        return None


def analyze_music(audio_file):
    if audio_file is None:
        return "No file uploaded", "N/A", "N/A", None, None

    genre, confidence = classify_audio(audio_file)

    if is_degraded():
        # Adaptive response to high resource usage (Case Study 2, extra credit #6):
        # skip the expensive image-generation step and return genre only.
        note = (
            "⚠️ System is currently operating near capacity — image generation "
            "is temporarily disabled. Genre classification is still available."
        )
        return genre, f"{confidence:.2f}", note, None, None

    if APP_MODE == "local":
        visual_prompt = FALLBACK_PROMPTS.get(genre.lower(), f"a colorful abstract illustration representing {genre} music")
        image = generate_image_local(visual_prompt)
    else:
        visual_prompt = create_visual_prompt_remote(genre)
        image = generate_image_remote(visual_prompt)

    saved_path = None
    if image is not None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_path = os.path.join(OUTPUT_DIR, f"{genre}_{timestamp}.png")
        image.save(saved_path)

    return genre, f"{confidence:.2f}", visual_prompt, image, saved_path


mode_label = "API-based (remote LLM + remote Qwen-Image)" if APP_MODE == "api" else "Local (local tiny-sd, no network calls)"

with gr.Blocks(title=f"Music-to-Art Generator [{APP_MODE}]") as demo:
    gr.Markdown(f"# Music-to-Art Generator — {mode_label}")
    gr.Markdown(
        "Upload audio. A local model always detects the genre. "
        f"This deployment ({APP_MODE}) is fixed to the **{mode_label}** image-generation path "
        "for Case Study 2's deployment requirements."
    )

    audio_input = gr.Audio(type="filepath", label="Upload Audio")
    analyze_btn = gr.Button("Analyze Music", variant="primary")

    with gr.Row():
        genre_output = gr.Textbox(label="Genre")
        confidence_output = gr.Textbox(label="Confidence")

    prompt_output = gr.Textbox(label="AI Interpretation", lines=3)
    image_output = gr.Image(label="Generated Artwork")
    file_output = gr.File(label="Saved image file")

    analyze_btn.click(
        fn=analyze_music,
        inputs=[audio_input],
        outputs=[genre_output, confidence_output, prompt_output, image_output, file_output],
    )

    gr.Markdown("Health check endpoint: `/` returns 200 when this Gradio server is up.")

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=PORT)
