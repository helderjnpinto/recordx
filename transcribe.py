#!/usr/bin/env python3
"""Transcription (WhisperX / faster-whisper) and speaker diarization (pyannote)."""
import gc
import os
import re
import warnings

warnings.filterwarnings("ignore", category=UserWarning)

import torch

try:
    import whisperx
    WHISPERX_AVAILABLE = True
except ImportError:
    WHISPERX_AVAILABLE = False

try:
    from pyannote.audio import Pipeline
    PYANNOTE_AVAILABLE = True
except ImportError:
    PYANNOTE_AVAILABLE = False

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False

DEFAULT_DIARIZATION_MODEL = "pyannote/speaker-diarization-community-1"


class DiarizationError(RuntimeError):
    """Raised when diarization was requested but could not be loaded/run."""


def detect_device():
    if torch.cuda.is_available():
        device = "cuda"
        print(f"[+] CUDA detected: {torch.cuda.get_device_name()}")
        print(f"    VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GB")
    else:
        device = "cpu"
        print("[+] CUDA not available, using CPU")
    return device


def is_valid_segment(text, duration):
    """Filter out garbage transcriptions (timer/counter artifacts, VAD noise)."""
    text = text.strip()
    if not text:
        return False
    if re.match(r'^[\d\s]+$', text):
        return False
    if len(text) <= 2 and not re.search(r'[aeiouáàâãéèêíóôõúü]', text, re.IGNORECASE):
        return False
    if re.match(r'^[\d:.]+\s*[\d:.]*$', text):
        return False
    if re.match(r'^[,.\-_:;]+$', text):
        return False
    if duration < 0.5 and len(text.split()) <= 2:
        if not re.search(r'[aeiouáàâãéèêíóôõúü]', text, re.IGNORECASE):
            return False
    return True


def load_diarization_pipeline(diarization_model, hf_token, device):
    if not PYANNOTE_AVAILABLE:
        raise DiarizationError(
            "pyannote.audio is not installed. Install it with `pip install pyannote.audio` "
            "or run with --no-diarize."
        )
    token = hf_token or os.environ.get("HF_TOKEN")
    if not token:
        raise DiarizationError(
            "Diarization requires a Hugging Face access token. Set HF_TOKEN in .env "
            "or pass --hf-token."
        )
    try:
        pipeline = Pipeline.from_pretrained(diarization_model, token=token)
    except Exception as e:
        model_url = f"https://huggingface.co/{diarization_model}"
        raise DiarizationError(
            f"Failed to load diarization model '{diarization_model}': {e}\n"
            f"    This is a repository access-gate issue, NOT a problem with your HF_TOKEN's\n"
            f"    validity - the token can be perfectly valid and still be refused if the\n"
            f"    account hasn't been granted access to this specific gated repo.\n"
            f"    Visit {model_url} while logged in as the token's account, click\n"
            f"    'Agree and access repository'. Access is not always instant - if it still\n"
            f"    fails right after accepting, wait a minute and try again before assuming\n"
            f"    the token itself is broken."
        ) from e
    if device == "cuda":
        pipeline = pipeline.to(torch.device("cuda"))
    return pipeline


def merge_consecutive_speaker_segments(segments, max_gap=1.0):
    if not segments:
        return []
    merged = []
    current = segments[0].copy()
    for next_seg in segments[1:]:
        if (current["speaker"] == next_seg["speaker"]
                and next_seg["start"] - current["end"] <= max_gap):
            current["end"] = next_seg["end"]
            current["text"] += " " + next_seg["text"]
        else:
            merged.append(current)
            current = next_seg.copy()
    merged.append(current)
    return merged


def _duration_of(result, segments):
    if result.get("duration"):
        return result["duration"]
    return max((seg["end"] for seg in segments), default=0)


def _single_speaker_segments(result, language):
    segments = [
        {
            "speaker": "SPEAKER_00",
            "start": float(seg["start"]),
            "end": float(seg["end"]),
            "text": seg["text"].strip(),
        }
        for seg in result["segments"]
    ]
    meta = {
        "diarization_model": "none",
        "language": result.get("language", language),
        "total_segments": len(segments),
        "unique_speakers": ["SPEAKER_00"],
        "duration": _duration_of(result, segments),
    }
    return segments, meta


def transcribe_with_faster_whisper(audio_path, model_name, device, compute_type, language):
    print("[+] Using faster-whisper")
    print(f"[+] Loading faster-whisper model: {model_name}")

    fw_compute_type = compute_type if compute_type in ("float16", "int8") else "default"
    model = WhisperModel(model_name, device=device, compute_type=fw_compute_type)

    print("[+] Transcribing with faster-whisper...")
    segments_iter, info = model.transcribe(
        str(audio_path),
        language=language,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        condition_on_previous_text=True,
        word_timestamps=False,
    )

    segments = []
    for seg in segments_iter:
        text = seg.text.strip()
        if is_valid_segment(text, seg.end - seg.start):
            segments.append({
                "speaker": "SPEAKER_00",
                "start": float(seg.start),
                "end": float(seg.end),
                "text": text,
            })

    meta = {
        "diarization_model": "none",
        "language": getattr(info, "language", language),
        "total_segments": len(segments),
        "unique_speakers": ["SPEAKER_00"],
        "duration": getattr(info, "duration", 0),
        "backend": "faster-whisper",
    }
    return segments, meta


