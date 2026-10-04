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
  # NOTE: PORT is the port this process binds to ON THE VM. The WPI-side
  # port forwarder maps external http://<host>:8012 -> internal port 7860
  # (Gradio's default), not internal port 8012 -- see Docs/SSH_ACCESS.md and
  # the group's port-mapping email from the course staff. genre-api.service
  # sets PORT=7860 accordingly; this is NOT the externally-visible port.
  APP_MODE=api   PORT=7860 HF_TOKEN=xxx python vm_app.py
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


def get_local_image_pipe():
    """Lazily loads the local tiny-sd pipeline on first actual need.

    In APP_MODE=local this is called once eagerly at startup (same timing as
    before this change). In APP_MODE=api it is NOT loaded at startup -- it is
    only loaded the first time generate_image_remote() actually fails, so a
    healthy API-mode deployment never pays the extra memory/load cost. This
    mirrors the lazy-failover-load pattern already used for the local LLM in
    app.py's adaptive-failover design.
    """
    global local_image_pipe
    if local_image_pipe is None:
        from diffusers import DiffusionPipeline

        print(f"[startup] Loading local image generator ({LOCAL_IMAGE_MODEL_ID})...")
        local_image_pipe = DiffusionPipeline.from_pretrained(
            LOCAL_IMAGE_MODEL_ID, torch_dtype=torch.float32 if torch else None
        )
        device = "cuda" if torch and torch.cuda.is_available() else "cpu"
        local_image_pipe.to(device)
        # Diffusers' built-in attention-slicing trades a small amount of
        # compute time for materially lower peak memory during inference --
        # safe on both local-mode's startup load and API-mode's in-process
        # failover load, so applied unconditionally rather than gated on
        # low-memory mode specifically.
        local_image_pipe.enable_attention_slicing()
        print(f"[startup] tiny-sd on device: {device}")
    return local_image_pipe


if APP_MODE == "local":
    get_local_image_pipe()

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


def generate_image_local(prompt, low_memory=False):
    """Generate an image with the local tiny-sd pipeline.

    low_memory=True is used only by API-mode's in-process failover path
    (see analyze_music below), where tiny-sd is loaded on top of an
    already-running process that also holds the classifier and a live
    Gradio/HF-client stack -- on this VM's 4GB RAM, that combination was
    observed pushing memory to 84-86% with heavy swapping during a normal
    (steps=15, native-resolution) generation, correlated with the process
    exiting during the heaviest compute window (see Test 5 in
    Docs/RESILIENCE_TESTING.md for the full investigation). Plain
    APP_MODE=local is unaffected by this flag (default False, unchanged
    behavior) since that path has no extra classifier/HF-client overhead
    sharing the same process and was already confirmed working as-is.
    """
    import gc

    pipe = get_local_image_pipe()
    if low_memory:
        gc.collect()
        image = pipe(prompt, num_inference_steps=10, height=384, width=384).images[0]
    else:
        image = pipe(prompt, num_inference_steps=15).images[0]
    return image


def generate_image_remote(prompt):
    try:
        return remote_client.text_to_image(prompt, model=REMOTE_IMAGE_MODEL_ID)
    except Exception as e:
        print(f"[ERROR] Remote image generation failed: {e}")
        return None


def analyze_music(audio_file):
    if audio_file is None:
        return "No file uploaded", "N/A", "N/A", None, None, "N/A"

    genre, confidence = classify_audio(audio_file)

    if is_degraded():
        # Adaptive response to high resource usage (Case Study 2, extra credit #6):
        # skip the expensive image-generation step and return genre only.
        note = (
            "⚠️ System is currently operating near capacity — image generation "
            "is temporarily disabled. Genre classification is still available."
        )
        return genre, f"{confidence:.2f}", note, None, None, "N/A (degraded mode)"

    image_source = None
    if APP_MODE == "local":
        visual_prompt = FALLBACK_PROMPTS.get(genre.lower(), f"a colorful abstract illustration representing {genre} music")
        image = generate_image_local(visual_prompt)
        image_source = f"Local {LOCAL_IMAGE_MODEL_ID} (fixed deployment mode)"
    else:
        visual_prompt = create_visual_prompt_remote(genre)
        image = generate_image_remote(visual_prompt)
        image_source = f"Remote {REMOTE_IMAGE_MODEL_ID} (HF Inference)"
        if image is None:
            # Automatic image-generation failover (Case Study 2): the remote
            # Qwen-Image call failed (timeout, rate-limit, auth error, or a
            # billing/quota limit such as HTTP 402) -- fall back to the local
            # tiny-sd pipeline rather than returning no image at all. The
            # local model is lazily loaded on this first failover only, so a
            # healthy API-mode deployment never pays its startup cost.
            print("[FAILOVER] Remote image generation unavailable -- falling back to local tiny-sd (low-memory mode).")
            image = generate_image_local(visual_prompt, low_memory=True)
            image_source = f"Local {LOCAL_IMAGE_MODEL_ID} (automatic failover, low-memory mode — remote image generation unavailable)"

    saved_path = None
    if image is not None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_path = os.path.join(OUTPUT_DIR, f"{genre}_{timestamp}.png")
        image.save(saved_path)

    return genre, f"{confidence:.2f}", visual_prompt, image, saved_path, image_source


mode_label = "API-based (remote LLM + remote Qwen-Image)" if APP_MODE == "api" else "Local (local tiny-sd, no network calls)"

with gr.Blocks(title=f"Music-to-Art Generator [{APP_MODE}]") as demo:
    gr.Markdown(f"# Music-to-Art Generator — {mode_label}")
    extra_note = (
        " If the remote image call fails (timeout, rate-limit, or a billing/quota "
        "limit), it automatically falls back to the local tiny-sd model so a result "
        "is still produced." if APP_MODE == "api" else ""
    )
    gr.Markdown(
        "Upload audio. A local model always detects the genre. "
        f"This deployment ({APP_MODE}) primarily uses the **{mode_label}** image-generation path "
        f"for Case Study 2's deployment requirements.{extra_note}"
    )

    audio_input = gr.Audio(type="filepath", label="Upload Audio")
    analyze_btn = gr.Button("Analyze Music", variant="primary")

    with gr.Row():
        genre_output = gr.Textbox(label="Genre")
        confidence_output = gr.Textbox(label="Confidence")

    prompt_output = gr.Textbox(label="AI Interpretation", lines=3)
    image_output = gr.Image(label="Generated Artwork")
    file_output = gr.File(label="Saved image file")
    image_source_output = gr.Textbox(label="Image generated by")

    analyze_btn.click(
        fn=analyze_music,
        inputs=[audio_input],
        outputs=[genre_output, confidence_output, prompt_output, image_output, file_output, image_source_output],
    )

    gr.Markdown("Health check endpoint: `/` returns 200 when this Gradio server is up.")

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=PORT)
