#!/usr/bin/env python3
import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
import warnings

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore", category=UserWarning)

import torch

# Try to import WhisperX, but handle gracefully if not available
try:
    import whisperx
    WHISPERX_AVAILABLE = True
except ImportError as e:
    print(f"[!] Warning: WhisperX not available ({e})")
    print("    Will use faster-whisper fallback")
    WHISPERX_AVAILABLE = False

# Try to import pyannote, but handle gracefully if not available
try:
    from pyannote.audio import Pipeline
    PYANNOTE_AVAILABLE = True
except ImportError as e:
    print(f"[!] Warning: pyannote not available ({e})")
    print("    Will use WhisperX-only mode without speaker diarization")
    PYANNOTE_AVAILABLE = False

# Import faster-whisper as reliable fallback
try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError as e:
    print(f"[!] Warning: faster-whisper not available ({e})")
    FASTER_WHISPER_AVAILABLE = False


def is_valid_segment(text, duration):
    """
    Filter out garbage transcriptions that appear after speech ends.
    Returns False for:
    - Segments containing only numbers (like "1435", "1436")
    - Very short segments with just numbers or single words
    - Segments that appear to be timer/counter outputs
    """
    import re
    
    # Strip text
    text = text.strip()
    if not text:
        return False
    
    # If text is only numbers (with or without spaces), reject it
    # This catches "1435", "1436", "1 2 3 4 5" etc.
    if re.match(r'^[\d\s]+$', text):
        return False
    
    # If text is very short (1-2 chars) and doesn't look like a real word, reject
    if len(text) <= 2 and not re.search(r'[aeiouáàâãéèêíóôõúü]', text, re.IGNORECASE):
        return False
    
    # Reject segments that look like timestamps or counters
    # e.g., "1435", "1411", "10:30", "10 30"
    if re.match(r'^[\d:.]+\s*[\d:.]*$', text):
        return False
    
    # Reject segments that are just punctuation
    if re.match(r'^[,.\-_:;]+$', text):
        return False
    
    # Reject very short segments that are likely VAD artifacts
    if duration < 0.5 and len(text.split()) <= 2:
        # But keep if it contains vowels (real words)
        if not re.search(r'[aeiouáàâãéèêíóôõúü]', text, re.IGNORECASE):
            return False
    
    return True


def run_cmd(cmd, check=True, capture_output=False, text=True):
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture_output,
        text=text,
    )


def ensure_ffmpeg():
    try:
        run_cmd(["ffmpeg", "-version"], check=True, capture_output=True)
    except Exception:
        print("ERROR: ffmpeg not found in PATH.")
        sys.exit(1)


def detect_device():
    """Detect optimal device for WhisperX and pyannote"""
    if torch.cuda.is_available():
        device = "cuda"
        print(f"[+] CUDA detected: {torch.cuda.get_device_name()}")
        print(f"    VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GB")
    else:
        device = "cpu"
        print("[+] CUDA not available, using CPU")
    return device


def timestamp_slug():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_ffmpeg_command(monitor_source, mic_source, output_wav, sample_rate=16000):
    """
    Record desktop/Discord audio from a Pulse/PipeWire monitor source
    and microphone from another source, then mix both into a mono WAV.

    Notes:
    - We resample to 16 kHz mono for Whisper.
    - We slightly reduce each input before mixing to avoid clipping.
    - loudnorm helps stabilize transcript quality a bit.
    """
    filter_complex = (
        "[0:a]volume=1.0,aresample={sr},aformat=sample_fmts=s16:channel_layouts=mono[a0];"
        "[1:a]volume=1.0,aresample={sr},aformat=sample_fmts=s16:channel_layouts=mono[a1];"
        "[a0][a1]amix=inputs=2:duration=longest:dropout_transition=2,"
        "loudnorm=I=-16:TP=-1.5:LRA=11[out]"
    ).format(sr=sample_rate)

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "warning",
        "-f", "pulse",
        "-i", monitor_source,
        "-f", "pulse",
        "-i", mic_source,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-ar", str(sample_rate),
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(output_wav),
    ]
    return cmd


