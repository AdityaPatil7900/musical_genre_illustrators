"""
PHASE 1: Interface only. No AI. Just wiring up the UI so you can see
the shape of the app before adding any real intelligence.
Run: python phase1_ui.py
"""

import gradio as gr


def fake_analyze_music(audio_file):
    """Placeholder - returns fake data so we can test the UI layout."""
    if audio_file is None:
        return "No file uploaded", "N/A", "N/A", None

    genre = "Jazz"
    confidence = "0.91"
    ai_interpretation = (
        "A soulful midnight jazz club with a saxophonist, warm amber "
        "lighting, expressive brush strokes, atmospheric cinematic illustration."
    )
    generated_image = None  # Phase 4 will fill this in with a real image

    return genre, confidence, ai_interpretation, generated_image


with gr.Blocks(title="Music-to-Art Generator") as demo:
    gr.Markdown("# 🎵 Music-to-Art Generator")

    audio_input = gr.Audio(type="filepath", label="Upload Audio")
    analyze_btn = gr.Button("Analyze Music", variant="primary")

    with gr.Row():
        genre_output = gr.Textbox(label="Genre")
        confidence_output = gr.Textbox(label="Confidence")

    prompt_output = gr.Textbox(label="AI Interpretation", lines=3)
    image_output = gr.Image(label="Generated Artwork")

    analyze_btn.click(
        fn=fake_analyze_music,
        inputs=[audio_input],
        outputs=[genre_output, confidence_output, prompt_output, image_output],
    )

if __name__ == "__main__":
    demo.launch()
