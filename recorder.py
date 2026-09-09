#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import audio
import config
import output
import transcribe


def finish(segments, meta, session_dir, recording_started_at, args):
    """Shared tail for both the fresh-recording and --transcribe-only paths."""
    mapping = output.prompt_speaker_names(segments, no_prompt=args.no_name_prompt)
    segments = output.apply_speaker_names(segments, mapping)

    result = output.create_output(segments, meta, recording_started_at)

    output_json = session_dir / "output.json"
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[+] Done. Output: {output_json}")
    print("[+] Speaker summary:")
    for speaker, stats in result["speaker_statistics"].items():
        print(f"    {speaker}: {stats['turns']} turns, {stats['words']} words, {stats['duration']:.1f}s")


def main():
    parser = argparse.ArgumentParser(
        description="Record mic + system audio on Linux and transcribe with WhisperX + pyannote diarization."
    )
    parser.add_argument("--configure", action="store_true", help="Run interactive device setup and exit")
    parser.add_argument("--profile", default=None, help="Use this saved device profile instead of the active one")
    parser.add_argument("--outdir", default="recordings", help="Output directory")
    parser.add_argument("--model", default="large-v3", help="WhisperX model name, e.g. large-v3")
    parser.add_argument("--language", default="pt", help="Language code, e.g. pt or en")
    parser.add_argument("--device", default="auto", help="Device: auto/cuda/cpu")
    parser.add_argument("--compute-type", default="float16", help="float16/int8/auto")
    parser.add_argument("--max-minutes", type=int, default=None, help="Optional hard stop for recording")
    parser.add_argument("--skip-transcription", action="store_true", help="Only record audio, do not transcribe")
    parser.add_argument("--transcribe-only", help="Only transcribe existing audio file (path to wav file)")

    parser.add_argument("--diarize", dest="diarize", action="store_true", default=True,
                         help="Enable speaker diarization (default)")
    parser.add_argument("--no-diarize", dest="diarize", action="store_false",
                         help="Skip diarization, produce single-speaker output")
    parser.add_argument("--min-speakers", type=int, default=None)
    parser.add_argument("--max-speakers", type=int, default=None)
    parser.add_argument("--diarization-model", default=transcribe.DEFAULT_DIARIZATION_MODEL)
    parser.add_argument("--hf-token", default=None, help="HuggingFace token for gated diarization model")

    parser.add_argument("--no-name-prompt", action="store_true", help="Skip the end-of-recording speaker naming prompt")

    args = parser.parse_args()

    if args.configure:
        config.interactive_configure(config.load_config())
        return

    if args.device == "auto":
        device = transcribe.detect_device()
    else:
        device = args.device

    def run_transcription(audio_path):
        try:
            return transcribe.transcribe_with_diarization(
                audio_path,
                model_name=args.model,
                device=device,
                compute_type=args.compute_type,
                language=args.language,
                min_speakers=args.min_speakers,
                max_speakers=args.max_speakers,
                diarization_model=args.diarization_model,
                hf_token=args.hf_token,
                diarize=args.diarize,
            )
        except transcribe.DiarizationError as e:
            print(f"\n[!] Diarization failed:\n    {e}\n")
            print(f"[i] Audio is safe on disk at: {audio_path}")
            print(f"    Re-run once fixed: python recorder.py --transcribe-only {audio_path} --diarize")
            print(f"    Or skip diarization: python recorder.py --transcribe-only {audio_path} --no-diarize")
            sys.exit(1)

    if args.transcribe_only:
        audio_path = Path(args.transcribe_only)
        if not audio_path.exists():
            print(f"ERROR: Audio file not found: {audio_path}")
            sys.exit(1)

        print(f"[+] Transcribing existing file: {audio_path}")
        segments, meta = run_transcription(audio_path)
        finish(segments, meta, audio_path.parent, audio.timestamp_slug(), args)
        return

    cfg = config.ensure_config(args.profile)
    profile = config.get_profile(cfg, args.profile)

    audio.ensure_ffmpeg()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    slug = audio.timestamp_slug()
    session_dir = outdir / f"standup_{slug}"
    session_dir.mkdir(parents=True, exist_ok=True)
    mixed_wav = session_dir / "mixed.wav"

    ffmpeg_cmd = audio.build_ffmpeg_command(
        monitor_source=profile["monitor_source"],
        mic_source=profile["mic_source"],
        output_wav=mixed_wav,
        sample_rate=16000,
    )

    audio.record_until_stopped(ffmpeg_cmd, max_minutes=args.max_minutes)

    if not mixed_wav.exists() or mixed_wav.stat().st_size == 0:
        print("ERROR: recording file was not created or is empty.")
        sys.exit(1)

    print(f"[+] Audio saved: {mixed_wav}")

    if args.skip_transcription:
        print("[+] Recording complete. Transcription skipped.")
        return

    print("[+] Starting transcription...")
    segments, meta = run_transcription(mixed_wav)
    finish(segments, meta, session_dir, slug, args)


if __name__ == "__main__":
    main()