def write_srt(segments, srt_path):
    def fmt_ts(seconds):
        ms = int(round(seconds * 1000))
        h = ms // 3600000
        ms %= 3600000
        m = ms // 60000
        ms %= 60000
        s = ms // 1000
        ms %= 1000
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    with open(srt_path, "w", encoding="utf-8") as f:
        for idx, seg in enumerate(segments, start=1):
            start = fmt_ts(seg["start"])
            end = fmt_ts(seg["end"])
            text = seg["text"].strip()
            speaker = seg.get("speaker", "UNKNOWN")
            f.write(f"{idx}\n{start} --> {end}\n[{speaker}] {text}\n\n")


def transcribe_with_diarization(
    audio_path,
    model_name="large-v3",
    device="auto",
    compute_type="float16",
    language="pt",
    min_speakers=None,
    max_speakers=None,
    diarization_model="pyannote/speaker-diarization-community-1.0",
    hf_token=None,
):
    """
    Transcribe audio with WhisperX and perform speaker diarization with pyannote.
    Returns speaker-labeled segments ready for n8n integration.
    Falls back to faster-whisper if WhisperX has dependency issues.
    """
    print(f"[+] Using device: {device}")
    
    # Try WhisperX first
    if WHISPERX_AVAILABLE:
        print(f"[+] Loading WhisperX model: {model_name}")
        print("    (First time may download model - this can take a while)")
        
        try:
            # Load WhisperX model
            model = whisperx.load_model(model_name, device, compute_type=compute_type)
            
            print("[+] Transcribing with WhisperX...")
            
            # Transcribe with WhisperX
            result = model.transcribe(str(audio_path), language=language)
            
            # Check if pyannote is available
            if not PYANNOTE_AVAILABLE:
                print("[!] pyannote not available, using WhisperX-only mode")
                return create_fallback_segments(result, "whisperx", model_name, device, language)
            
            print("[+] Loading diarization pipeline...")
            print("    (First time may download diarization model)")
            
            # Load diarization pipeline
            try:
                # Check for token in args first, then environment
                token = hf_token or os.environ.get("HF_TOKEN")
                diarization_pipeline = Pipeline.from_pretrained(
                    diarization_model,
                    token=token
                )
                if device == "cuda":
                    diarization_pipeline = diarization_pipeline.to(torch.device("cuda"))
            except Exception as e:
                print(f"[!] Error loading diarization pipeline: {e}")
                print("    Falling back to transcription without diarization")
                return create_fallback_segments(result, "whisperx", model_name, device, language)
            
            print("[+] Performing speaker diarization...")
            
            # Perform diarization
            try:
                diarization = diarization_pipeline(
                    str(audio_path),
                    min_speakers=min_speakers,
                    max_speakers=max_speakers
                )
            except Exception as e:
                print(f"[!] Error in diarization: {e}")
                print("    Falling back to transcription without diarization")
                return create_fallback_segments(result, "whisperx", model_name, device, language)
            
            print("[+] Aligning transcription with diarization...")
            
            # Align words with timestamps
            try:
                model_a, metadata = whisperx.load_align_model(
                    language_code=language, 
                    device=device
                )
                result_aligned = whisperx.align(
                    result["segments"], 
                    model_a, 
                    metadata, 
                    str(audio_path), 
                    device
                )
            except Exception as e:
                print(f"[!] Warning: Alignment failed ({e})")
                print("    Using original timestamps")
                result_aligned = result
            
            # Merge transcription with diarization
            speaker_segments = []
            
            # Get word-level segments if available
            segments = result_aligned.get("segments", result["segments"])
            
            for segment in segments:
                words = segment.get("words", [])
                
                if words:
                    # Word-level processing
                    for word in words:
                        word_start = word["start"]
                        word_end = word["end"]
                        word_text = word["word"]
                        
                        # Find speaker for this word
                        speaker = "SPEAKER_UNKNOWN"
                        for turn, _, speaker_label in diarization.itertracks(yield_label=True):
                            if turn.start <= word_start and turn.end >= word_end:
                                speaker = speaker_label
                                break
                        
                        speaker_segments.append({
                            "speaker": speaker,
                            "start": float(word_start),
                            "end": float(word_end),
                            "text": word_text.strip()
                        })
                else:
                    # Segment-level processing
                    seg_start = segment["start"]
                    seg_end = segment["end"]
                    seg_text = segment["text"].strip()
                    
                    # Find speaker for this segment
                    speaker = "SPEAKER_UNKNOWN"
                    for turn, _, speaker_label in diarization.itertracks(yield_label=True):
                        if turn.start <= seg_start and turn.end >= seg_end:
                            speaker = speaker_label
                            break
                    
                    speaker_segments.append({
                        "speaker": speaker,
                        "start": float(seg_start),
                        "end": float(seg_end),
                        "text": seg_text
                    })
            
            # Merge consecutive segments from same speaker
            merged_segments = merge_consecutive_speaker_segments(speaker_segments)
            
            # Create metadata
            meta = {
                "whisper_model": model_name,
                "diarization_model": diarization_model,
                "language": result.get("language", language),
                "device": device,
                "min_speakers": min_speakers,
                "max_speakers": max_speakers,
                "total_segments": len(merged_segments),
                "unique_speakers": list(set(seg["speaker"] for seg in merged_segments)),
                "duration": result.get("duration", 0)
            }
            
            return merged_segments, meta
            
        except Exception as e:
            print(f"[!] WhisperX failed: {e}")
            print("    Falling back to faster-whisper...")
    
    # Fallback to faster-whisper
    if FASTER_WHISPER_AVAILABLE:
        return transcribe_with_faster_whisper(
            audio_path, model_name, device, compute_type, language
        )
    else:
        print("[!] Neither WhisperX nor faster-whisper available!")
        raise ImportError("No transcription backend available")


