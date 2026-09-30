---
title: Musical Genre Illustrator
emoji: 💬
colorFrom: yellow
colorTo: purple
sdk: gradio
sdk_version: 6.5.1
app_file: app.py
pinned: false
hf_oauth: true
hf_oauth_scopes:
- inference-api
short_description: ' '
---

<div align="center">

# 🎵 Musical Genre Illustrator

### Translating Sound into Art through a Multi-Model AI Pipeline

*Machine Learning Development and Operations*

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Gradio](https://img.shields.io/badge/Gradio-6.5.1-FF7C00?style=flat-square&logo=huggingface&logoColor=white)](https://gradio.app)
[![HF Spaces](https://img.shields.io/badge/🤗%20HF%20Spaces-Deployed-FFD21E?style=flat-square)](YOUR_HF_SPACES_URL_HERE)
[![Transformers](https://img.shields.io/badge/🤗%20Transformers-4.40%2B-yellow?style=flat-square)](https://huggingface.co/docs/transformers)
[![Diffusers](https://img.shields.io/badge/Diffusers-0.27%2B-blue?style=flat-square)](https://huggingface.co/docs/diffusers)
[![Pytest](https://img.shields.io/badge/Tested%20with-pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white)](https://pytest.org)
[![ZeroGPU](https://img.shields.io/badge/ZeroGPU-Compatible-brightgreen?style=flat-square)](https://huggingface.co/docs/hub/spaces-zerogpu)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

[🔴 Live Demo](#-live-demo) &nbsp;•&nbsp; [📐 Architecture](#-system-architecture) &nbsp;•&nbsp; [⚡ Quick Start](#-setup--installation) &nbsp;•&nbsp; [🧪 Tests](#-testing) &nbsp;•&nbsp; [🧠 Failover](#-adaptive-llm-failover--extra-credit)

</div>

---

## 📋 Table of Contents

- [Abstract](#-abstract)
- [Live Demo](#-live-demo)
- [System Architecture](#-system-architecture)
- [Key Features](#-key-features)
- [Technology Stack](#-technology-stack)
- [Pipeline Walkthrough](#-pipeline-walkthrough)
- [Adaptive LLM Failover — Extra Credit](#-adaptive-llm-failover--extra-credit)
- [Repository Structure](#-repository-structure)
- [Phased Development](#-phased-development)
- [Setup & Installation](#-setup--installation)
- [Usage](#-usage)
- [Testing](#-testing)
- [Design Decisions & Trade-offs](#-design-decisions--trade-offs)
- [Limitations & Future Work](#-limitations--future-work)
- [References](#-references)
- [Acknowledgments](#-acknowledgments)

---

## 🧪 Abstract

**Musical Genre Illustrator** is an end-to-end, multi-model AI pipeline that transforms raw audio into genre-specific generative artwork. The system chains three specialized models in sequence: a **local audio classification model** detects the music genre from an uploaded audio file, a **large language model (LLM)** translates the detected genre into a richly descriptive image-generation prompt, and a **text-to-image diffusion model** renders the final visual artwork.

A core engineering contribution of this project is an **adaptive LLM failover system** built on a lightweight circuit-breaker pattern. The prompt-writing step preferentially calls a remote-hosted `meta-llama/Llama-3.1-8B-Instruct` model, but automatically degrades to a local `Qwen/Qwen2.5-0.5B-Instruct` model on any failure (timeout, rate-limit, or network error), and further falls back to curated static per-genre templates if both LLMs are unavailable. This three-tier degradation hierarchy ensures the pipeline never dead-ends, even under adverse API conditions.

The application is deployed on **Hugging Face Spaces** with **ZeroGPU**, exposes a **Gradio 6.5.1** web interface supporting HF OAuth login, local/remote image-generation toggling, and a simulation mode for demonstrating failover behavior on demand.

---

## 🚀 Live Demo

> ### 🔗 [Launch the App on Hugging Face Spaces → YOUR_HF_SPACES_URL_HERE](YOUR_HF_SPACES_URL_HERE)

| Control | Description |
|---|---|
| 📂 **Upload Audio** | Upload any `.wav`, `.mp3`, or `.flac` file |
| 🔐 **HF Login** | Log in with your HF account for remote LLM + image generation |
| 🔘 **Use Local Model** | Toggle between `tiny-sd` (local) and `Qwen-Image` (remote HF API) |
| ⚠️ **Simulate Outage** | Force-trip the circuit breaker to demonstrate automatic LLM failover |
| 🎨 **Analyze Music** | Run the full 3-step pipeline and generate artwork |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         AUDIO INPUT                         │
│              (.wav / .mp3 / .flac upload)                   │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│            STEP 1 — GENRE CLASSIFIER  [LOCAL]               │
│  Model  :  dima806/music_genres_classification               │
│  Library:  transformers.pipeline("audio-classification")     │
│  Runtime:  @spaces.GPU  ·  loaded at startup                │
│  Output :  genre: str  ·  confidence: float [0, 1]          │
└──────────────────────────┬──────────────────────────────────┘
                           │  (genre, confidence)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│            STEP 2 — PROMPT WRITER                           │
│            create_visual_prompt(genre, hf_token)            │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  TIER 1 ─ Remote LLM (preferred)                    │   │
│   │  meta-llama/Llama-3.1-8B-Instruct                   │   │
│   │  InferenceClient · 15s timeout                       │   │
│   └──────────────────────┬──────────────────────────────┘   │
│                          │ on failure (timeout / 429 / err) │
│                          ▼                                  │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  TIER 2 ─ Local LLM (automatic failover)            │   │
│   │  Qwen/Qwen2.5-0.5B-Instruct                         │   │
│   │  transformers · lazy-loaded · @spaces.GPU            │   │
│   └──────────────────────┬──────────────────────────────┘   │
│                          │ on failure                       │
│                          ▼                                  │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  TIER 3 ─ Static fallback (last resort)             │   │
│   │  FALLBACK_PROMPTS[genre] · 10 hardcoded strings     │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   _RemoteLLMCircuitBreaker · 60s cooldown · auto-heals      │
└──────────────────────────┬──────────────────────────────────┘
                           │  (visual_prompt: str, source: str)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│            STEP 3 — IMAGE GENERATOR                         │
│                                                             │
│   LOCAL  :  segmind/tiny-sd  ·  DiffusionPipeline          │
│             15 inference steps  ·  @spaces.GPU              │
│                                                             │
│   REMOTE :  Qwen/Qwen-Image                                 │
│             InferenceClient.text_to_image()                 │
│             Requires HF OAuth token                         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│               GENERATED ARTWORK (PNG)                       │
│       Saved to  generated_images/{genre}_{timestamp}.png    │
└─────────────────────────────────────────────────────────────┘
```

### Component Summary

| Component | Model / Library | Mode | Notes |
|---|---|---|---|
| Genre Classifier | `dima806/music_genres_classification` | Local | Loaded at startup; 10 genre labels |
| LLM Prompt Writer (primary) | `meta-llama/Llama-3.1-8B-Instruct` | Remote | 15s timeout; circuit breaker guard |
| LLM Prompt Writer (failover) | `Qwen/Qwen2.5-0.5B-Instruct` | Local | Lazy-loaded on first failover event |
| Image Generator (local) | `segmind/tiny-sd` | Local | 15 diffusion steps; ZeroGPU |
| Image Generator (remote) | `Qwen/Qwen-Image` | Remote | Requires authenticated HF session |
| UI / Deployment | `Gradio 6.5.1` on HF Spaces | Cloud | ZeroGPU · HF OAuth · `gr.LoginButton()` |

---

## ✨ Key Features

- **🎵 Audio-to-art pipeline** — end-to-end transformation from raw audio to genre-themed artwork through three chained AI models
- **🔊 10-genre classification** — rock, pop, jazz, classical, hip-hop, country, disco, metal, reggae, blues
- **🧠 Adaptive LLM failover** — three-tier prompt-writing degradation (remote → local → static) with no user-visible error
- **⚡ Circuit breaker pattern** — `_RemoteLLMCircuitBreaker` enforces a 60-second cooldown and auto-heals after outage
- **🔀 Local / remote image toggle** — `segmind/tiny-sd` for offline use; `Qwen-Image` API for higher quality
- **🛡️ ZeroGPU compatible** — all GPU operations wrapped with `@spaces.GPU` for Hugging Face Spaces
- **🔐 HF OAuth integration** — secure token propagation via `gr.OAuthToken` and `gr.LoginButton()`
- **💾 Image persistence** — artwork saved to `generated_images/{genre}_{timestamp}.png`
- **🔬 Failover simulation mode** — UI checkbox triggers the circuit breaker on demand for live demonstration
- **✅ Isolated test suite** — six pytest unit tests covering null input, failover routing, cooldown window, and double-failure fallback

---

## 🛠️ Technology Stack

### Machine Learning

| Library | Version | Role |
|---|---|---|
| `transformers` | ≥ 4.40.0 | Audio classification pipeline; local LLM text-generation pipeline |
| `diffusers` | ≥ 0.27.0 | Local image generation via `DiffusionPipeline` |
| `torch` | latest | Deep learning backend; `torch.float32` dtype for CPU/GPU compatibility |
| `torchaudio` | latest | Audio preprocessing |
| `accelerate` | latest | Model loading and inference acceleration |

### Deployment & Infrastructure

| Library | Version | Role |
|---|---|---|
| `gradio` | ≥ 4.0.0 (SDK 6.5.1) | Web UI, HF OAuth, `@spaces.GPU` ZeroGPU decorator |
| `huggingface_hub` | ≥ 0.24.0 | `InferenceClient` for remote LLM + image generation APIs |
| `spaces` | latest | `@spaces.GPU` for ZeroGPU GPU allocation on HF Spaces |
| `soundfile` | latest | Audio file I/O |
| `pillow` | latest | Image saving and format handling |

### Testing

| Tool | Role |
|---|---|
| `pytest` | Test runner and assertion framework |
| `monkeypatch` | Stubs out local LLM downloads — tests run without network calls |
| `autouse fixture` | Resets global circuit breaker state between every test |

---

## 🔄 Pipeline Walkthrough

### Step 1 — Genre Classification

```python
# Model loaded once at module startup
classifier = pipeline("audio-classification", model="dima806/music_genres_classification")

@spaces.GPU
def classify_audio(audio_file):
    if audio_file is None:
        return "unknown", 0.0
    result = classifier(audio_file)
    return result[0]["label"], result[0]["score"]
```

The genre classifier runs **entirely on-device** on every call — there is no remote dependency for this step. The model is loaded once at module import and stays resident in memory. `@spaces.GPU` ensures the CUDA device is allocated by the ZeroGPU scheduler only for the duration of the active request.

**Supported genres:** `rock` · `pop` · `jazz` · `classical` · `hiphop` · `country` · `disco` · `metal` · `reggae` · `blues`

---

### Step 2 — Prompt Writing

```python
def create_visual_prompt(genre, hf_token, simulate_remote_failure=False):
    instruction = f"""
    The uploaded music has been classified as {genre}.
    Create a detailed artistic prompt for an image generator.
    Capture the mood, atmosphere, instruments, colors,
    energy, and visual identity associated with {genre}.
    Return only the image generation prompt, nothing else.
    """
    # Tries: Remote LLM → Local LLM → Static template
    # Returns: (prompt_text: str, source_label: str)
```

`create_visual_prompt()` returns a `(prompt_text, source_label)` tuple, where `source_label` states which model actually handled the request — e.g., `Remote LLM (meta-llama/Llama-3.1-8B-Instruct)` or `Local LLM (Qwen/Qwen2.5-0.5B-Instruct) — automatic failover`. This label is surfaced directly in the Gradio UI under **"Prompt written by"**.

---

### Step 3 — Image Generation

```python
# LOCAL path — segmind/tiny-sd
@spaces.GPU
def generate_image_local(prompt):
    local_image_pipe.to("cuda" if torch.cuda.is_available() else "cpu")
    return local_image_pipe(prompt, num_inference_steps=15).images[0]

# REMOTE path — Qwen/Qwen-Image via HF Inference API
def generate_image_remote(prompt, hf_token):
    client = InferenceClient(token=hf_token.token, timeout=REMOTE_TIMEOUT_SECONDS)
    return client.text_to_image(prompt, model=REMOTE_IMAGE_MODEL_ID)
```

A Gradio `Checkbox` controls which path is taken. **Local inference** with `segmind/tiny-sd` runs 15 diffusion steps and requires no login. **Remote inference** calls the HF Inference API and requires an active HF OAuth session.

> **ZeroGPU note:** `local_image_pipe` is loaded at startup with `torch_dtype=torch.float32` **without** `.to("cuda")`. The device transfer only occurs inside the `@spaces.GPU`-decorated function, which is a requirement of the HF Spaces ZeroGPU architecture.

---

## 🧠 Adaptive LLM Failover — Extra Credit

This section describes the primary reliability engineering contribution of the project.

### Overview

The prompt-writing step implements a **circuit breaker pattern** to provide automatic, user-transparent LLM failover across three tiers, with no manual intervention required at any point.

### Failure Classification

```python
REMOTE_TIMEOUT_SECONDS = 15   # InferenceClient request timeout
REMOTE_COOLDOWN_SECONDS = 60  # Circuit breaker cooldown window

def _classify_remote_failure(exc) -> str:
    """Classifies why a remote LLM call failed for logging and UI display."""
    msg = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timed out" in msg or "timeout" in msg:
        return "timeout"
    if "429" in msg or "rate limit" in msg or "too many requests" in msg:
        return "rate limited"
    return "unavailable"
```

Any exception from the remote API — connection error, 15-second timeout, HTTP 429 rate-limit, or missing authentication — is caught and routed into the failover chain.

### Circuit Breaker Implementation

```python
class _RemoteLLMCircuitBreaker:
    """Lightweight circuit breaker for the remote LLM endpoint."""
    def __init__(self):
        self.unavailable_until = 0.0   # POSIX epoch timestamp
        self.last_reason = None

    def is_down(self) -> bool:
        return time.time() < self.unavailable_until

    def mark_down(self, reason: str):
        self.unavailable_until = time.time() + REMOTE_COOLDOWN_SECONDS
        self.last_reason = reason
        print(
            f"[FAILOVER] Remote LLM marked unavailable for "
            f"{REMOTE_COOLDOWN_SECONDS}s ({reason}); routing to local LLM."
        )

_remote_breaker = _RemoteLLMCircuitBreaker()
```

| Breaker State | Condition | Behavior |
|---|---|---|
| **Closed** *(healthy)* | `time.time() >= unavailable_until` | Attempts remote LLM call first |
| **Open** *(tripped)* | `time.time() < unavailable_until` | Skips remote; routes directly to local LLM |
| **Half-Open** *(auto-heal)* | Cooldown window elapsed | Next request automatically retries remote |

### Three-Tier Failover Routing

```
create_visual_prompt()
│
├─ [breaker CLOSED] ──────→ Remote LLM  (Llama-3.1-8B via HF API)
│                                │
│                         success → return (prompt, "Remote LLM (...)")
│                                │
│                         failure → _remote_breaker.mark_down(reason)
│                                │
│                                ▼
└─ [breaker OPEN or just failed] ──→ Local LLM  (Qwen2.5-0.5B, lazy-loaded)
                                            │
                                     success → return (prompt, "Local LLM (...) — automatic failover")
                                            │
                                     failure
                                            │
                                            ▼
                                     FALLBACK_PROMPTS[genre]
                                     return (prompt, "Static fallback template (...)")
```

### Lazy Loading of the Local Model

```python
_local_text_pipe = None

def _get_local_text_pipe():
    """Loads Qwen2.5-0.5B only on the first actual failover — never at startup."""
    global _local_text_pipe
    if _local_text_pipe is None:
        print(f"Loading local LLM ({LOCAL_TEXT_MODEL_ID}) for failover...")
        _local_text_pipe = pipeline(
            "text-generation", model=LOCAL_TEXT_MODEL_ID, torch_dtype=torch.float32
        )
    return _local_text_pipe
```

If the remote LLM is healthy throughout a session, the local model is **never downloaded or loaded** — saving startup latency and several hundred MB of RAM.

### Static Fallback Prompts

```python
FALLBACK_PROMPTS = {
    "rock":      "a gritty, high-energy illustration with electric guitars, sparks, bold red and black tones",
    "pop":       "a bright, glossy, colorful pop-art style illustration full of energy and glitter",
    "jazz":      "a moody, smoky illustration of a jazz club with warm amber lighting and saxophones",
    "classical": "an elegant illustration of an orchestra hall with soft golden light and violins",
    "hiphop":    "an urban street-art style illustration with bold graffiti colors and city skyline",
    "country":   "a warm, rustic illustration of open fields, a guitar, and a sunset",
    "disco":     "a vibrant retro illustration with disco balls, neon lights, and 70s colors",
    "metal":     "a dark, intense illustration with jagged shapes, fire, and heavy shadows",
    "reggae":    "a relaxed, sun-drenched illustration in green-yellow-red tones with palm trees",
    "blues":     "a melancholic blue-toned illustration of a lone guitarist under a streetlamp",
}
```

### Demo / Simulation Mode

A **"Simulate remote LLM outage"** checkbox in the Gradio UI exposes `simulate_remote_failure=True`, which raises a `RuntimeError` before the remote call is attempted. This allows evaluators to observe the full circuit-breaker trip and failover chain — including `[FAILOVER]` console output and the updated `source_label` — without requiring a real API outage or rate limit.

**To observe the failover live:**
1. Check **"Simulate remote LLM outage"** in the UI
2. Click **"Analyze Music"**
3. The `Prompt written by` field will show `Local LLM (Qwen/Qwen2.5-0.5B-Instruct) — automatic failover`
4. The terminal will print:
   ```
   [FAILOVER] Remote LLM marked unavailable for 60s (unavailable); routing to local LLM.
   ```
5. Subsequent requests within 60 seconds will skip remote entirely:
   ```
   [FAILOVER] Remote LLM still in cooldown (unavailable); using local LLM.
   ```

### Failover Trade-off Analysis

| Aspect | Advantage | Disadvantage |
|---|---|---|
| **Availability** | App remains fully functional during remote outages and rate limits | — |
| **Prompt quality** | Remote 8B model produces richer, more creative prompts | Local 0.5B yields noticeably lower-quality prompts during failover |
| **Latency** | 60s cooldown avoids repeated timeout waits on every request | First-failover request incurs one-time lazy model load delay |
| **Resource usage** | Local model is lazy-loaded — no cost if remote is healthy | Model load adds memory pressure and initial latency when triggered |
| **Transparency** | `source_label` field makes the active model explicitly visible | Silent failover may mask systemic issues (e.g., an expired HF token) |
| **Cooldown precision** | Simple and predictable; no complex state to manage | Fixed 60s window — transient blips cause unnecessary local routing for 60s |

---

## 📁 Repository Structure

```
musical_genre_illustrator/
│
├── app.py                       # ★ Main application — full Phase 5 + 6 pipeline (326 lines)
│
├── phase1_ui.py                 # Phase 1: Gradio UI skeleton, hardcoded fake outputs
├── phase2_test_classifier.py    # Phase 2: Genre classifier integration
├── phase3_test_llm.py           # Phase 3: LLM prompt-writing integration
├── phase4_test_image.py         # Phase 4: Image generation integration
│
├── test_app.py                  # ★ Unit test suite — 6 pytest tests, no remote calls (94 lines)
├── dance_of_lyfe.py             # Early CI utility function
│
├── requirements.txt             # Python dependencies
│
├── .claude/                     # Claude AI assistant workspace configuration
├── .github/
│   └── workflows/               # GitHub Actions CI — automated test runs on push
└── tests/                       # Additional test assets and fixtures
```

> Files marked **★** are the primary deliverables.

---

## 🧩 Phased Development

The project follows an **iterative, phase-gated development methodology**: the user interface is validated independently before any AI model is integrated, then each AI component is tested in isolation before being connected to the full pipeline. This approach minimizes debugging surface area at each stage.

| Phase | File | Description | AI Integrated |
|---|---|---|---|
| **1** | `phase1_ui.py` | Gradio UI scaffold with hardcoded fake outputs — no models | ❌ None |
| **2** | `phase2_test_classifier.py` | Integrate local genre classifier; validate input/output contract | ✅ Audio classifier |
| **3** | `phase3_test_llm.py` | Connect remote LLM; validate prompt generation | ✅ + Remote LLM |
| **4** | `phase4_test_image.py` | Connect image generator; validate end-to-end image output | ✅ + Diffusion model |
| **5** | `app.py` | Full connected pipeline; production-ready Gradio UI | ✅ Complete pipeline |
| **6** | `app.py` | Adaptive LLM failover with circuit breaker *(extra credit)* | ✅ + Resilience layer |

Each phase's intermediate file is preserved in the repository, providing a clear audit trail of development progress.

---

## ⚙️ Setup & Installation

### Prerequisites

- Python **3.10** or higher
- A [Hugging Face account](https://huggingface.co/join) *(required for remote inference features)*
- GPU recommended — CPU fallback is supported via `torch.float32`

### 1. Clone the repository

```bash
git clone https://github.com/sanikadhanwate/musical_genre_illustrator.git
cd musical_genre_illustrator
```

### 2. Create and activate a virtual environment

```bash
# macOS / Linux
python -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate.bat
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure your Hugging Face token *(optional)*

> Remote LLM and remote image generation require authentication. The app runs fully offline without this — local genre classification and local image generation work without any token.

```bash
# macOS / Linux
export HF_TOKEN=hf_your_token_here

# Windows
set HF_TOKEN=hf_your_token_here
```

Alternatively, use the **HF Login button** directly in the Gradio UI after launching.

### 5. Launch the application

```bash
python app.py
```

Open your browser at `http://localhost:7860`.

---

## 🎛️ Usage

### Standard workflow

1. **Upload an audio file** (`.wav`, `.mp3`, `.flac`, etc.)
2. **Log in with Hugging Face** using the `gr.LoginButton` in the UI *(for remote features)*
3. Optionally check **"Use Local Model for image generation"** for offline generation
4. Click **"Analyze Music"**

### Output fields

| Field | Description |
|---|---|
| **Genre** | Predicted genre label (e.g., `jazz`) |
| **Confidence** | Classifier probability score `[0.0 – 1.0]` |
| **Prompt written by** | Source model for the image prompt — `Remote LLM`, `Local LLM`, or `Static fallback` |
| **AI Interpretation** | The full image-generation prompt passed to the diffusion model |
| **Generated Artwork** | Rendered image displayed inline |
| **Saved image file** | Downloadable PNG — `generated_images/{genre}_{timestamp}.png` |

### Running individual pipeline phases

```bash
# Phase 1: UI only (no AI)
python phase1_ui.py

# Full pipeline (Phase 5 + 6)
python app.py
```

---

## 🧪 Testing

All tests are written with **pytest** and require **no remote API calls**. The local LLM download is stubbed via `monkeypatch`, so the full suite runs in an isolated environment without any model weights.

### Run the test suite

```bash
# Run all tests with verbose output
pytest test_app.py -v

# Run a specific test
pytest test_app.py::test_simulated_remote_failure_routes_to_local_llm -v
```

### Test descriptions

| Test | Coverage |
|---|---|
| `test_classify_audio_handles_none` | `classify_audio(None)` returns `("unknown", 0.0)` without raising |
| `test_classify_audio_returns_genre_and_confidence` | Real audio returns a valid `str` genre and `float` confidence *(skipped if `sample.wav` absent)* |
| `test_generate_image_local_returns_image` | `tiny-sd` diffusion pipeline returns a non-`None` image object |
| `test_simulated_remote_failure_routes_to_local_llm` | Forced failure routes to local LLM; source label contains `"Local LLM"` + `"failover"`; breaker trips |
| `test_remote_stays_in_cooldown_after_a_failure_and_skips_straight_to_local` | Second call during cooldown skips remote without re-attempting it |
| `test_both_llms_unavailable_falls_back_to_static_template` | Both LLMs raising returns `FALLBACK_PROMPTS["jazz"]`; source label contains `"fallback"` |

### Test isolation mechanism

An `autouse` fixture resets the global circuit breaker before and after every test, preventing state bleed:

```python
@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    _remote_breaker.unavailable_until = 0.0
    _remote_breaker.last_reason = None
    yield
    _remote_breaker.unavailable_until = 0.0
    _remote_breaker.last_reason = None
```

### Adding a test audio file

To enable `test_classify_audio_returns_genre_and_confidence`, place a short `.wav` in the repository root:

```bash
# Generate a 5-second test clip using ffmpeg
ffmpeg -f lavfi -i "sine=frequency=440:duration=5" sample.wav
```

### Continuous Integration

The `.github/workflows/` directory contains a GitHub Actions workflow that automatically runs the test suite on every push and pull request.

---

## ⚖️ Design Decisions & Trade-offs

### 1. Genre classifier is always local — never remote

**Decision:** `dima806/music_genres_classification` runs on-device on every request.

**Rationale:** Audio classification is a lightweight task — the model is small and fast. Keeping Step 1 fully local eliminates a remote dependency at the most critical point in the pipeline. The app can classify genres even when the HF API is unavailable, which simplifies failure handling: only Step 2 and Step 3 need resilience logic.

---

### 2. Lazy loading for the local LLM

**Decision:** `Qwen2.5-0.5B-Instruct` is not loaded at startup — only when a failover is first triggered.

**Rationale:** Loading a 0.5B model takes several seconds and consumes hundreds of MB of RAM. If the remote LLM is healthy (the common-case path), this cost is never incurred. Lazy initialization is the correct engineering choice here and is a standard pattern in resource-constrained ML serving environments.

---

### 3. Static prompts as the guaranteed last resort

**Decision:** Ten handcrafted genre-specific strings in `FALLBACK_PROMPTS` serve as an absolute safety net.

**Rationale:** A deterministic fallback guarantees the pipeline always produces *some* output. Even a lower-quality static prompt generates an image, which is better than an unhandled exception reaching the user. This aligns with the MLOps principle that every critical path should have a final, deterministic fallback with no external dependencies.

---

### 4. ZeroGPU-compatible deferred device placement

**Decision:** Models are instantiated on CPU at startup; `.to("cuda")` is called inside `@spaces.GPU`-decorated functions only.

**Rationale:** HF Spaces' ZeroGPU scheduler allocates GPU resources dynamically, per-request. Calling `.to("cuda")` at module import time would fail because no GPU is assigned at startup. The `@spaces.GPU` decorator signals ZeroGPU to allocate a GPU for the duration of that function call. This is not an optimization — it is a hard platform requirement.

---

### 5. `simulate_remote_failure` flag in the production function signature

**Decision:** The failover simulation flag is a parameter of `create_visual_prompt()`, not a test-only mock.

**Rationale:** Demonstrating circuit-breaker behavior on demand — without a real outage — requires controlled fault injection. Embedding `simulate_remote_failure=False` in the production signature (defaulting to no effect) is a common pattern in resilience engineering. It also means the simulation is testable through the same code path used in production, not a separate mock.

---

## 🔮 Limitations & Future Work

### Current Limitations

| Limitation | Risk |
|---|---|
| Global `_remote_breaker` state is not thread-safe | Two concurrent Gradio requests could race on `mark_down()` |
| `Qwen/Qwen-Image` model ID may be a placeholder | Remote image generation may not resolve to a valid endpoint |
| No pinned versions in `requirements.txt` | Breaking changes in `diffusers` or `transformers` minor releases could silently break the app |
| `generate_image_remote()` returning `None` is not handled in `analyze_music()` | A failed remote image call would raise `AttributeError` on `image.save()` |
| Fixed 60-second cooldown regardless of outage severity | Transient blips and prolonged outages receive identical treatment |

### Proposed Improvements

- **Thread-safe circuit breaker** — wrap `unavailable_until` mutations in a `threading.Lock()` to prevent race conditions under concurrent requests
- **Exponential backoff** — replace the fixed cooldown with an exponential window (60s → 120s → 240s) for persistent outages
- **Breaker state in the UI** — surface remaining cooldown time and breaker state in a Gradio `State` component
- **Dependency pinning** — use `==` version constraints in `requirements.txt` and automate updates with Dependabot or Renovate
- **Graceful `None` handling** — add a null-check after `generate_image_remote()` and surface a user-friendly error in the Gradio UI
- **Async inference** — use `async InferenceClient` to avoid blocking the Gradio event loop during remote API calls
- **Top-k genre display** — return and display the top-3 genre predictions with confidence scores rather than just the top-1

---

## 🤝 Acknowledgments

- **[Hugging Face](https://huggingface.co)** — model hub, Inference API, Spaces platform, and ZeroGPU infrastructure
- **[dima806](https://huggingface.co/dima806)** — `music_genres_classification` audio model
- **[Segmind](https://huggingface.co/segmind)** — `tiny-sd` lightweight diffusion model
- **[Meta AI](https://ai.meta.com)** — Llama 3.1 model family
- **[Qwen Team / Alibaba Cloud](https://github.com/QwenLM)** — Qwen 2.5 model series
- **Martin Fowler** — for formalizing the Circuit Breaker pattern in distributed systems design

---

<div align="center">

*Submitted for the Machine Learning Development and Operations course.*

[![Made with Gradio](https://img.shields.io/badge/Made%20with-Gradio-FF7C00?style=flat-square&logo=huggingface&logoColor=white)](https://gradio.app)
[![Powered by HF](https://img.shields.io/badge/Powered%20by-Hugging%20Face-FFD21E?style=flat-square)](https://huggingface.co)

**[⬆ Back to top](#-musical-genre-illustrator)**

</div>