def _as_annotation(diarization):
    """pyannote.audio >=4 returns a DiarizeOutput wrapping Annotations instead
    of returning an Annotation directly; older versions return the Annotation
    itself. Prefer exclusive_speaker_diarization (no overlapping speech turns)
    since we're assigning one speaker per transcribed word/segment."""
    if hasattr(diarization, "exclusive_speaker_diarization"):
        return diarization.exclusive_speaker_diarization
    if hasattr(diarization, "speaker_diarization"):
        return diarization.speaker_diarization
    return diarization


def _diarize_segments(result, diarization):
    diarization = _as_annotation(diarization)
    speaker_segments = []
    for segment in result["segments"]:
        words = segment.get("words", [])
        if words:
            for word in words:
                if "start" not in word or "end" not in word:
                    continue
                speaker = _speaker_for_span(diarization, word["start"], word["end"])
                speaker_segments.append({
                    "speaker": speaker,
                    "start": float(word["start"]),
                    "end": float(word["end"]),
                    "text": word["word"].strip(),
                })
        else:
            speaker = _speaker_for_span(diarization, segment["start"], segment["end"])
            speaker_segments.append({
                "speaker": speaker,
                "start": float(segment["start"]),
                "end": float(segment["end"]),
                "text": segment["text"].strip(),
            })
    return merge_consecutive_speaker_segments(speaker_segments)


def _speaker_for_span(diarization, start, end):
    for turn, _, speaker_label in diarization.itertracks(yield_label=True):
        if turn.start <= start and turn.end >= end:
            return speaker_label
    return "SPEAKER_UNKNOWN"


def transcribe_with_diarization(
    audio_path,
    model_name="large-v3",
    device="auto",
    compute_type="float16",
    language="pt",
    min_speakers=None,
    max_speakers=None,
    diarization_model=DEFAULT_DIARIZATION_MODEL,
    hf_token=None,
    diarize=True,
):
    """
    Transcribe audio with WhisperX (falling back to faster-whisper if WhisperX is
    unavailable) and, when diarize=True, label segments with real speakers via
    pyannote. Raises DiarizationError if diarization was requested but failed -
    callers must not treat that as "just use SPEAKER_00", the caller decides.
    """
    print(f"[+] Using device: {device}")

    if not WHISPERX_AVAILABLE:
        if not FASTER_WHISPER_AVAILABLE:
            raise ImportError("Neither WhisperX nor faster-whisper is available.")
        segments, meta = transcribe_with_faster_whisper(audio_path, model_name, device, compute_type, language)
        meta["device"] = device
        meta["whisper_model"] = model_name
        meta["min_speakers"] = None
        meta["max_speakers"] = None
        return segments, meta

    print(f"[+] Loading WhisperX model: {model_name}")
    model = whisperx.load_model(model_name, device, compute_type=compute_type)

    print("[+] Transcribing with WhisperX...")
    result = model.transcribe(str(audio_path), language=language)

    # Free the ASR model's GPU memory before loading the diarization pipeline -
    # both are large enough that keeping both resident can exceed VRAM on
    # smaller GPUs (e.g. 6GB laptop cards).
    del model
    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()

    if not diarize:
        segments, meta = _single_speaker_segments(result, language)
        meta["device"] = device
        meta["whisper_model"] = model_name
        meta["min_speakers"] = None
        meta["max_speakers"] = None
        return segments, meta

    print("[+] Loading diarization pipeline...")
    pipeline = load_diarization_pipeline(diarization_model, hf_token, device)

    print("[+] Performing speaker diarization...")
    diarization = pipeline(str(audio_path), min_speakers=min_speakers, max_speakers=max_speakers)

    del pipeline
    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()

    print("[+] Aligning transcription with diarization...")
    aligned = result
    try:
        model_a, align_meta = whisperx.load_align_model(language_code=language, device=device)
        aligned = whisperx.align(result["segments"], model_a, align_meta, str(audio_path), device)
    except Exception as e:
        print(f"[!] Warning: Alignment failed ({e}); using original timestamps")

    merged_segments = _diarize_segments(aligned, diarization)

    meta = {
        "whisper_model": model_name,
        "diarization_model": diarization_model,
        "language": result.get("language", language),
        "device": device,
        "min_speakers": min_speakers,
        "max_speakers": max_speakers,
        "total_segments": len(merged_segments),
        "unique_speakers": sorted(set(seg["speaker"] for seg in merged_segments)),
        "duration": _duration_of(result, merged_segments),
    }
    return merged_segments, meta