def transcribe_with_faster_whisper(
    audio_path,
    model_name="large-v3",
    device="auto",
    compute_type="float16",
    language="pt",
):
    """Fallback transcription using faster-whisper"""
    print(f"[+] Using faster-whisper fallback")
    print(f"[+] Loading faster-whisper model: {model_name}")
    
    # Map compute_type for faster-whisper
    if compute_type == "float16":
        fw_compute_type = "float16"
    elif compute_type == "int8":
        fw_compute_type = "int8"
    else:
        fw_compute_type = "default"
    
    try:
        model = WhisperModel(model_name, device=device, compute_type=fw_compute_type)
    except KeyboardInterrupt:
        print("\n[!] Model download interrupted. The audio file is saved.")
        print("    Run again to resume - the model will continue downloading.")
        raise

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
    full_text_parts = []

    for seg in segments_iter:
        # Filter out garbage: very short segments or just numbers
        text = seg.text.strip()
        if is_valid_segment(text, seg.end - seg.start):
            item = {
                "speaker": "SPEAKER_00",
                "start": float(seg.start),
                "end": float(seg.end),
                "text": text,
            }
            segments.append(item)
            full_text_parts.append(text)

    meta = {
        "whisper_model": model_name,
        "diarization_model": "none",
        "language": getattr(info, "language", language),
        "device": device,
        "min_speakers": None,
        "max_speakers": None,
        "total_segments": len(segments),
        "unique_speakers": ["SPEAKER_00"],
        "duration": getattr(info, "duration", 0),
        "fallback": True,
        "backend": "faster-whisper"
    }

    return segments, meta


def create_fallback_segments(result, backend="whisperx", model_name="large-v3", device="auto", language="pt"):
    """Create segments without diarization as fallback"""
    segments = []
    
    if backend == "whisperx":
        # WhisperX result format
        for segment in result["segments"]:
            segments.append({
                "speaker": "SPEAKER_00",
                "start": float(segment["start"]),
                "end": float(segment["end"]),
                "text": segment["text"].strip()
            })
    else:
        # faster-whisper result format (already processed)
        return result
    
    meta = {
        "whisper_model": model_name,
        "diarization_model": "none",
        "language": result.get("language", language),
        "device": device,
        "min_speakers": None,
        "max_speakers": None,
        "total_segments": len(segments),
        "unique_speakers": ["SPEAKER_00"],
        "duration": result.get("duration", 0),
        "fallback": True,
        "backend": backend
    }
    
    return segments, meta


def merge_consecutive_speaker_segments(segments, max_gap=1.0):
    """Merge consecutive segments from the same speaker"""
    if not segments:
        return []
    
    merged = []
    current = segments[0].copy()
    
    for next_seg in segments[1:]:
        # Check if same speaker and gap is small enough
        if (current["speaker"] == next_seg["speaker"] and 
            next_seg["start"] - current["end"] <= max_gap):
            # Merge segments
            current["end"] = next_seg["end"]
            current["text"] += " " + next_seg["text"]
        else:
            # Add current and start new
            merged.append(current)
            current = next_seg.copy()
    
    merged.append(current)
    return merged


