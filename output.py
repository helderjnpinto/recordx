#!/usr/bin/env python3
"""Builds the single output.json (n8n-style) and the end-of-recording speaker naming prompt."""
import sys


def _fmt_srt_ts(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _build_srt_cues(segments):
    cues = []
    for idx, seg in enumerate(segments, start=1):
        cues.append({
            "index": idx,
            "start": _fmt_srt_ts(seg["start"]),
            "end": _fmt_srt_ts(seg["end"]),
            "speaker": seg.get("speaker", "UNKNOWN"),
            "text": seg["text"].strip(),
        })
    return cues


def create_output(segments, meta, recording_started_at):
    """Build the single n8n-style output document for a session."""
    transcript = "\n".join(f"[{seg['speaker']}] {seg['text']}" for seg in segments)

    speaker_turns = [
        {
            "speaker": seg["speaker"],
            "start": seg["start"],
            "end": seg["end"],
            "duration": seg["end"] - seg["start"],
            "text": seg["text"],
            "word_count": len(seg["text"].split()),
        }
        for seg in segments
    ]

    speaker_stats = {}
    for seg in segments:
        stats = speaker_stats.setdefault(seg["speaker"], {"turns": 0, "words": 0, "duration": 0.0})
        stats["turns"] += 1
        stats["words"] += len(seg["text"].split())
        stats["duration"] += seg["end"] - seg["start"]

    full_meta = dict(meta)
    full_meta["srt"] = _build_srt_cues(segments)

    return {
        "meeting_info": {
            "timestamp": recording_started_at,
            "duration": meta.get("duration", 0),
            "language": meta.get("language"),
            "total_speakers": len(speaker_stats),
            "total_turns": len(segments),
            "total_words": sum(t["word_count"] for t in speaker_turns),
        },
        "transcript": transcript,
        "speaker_turns": speaker_turns,
        "speaker_statistics": speaker_stats,
        "metadata": full_meta,
    }


def prompt_speaker_names(segments, no_prompt=False):
    """
    Ask the user to map SPEAKER_XX labels to real names. Returns {old: new}
    for renamed speakers only. Auto-skips for non-TTY, --no-name-prompt, or
    a single-speaker session (nothing to disambiguate).
    """
    speakers = sorted(set(seg["speaker"] for seg in segments))
    if no_prompt or not sys.stdin.isatty() or len(speakers) <= 1:
        return {}

    stats = {}
    samples = {}
    for seg in segments:
        s = stats.setdefault(seg["speaker"], {"duration": 0.0, "turns": 0})
        s["duration"] += seg["end"] - seg["start"]
        s["turns"] += 1
        samples.setdefault(seg["speaker"], []).append(seg["text"])

    ordered = sorted(speakers, key=lambda sp: stats[sp]["duration"], reverse=True)

    print("\n[?] Who was speaking? Press Enter to keep a label as-is.")
    used_names = set()
    mapping = {}
    for speaker in ordered:
        sample = " ".join(samples[speaker][:2])[:150]
        print(f"\n  {speaker}: {stats[speaker]['duration']:.0f}s talk time, {stats[speaker]['turns']} turns")
        if sample:
            print(f"    sample: \"{sample}\"")
        while True:
            name = input(f"  Name for {speaker} (Enter to keep as-is): ").strip()
            if not name:
                break
            if name in used_names:
                print(f"    '{name}' was already used for another speaker, pick a different name.")
                continue
            used_names.add(name)
            mapping[speaker] = name
            break

    return mapping


def apply_speaker_names(segments, mapping):
    if not mapping:
        return segments
    for seg in segments:
        seg["speaker"] = mapping.get(seg["speaker"], seg["speaker"])
    return segments
