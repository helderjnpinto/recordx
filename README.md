# RecordX

RecordX records mic + system audio on Linux, transcribes it with WhisperX, and
identifies speakers with pyannote diarization. It produces one `output.json`
per session, shaped for n8n / automation workflows.

## Features

- Dual-source recording (system audio + microphone), mixed and resampled for Whisper
- WhisperX transcription with pyannote speaker diarization (on by default)
- Interactive device setup — works on any machine, not tied to one PC's hardware
- Loud, actionable errors if diarization can't run (never a silent single-speaker fallback)
- End-of-recording prompt to name detected speakers
- Stop a recording with Enter or Ctrl+C
- One output file per session: `output.json` (n8n-style) + `mixed.wav`

## Prerequisites

- Linux with PulseAudio or PipeWire (`pactl`)
- Python 3.8+
- FFmpeg installed system-wide
- Optional: NVIDIA GPU with CUDA

## Installation

```bash
make setup
```

Add a Hugging Face token to `.env` (see `.env.example`) — required for diarization.
It must have accepted the license for the gated diarization model; if not, the
tool will tell you the exact URL to visit when it fails.

## Device setup

Devices are no longer hardcoded — pick yours interactively:

```bash
make setup-devices
```

This lists your real `pactl` sources, lets you choose a microphone and a
system-audio monitor source, and saves the choice as a profile in `config.json`
(gitignored — see `config.example.json` for the schema). You can save multiple
profiles (e.g. one for Bluetooth headphones, one for laptop speakers as a
fallback) and select one per run with `--profile <name>` / `make run PROFILE=<name>`.

Re-run `make setup-devices` any time your devices change.

## Usage

```bash
make run              # record + transcribe with diarization (CPU)
make run-gpu           # same, GPU
make transcribe        # transcribe the most recent recording only (CPU)
make transcribe-gpu     # same, GPU
```

Pass extra flags with `ARGS="..."`, e.g. `make run ARGS="--no-diarize"`.
Pass a non-default device profile with `PROFILE=<name>`.

### Stopping a recording

Press **Enter** to stop and finalize the recording. Ctrl+C still works as a
fallback/emergency stop.

### Speaker naming

After a diarized recording with more than one detected speaker, RecordX shows
each speaker's talk time and a text sample, then asks you to type a real name
for each. Names propagate into `output.json`'s transcript, turns, and stats.
Skip this with `--no-name-prompt`; it's also auto-skipped for non-interactive runs.

### Diarization

Diarization is on by default. If it fails to load (most commonly: your HF
token hasn't accepted the gated model's license yet), the tool stops with an
error naming the exact model URL to visit — it never silently falls back to a
single `SPEAKER_00` label. Use `--no-diarize` to intentionally skip diarization.

Useful flags: `--min-speakers N`, `--max-speakers N`, `--diarization-model NAME`, `--hf-token TOKEN`.

## Output

Each session writes to `recordings/standup_<timestamp>/`:

```
mixed.wav      # the recorded audio
output.json    # everything else
```

`output.json` shape:

```json
{
  "meeting_info": {
    "timestamp": "20260908_092957",
    "duration": 1800.5,
    "language": "pt",
    "total_speakers": 3,
    "total_turns": 45,
    "total_words": 678
  },
  "transcript": "[Alice] Adicionei logs para falhas nas transações.\n[Bob] Hoje vou começar...",
  "speaker_turns": [
    {"speaker": "Alice", "start": 0.0, "end": 2.28, "duration": 2.28, "text": "...", "word_count": 6}
  ],
  "speaker_statistics": {
    "Alice": {"turns": 15, "words": 234, "duration": 120.5}
  },
  "metadata": {
    "whisper_model": "large-v3",
    "diarization_model": "pyannote/speaker-diarization-community-1",
    "srt": [{"index": 1, "start": "00:00:00,000", "end": "00:00:02,280", "speaker": "Alice", "text": "..."}]
  }
}
```

### n8n integration

`output.json` is the integration point:
- Meeting info: `$.meeting_info`
- Speaker turns: `$.speaker_turns[*]`
- Statistics: `$.speaker_statistics`
- Transcript: `$.transcript`
- SRT cues: `$.metadata.srt`

Sample workflow: HTTP trigger → run `recorder.py` → read `output.json` →
notify Slack/Teams with the summary.

### Old recordings

Sessions recorded before this refactor keep their original multi-file layout
(`metadata.json`, `speaker_segments.json`, `standup_summary.json`, `transcript.txt`,
`transcript.srt`) — only new or re-transcribed runs produce `output.json`.

## Troubleshooting

**Diarization fails to load** — visit the model URL printed in the error,
log in with the account that owns your `HF_TOKEN`, and click "Agree and
access repository", then retry.

> **This is a repository access gate, not a token-validity problem.** A
> perfectly valid `HF_TOKEN` will still get a 403/404 from
> `Pipeline.from_pretrained(...)` if that account hasn't been granted access
> to the specific gated model repo yet — regenerating the token or double
> checking `.env` won't fix it. Access after clicking "Agree" is also not
> always instant; if it fails immediately after accepting, wait a minute and
> retry before troubleshooting anything else. (This project's own default
> diarization model id was briefly wrong — `pyannote/speaker-diarization-community-1.0`
> instead of the real `pyannote/speaker-diarization-community-1` — which looked
> identical to an access problem in the error output; double-check the model
> id in the error message actually matches a real HF repo before assuming
> it's a permissions issue.)

**CUDA out of memory** — use `--model large-v2`, `--compute-type int8`, or `--device cpu`.

**Poor speaker separation** — set `--min-speakers`/`--max-speakers` to the
actual meeting size, and avoid people talking over each other.

**Audio device issues** — `make list-devices` shows the raw `pactl` listing;
`make setup-devices` re-runs the interactive picker.

## System requirements

- Minimum: 4+ CPU cores, 8GB RAM, 1GB storage
- Recommended: NVIDIA GPU with 6GB+ VRAM, 6+ CPU cores, 16GB RAM

## License

See repository license.