def create_n8n_output(segments, meta):
    """Create output format optimized for n8n processing"""
    # Basic transcript text
    transcript_lines = []
    for seg in segments:
        transcript_lines.append(f"[{seg['speaker']}] {seg['text']}")
    transcript = "\n".join(transcript_lines)
    
    # Speaker turns for easy processing
    speaker_turns = []
    for seg in segments:
        speaker_turns.append({
            "speaker": seg["speaker"],
            "start": seg["start"],
            "end": seg["end"],
            "duration": seg["end"] - seg["start"],
            "text": seg["text"],
            "word_count": len(seg["text"].split())
        })
    
    # Basic statistics
    speaker_stats = {}
    for seg in segments:
        speaker = seg["speaker"]
        if speaker not in speaker_stats:
            speaker_stats[speaker] = {
                "turns": 0,
                "words": 0,
                "duration": 0.0
            }
        speaker_stats[speaker]["turns"] += 1
        speaker_stats[speaker]["words"] += len(seg["text"].split())
        speaker_stats[speaker]["duration"] += seg["end"] - seg["start"]
    
    n8n_output = {
        "meeting_info": {
            "timestamp": timestamp_slug(),
            "duration": meta["duration"],
            "language": meta["language"],
            "total_speakers": len(meta["unique_speakers"]),
            "total_turns": len(segments),
            "total_words": sum(len(seg["text"].split()) for seg in segments)
        },
        "transcript": transcript,
        "speaker_turns": speaker_turns,
        "speaker_statistics": speaker_stats,
        "metadata": meta
    }
    
    return n8n_output


def summarize_standup(n8n_output):
    """Generate standup-specific summary"""
    speaker_turns = n8n_output["speaker_turns"]
    speaker_stats = n8n_output["speaker_statistics"]
    
    # Extract key information by speaker
    speaker_summaries = {}
    for speaker, stats in speaker_stats.items():
        # Find all turns for this speaker
        speaker_texts = [turn["text"] for turn in speaker_turns if turn["speaker"] == speaker]
        combined_text = " ".join(speaker_texts)
        
        # Simple keyword-based extraction (can be enhanced with LLM)
        summary = {
            "speaker": speaker,
            "total_talk_time": stats["duration"],
            "word_count": stats["words"],
            "key_points": extract_key_points(combined_text),
            "full_text": combined_text[:500] + "..." if len(combined_text) > 500 else combined_text
        }
        speaker_summaries[speaker] = summary
    
    meeting_summary = {
        "meeting_type": "standup",
        "timestamp": n8n_output["meeting_info"]["timestamp"],
        "duration_minutes": round(n8n_output["meeting_info"]["duration"] / 60, 1),
        "participants": list(speaker_summaries.keys()),
        "speaker_summaries": speaker_summaries,
        "overall_summary": generate_overall_summary(speaker_summaries)
    }
    
    return meeting_summary


def extract_key_points(text):
    """Extract key points from text (simple keyword-based approach)"""
    # Portuguese keywords for standups
    keywords = {
        "progress": ["fiz", "concluí", "terminei", "finalizei", "avançei", "progresso"],
        "plans": ["vou", "farei", "pretendo", "planejo", "hoje", "próximo"],
        "blockers": ["bloqueio", "problema", "dificuldade", "ajuda", "preciso"],
        "technical": ["api", "banco", "bug", "teste", "deploy", "merge"]
    }
    
    key_points = {}
    sentences = text.split(".")
    
    for category, words in keywords.items():
        matches = []
        for sentence in sentences:
            if any(word in sentence.lower() for word in words):
                matches.append(sentence.strip())
        if matches:
            key_points[category] = matches[:3]  # Limit to top 3
    
    return key_points


def generate_overall_summary(speaker_summaries):
    """Generate overall meeting summary"""
    total_points = 0
    blockers_found = []
    
    for speaker, summary in speaker_summaries.items():
        key_points = summary.get("key_points", {})
        if "progress" in key_points:
            total_points += len(key_points["progress"])
        if "blockers" in key_points:
            blockers_found.extend(key_points["blockers"])
    
    return {
        "total_progress_points": total_points,
        "blockers_identified": len(blockers_found),
        "blockers": blockers_found[:5],  # Top 5 blockers
        "meeting_health": "good" if len(blockers_found) == 0 else "needs_attention"
    }


