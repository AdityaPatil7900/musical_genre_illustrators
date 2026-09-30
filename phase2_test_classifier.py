"""
PHASE 2: Real genre classification, tested standalone first.
Run: python phase2_test_classifier.py path/to/song.wav
"""

import sys
from transformers import pipeline

classifier = pipeline(
    "audio-classification",
    model="dima806/music_genres_classification"
)


def classify_audio(audio_file):
    """Returns (genre, confidence) for the top prediction."""
    result = classifier(audio_file)
    genre = result[0]["label"]
    confidence = result[0]["score"]
    return genre, confidence


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python phase2_test_classifier.py path/to/song.wav")
        sys.exit(1)

    audio_file = sys.argv[1]
    genre, confidence = classify_audio(audio_file)
    print(f"Genre: {genre}")
    print(f"Confidence: {confidence:.2f}")
