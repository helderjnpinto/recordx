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

from faster_whisper import WhisperModel


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
            f.write(f"{idx}\n{start} --> {end}\n{text}\n\n")


def transcribe_audio(
    audio_path,
    model_name="large-v3",
    device="auto",
    compute_type="float16",
    language="pt",
    beam_size=5,
):
    print(f"[+] Loading model: {model_name} ({device}, {compute_type})")
    print("    (First time may download model - this can take a while)")
    
    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
    except KeyboardInterrupt:
        print("\n[!] Model download interrupted. The audio file is saved.")
        print("    Run again to resume - the model will continue downloading.")
        raise

    print("[+] Transcribing...")
    segments_iter, info = model.transcribe(
        str(audio_path),
        language=language,
        beam_size=beam_size,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        condition_on_previous_text=True,
        word_timestamps=False,
    )

    segments = []
    full_text_parts = []

    for seg in segments_iter:
        item = {
            "start": float(seg.start),
            "end": float(seg.end),
            "text": seg.text.strip(),
        }
        segments.append(item)
        full_text_parts.append(item["text"])

    transcript = "\n".join(full_text_parts).strip()

    meta = {
        "language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
        "duration": getattr(info, "duration", None),
        "duration_after_vad": getattr(info, "duration_after_vad", None),
    }

    return transcript, segments, meta


def summarize_basic(transcript):
    """
    Placeholder local non-LLM summary structure.
    This is intentionally simple for part 1.
    Later you can plug this into n8n or a local LLM.
    """
    lines = [line.strip() for line in transcript.splitlines() if line.strip()]
    excerpt = " ".join(lines[:12])

    summary = {
        "meeting_type": "standup",
        "high_level_summary": excerpt[:1000],
        "notes": [
            "Auto-summary is basic in this first version.",
            "Next step: add per-person extraction, blockers, and capacity detection.",
        ],
    }
    return summary


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
        description="Record Discord/system audio + mic on Linux and transcribe locally with faster-whisper."
    )
    parser.add_argument("--monitor-source", help="Pulse/PipeWire monitor source for Discord/system audio")
    parser.add_argument("--mic-source", help="Pulse/PipeWire microphone source")
    parser.add_argument("--outdir", default="recordings", help="Output directory")
    parser.add_argument("--model", default="large-v3", help="Whisper model name, e.g. large-v3")
    parser.add_argument("--language", default="pt", help="Language code, e.g. pt or en")
    parser.add_argument("--device", default="auto", help="Whisper device: auto/cuda/cpu")
    parser.add_argument("--compute-type", default="float16", help="float16/int8/auto")
    parser.add_argument("--max-minutes", type=int, default=None, help="Optional hard stop for recording")
    parser.add_argument("--skip-transcription", action="store_true", help="Only record audio, do not transcribe")
    parser.add_argument("--transcribe-only", help="Only transcribe existing audio file (path to wav file)")
    args = parser.parse_args()

    # Validate arguments
    if not args.transcribe_only:
        if not args.monitor_source or not args.mic_source:
            print("ERROR: --monitor-source and --mic-source are required for recording")
            sys.exit(1)

    # Handle transcribe-only mode
    if args.transcribe_only:
        audio_path = Path(args.transcribe_only)
        if not audio_path.exists():
            print(f"ERROR: Audio file not found: {audio_path}")
            sys.exit(1)
        
        print(f"[+] Transcribing existing file: {audio_path}")
        transcript, segments, meta = transcribe_audio(
            audio_path,
            model_name=args.model,
            device=args.device,
            compute_type=args.compute_type,
            language=args.language,
        )
        
        # Save transcription
        output_dir = audio_path.parent
        with open(output_dir / "transcript.txt", "w", encoding="utf-8") as f:
            f.write(transcript)
        with open(output_dir / "segments.json", "w", encoding="utf-8") as f:
            json.dump(segments, f, indent=2, ensure_ascii=False)
        with open(output_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        
        print(f"[+] Transcription saved to: {output_dir}")
        return

    ensure_ffmpeg()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    slug = timestamp_slug()
    session_dir = outdir / f"standup_{slug}"
    session_dir.mkdir(parents=True, exist_ok=True)

    mixed_wav = session_dir / "mixed.wav"
    transcript_txt = session_dir / "transcript.txt"
    segments_json = session_dir / "segments.json"
    srt_file = session_dir / "transcript.srt"
    meta_json = session_dir / "meta.json"
    basic_summary_json = session_dir / "basic_summary.json"

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

    transcript, segments, meta = transcribe_audio(
        audio_path=mixed_wav,
        model_name=args.model,
        device=args.device,
        compute_type=args.compute_type,
        language=args.language,
        beam_size=5,
    )

    transcript_txt.write_text(transcript, encoding="utf-8")
    segments_json.write_text(
        json.dumps(segments, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    meta_json.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_srt(segments, srt_file)

    basic_summary = summarize_basic(transcript)
    basic_summary_json.write_text(
        json.dumps(basic_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("[+] Done.")
    print(f"    Transcript: {transcript_txt}")
    print(f"    Segments:   {segments_json}")
    print(f"    SRT:        {srt_file}")
    print(f"    Meta:       {meta_json}")
    print(f"    Summary:    {basic_summary_json}")


if __name__ == "__main__":
    main()