def record_until_stopped(ffmpeg_cmd, max_minutes=None):
    print("[+] Starting recording...")
    print("    Press Ctrl+C to stop.\n")
    print("    FFmpeg command:")
    print("    " + " ".join(ffmpeg_cmd))
    print("\n[=] Initializing audio sources...")
    
    proc = subprocess.Popen(ffmpeg_cmd)
    
    # Wait a moment for FFmpeg to start
    time.sleep(1)
    
    if proc.poll() is None:
        print("[=] Recording started successfully!")
        print("[=] Audio capture in progress...")
        print("[=] Recording time: ", end="", flush=True)
    else:
        print("[!] ERROR: FFmpeg failed to start")
        return

    stop_event = threading.Event()
    start_time = time.time()

    def timeout_thread():
        if max_minutes is None:
            return
        time.sleep(max_minutes * 60)
        if proc.poll() is None:
            print(f"\n[+] Max duration reached ({max_minutes} min), stopping...")
            proc.send_signal(signal.SIGINT)
            stop_event.set()

    t = threading.Thread(target=timeout_thread, daemon=True)
    t.start()

    try:
        while proc.poll() is None and not stop_event.is_set():
            elapsed = int(time.time() - start_time)
            print(f"{elapsed:03d}s", end="\r", flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[+] Stopping recording...")
        if proc.poll() is None:
            print("    Waiting for FFmpeg to finalize...")
            # Give FFmpeg more time to finish writing
            time.sleep(2)
            proc.terminate()  # More graceful than SIGINT
            # Wait a bit more for termination
            time.sleep(1)
            # If still running, force kill
            if proc.poll() is None:
                print("    Force stopping FFmpeg...")
                proc.kill()

    proc.wait()
    
    # Calculate and display recording duration
    total_duration = int(time.time() - start_time)
    print(f"\n[=] Recording completed! Duration: {total_duration:03d}s")

    if proc.returncode not in (0, 255):
        print(f"WARNING: ffmpeg exited with code {proc.returncode}")


def main():
    parser = argparse.ArgumentParser(
        description="Record Discord/system audio + mic on Linux and transcribe with WhisperX + pyannote diarization."
    )
    parser.add_argument("--monitor-source", help="Pulse/PipeWire monitor source for Discord/system audio")
    parser.add_argument("--mic-source", help="Pulse/PipeWire microphone source")
    parser.add_argument("--outdir", default="recordings", help="Output directory")
    parser.add_argument("--model", default="large-v3", help="WhisperX model name, e.g. large-v3")
    parser.add_argument("--language", default="pt", help="Language code, e.g. pt or en")
    parser.add_argument("--device", default="auto", help="Device: auto/cuda/cpu")
    parser.add_argument("--compute-type", default="float16", help="float16/int8/auto")
    parser.add_argument("--max-minutes", type=int, default=None, help="Optional hard stop for recording")
    parser.add_argument("--skip-transcription", action="store_true", help="Only record audio, do not transcribe")
    parser.add_argument("--transcribe-only", help="Only transcribe existing audio file (path to wav file)")
    
    # Diarization options
    parser.add_argument("--min-speakers", type=int, default=None, help="Minimum number of speakers")
    parser.add_argument("--max-speakers", type=int, default=None, help="Maximum number of speakers")
    parser.add_argument("--diarization-model", default="pyannote/speaker-diarization-community-1.0", 
                       help="Diarization model")
    parser.add_argument("--hf-token", default=None, 
                       help="HuggingFace token for gated diarization model")
    
    args = parser.parse_args()

    # Validate arguments
    if not args.transcribe_only:
        if not args.monitor_source or not args.mic_source:
            print("ERROR: --monitor-source and --mic-source are required for recording")
            sys.exit(1)

    # Device detection
    if args.device == "auto":
        device = detect_device()
    else:
        device = args.device

    # Handle transcribe-only mode
    if args.transcribe_only:
        audio_path = Path(args.transcribe_only)
        if not audio_path.exists():
            print(f"ERROR: Audio file not found: {audio_path}")
            sys.exit(1)
        
        print(f"[+] Transcribing existing file: {audio_path}")
        segments, meta = transcribe_with_diarization(
            audio_path,
            model_name=args.model,
            device=device,
            compute_type=args.compute_type,
            language=args.language,
            min_speakers=args.min_speakers,
            max_speakers=args.max_speakers,
            diarization_model=args.diarization_model,
            hf_token=args.hf_token,
        )
        
        # Create outputs
        n8n_output = create_n8n_output(segments, meta)
        standup_summary = summarize_standup(n8n_output)
        
        # Save outputs
        output_dir = audio_path.parent
        with open(output_dir / "speaker_segments.json", "w", encoding="utf-8") as f:
            json.dump(segments, f, indent=2, ensure_ascii=False)
        with open(output_dir / "n8n_output.json", "w", encoding="utf-8") as f:
            json.dump(n8n_output, f, indent=2, ensure_ascii=False)
        with open(output_dir / "standup_summary.json", "w", encoding="utf-8") as f:
            json.dump(standup_summary, f, indent=2, ensure_ascii=False)
        with open(output_dir / "transcript.txt", "w", encoding="utf-8") as f:
            f.write(n8n_output["transcript"])
        with open(output_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        
        # Write SRT with speaker labels
        write_srt(segments, output_dir / "transcript.srt")
        
        print(f"[+] Transcription with diarization saved to: {output_dir}")
        print(f"    Speaker segments: {output_dir / 'speaker_segments.json'}")
        print(f"    n8n output: {output_dir / 'n8n_output.json'}")
        print(f"    Standup summary: {output_dir / 'standup_summary.json'}")
        return

    ensure_ffmpeg()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    slug = timestamp_slug()
    session_dir = outdir / f"standup_{slug}"
    session_dir.mkdir(parents=True, exist_ok=True)

    mixed_wav = session_dir / "mixed.wav"
    speaker_segments_json = session_dir / "speaker_segments.json"
    n8n_output_json = session_dir / "n8n_output.json"
    standup_summary_json = session_dir / "standup_summary.json"
    transcript_txt = session_dir / "transcript.txt"
    srt_file = session_dir / "transcript.srt"
    meta_json = session_dir / "metadata.json"

    ffmpeg_cmd = build_ffmpeg_command(
        monitor_source=args.monitor_source,
        mic_source=args.mic_source,
        output_wav=mixed_wav,
        sample_rate=16000,
    )

    record_until_stopped(ffmpeg_cmd, max_minutes=args.max_minutes)

    if not mixed_wav.exists() or mixed_wav.stat().st_size == 0:
        print("ERROR: recording file was not created or is empty.")
        sys.exit(1)

    print(f"[+] Audio saved: {mixed_wav}")

    if args.skip_transcription:
        print("[+] Recording complete. Transcription skipped.")
        return

    print("[+] Starting transcription with speaker diarization...")
    segments, meta = transcribe_with_diarization(
        audio_path=mixed_wav,
        model_name=args.model,
        device=device,
        compute_type=args.compute_type,
        language=args.language,
        min_speakers=args.min_speakers,
        max_speakers=args.max_speakers,
        diarization_model=args.diarization_model,
        hf_token=args.hf_token,
    )

    # Create outputs
    n8n_output = create_n8n_output(segments, meta)
    standup_summary = summarize_standup(n8n_output)

    # Save all outputs
    speaker_segments_json.write_text(
        json.dumps(segments, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    n8n_output_json.write_text(
        json.dumps(n8n_output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    standup_summary_json.write_text(
        json.dump(standup_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    transcript_txt.write_text(n8n_output["transcript"], encoding="utf-8")
    meta_json.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_srt(segments, srt_file)

    print("[+] Done.")
    print(f"    Speaker segments: {speaker_segments_json}")
    print(f"    n8n output: {n8n_output_json}")
    print(f"    Standup summary: {standup_summary_json}")
    print(f"    Transcript: {transcript_txt}")
    print(f"    SRT: {srt_file}")
    print(f"    Meta: {meta_json}")
    
    # Display speaker summary
    print(f"\n[+] Speaker Summary:")
    for speaker, stats in n8n_output["speaker_statistics"].items():
        print(f"    {speaker}: {stats['turns']} turns, {stats['words']} words, {stats['duration']:.1f}s")


if __name__ == "__main__":
    main()
