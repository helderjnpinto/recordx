# Standup Recorder with Speaker Diarization

Enhanced version of the standup recorder using **WhisperX + pyannote** for accurate speaker diarization and transcription optimized for Discord calls.

## What's New

- **Speaker Diarization**: Automatically identifies and labels different speakers
- **WhisperX Integration**: Uses WhisperX for improved transcription accuracy
- **n8n-Ready Output**: Structured JSON format for workflow automation
- **GPU Optimization**: Automatic CUDA detection and optimization for RTX 3060
- **Standup-Specific Summaries**: Extracts progress, plans, and blockers automatically

## Installation

```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install whisperx pyannote.audio

# Verify installation
python standup_recorder_diarized.py --help
```

## Quick Start

### Basic Recording with Diarization

```bash
python standup_recorder_diarized.py \
  --monitor-source bluez_output.44_E1_61_91_CC_47.1.monitor \
  --mic-source alsa_input.usb-046d_HD_Pro_Webcam_C920_7ACBEC1F-02.3.analog-stereo \
  --model large-v3 \
  --language pt \
  --device cuda
```

### With Known Number of Speakers (Recommended)

```bash
python standup_recorder_diarized.py \
  --monitor-source bluez_output.44_E1_61_91_CC_47.1.monitor \
  --mic-source alsa_input.usb-046d_HD_Pro_Webcam_C920_7ACBEC1F-02.3.analog-stereo \
  --model large-v3 \
  --language pt \
  --device cuda \
  --min-speakers 2 \
  --max-speakers 4
```

### Transcribe Existing Recording

```bash
python standup_recorder_diarized.py \
  --transcribe-only recordings/standup_20260416_221042/mixed.wav \
  --model large-v3 \
  --language pt \
  --device cuda \
  --min-speakers 2 \
  --max-speakers 4
```

## Command Line Options

### Core Options
- `--monitor-source`: Pulse/PipeWire monitor source for Discord/system audio
- `--mic-source`: Pulse/PipeWire microphone source
- `--outdir`: Output directory (default: recordings)
- `--model`: WhisperX model (default: large-v3)
- `--language`: Language code (default: pt)
- `--device`: Device (auto/cuda/cpu, default: auto)
- `--compute-type`: Computation type (float16/int8/auto, default: float16)

### Diarization Options
- `--min-speakers`: Minimum number of speakers (helps accuracy)
- `--max-speakers`: Maximum number of speakers (helps accuracy)
- `--diarization-model`: Diarization model (default: pyannote/speaker-diarization-community-1.0)

### Other Options
- `--max-minutes`: Maximum recording duration
- `--skip-transcription`: Only record, don't transcribe
- `--transcribe-only`: Transcribe existing audio file

## Output Files

Each recording session creates multiple output files:

### Core Files
- `speaker_segments.json`: Raw speaker-labeled segments
- `n8n_output.json`: Structured output for automation
- `standup_summary.json`: Standup-specific analysis
- `transcript.txt`: Human-readable transcript
- `transcript.srt`: Subtitle format with speaker labels
- `metadata.json`: Processing metadata

### Example Speaker Segments Output

```json
[
  {
    "speaker": "SPEAKER_00",
    "start": 0.00,
    "end": 2.28,
    "text": "Adicionei logs para falhas nas transações."
  },
  {
    "speaker": "SPEAKER_01",
    "start": 2.96,
    "end": 6.40,
    "text": "Hoje vou começar a integrar o webhook dos providers externos."
  }
]
```

### Example n8n Output

```json
{
  "meeting_info": {
    "timestamp": "20260416_221042",
    "duration": 1800.5,
    "language": "pt",
    "total_speakers": 3,
    "total_turns": 45,
    "total_words": 678
  },
  "transcript": "[SPEAKER_00] Adicionei logs para falhas nas transações.\n[SPEAKER_01] Hoje vou começar...",
  "speaker_turns": [...],
  "speaker_statistics": {
    "SPEAKER_00": {"turns": 15, "words": 234, "duration": 120.5},
    "SPEAKER_01": {"turns": 20, "words": 312, "duration": 180.2},
    "SPEAKER_02": {"turns": 10, "words": 132, "duration": 89.8}
  },
  "metadata": {...}
}
```

### Example Standup Summary

```json
{
  "meeting_type": "standup",
  "timestamp": "20260416_221042",
  "duration_minutes": 30.1,
  "participants": ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"],
  "speaker_summaries": {
    "SPEAKER_00": {
      "speaker": "SPEAKER_00",
      "total_talk_time": 120.5,
      "word_count": 234,
      "key_points": {
        "progress": ["Adicionei logs para falhas nas transações"],
        "plans": ["Vou testar o fluxo de integração"],
        "blockers": []
      }
    }
  },
  "overall_summary": {
    "total_progress_points": 8,
    "blockers_identified": 2,
    "blockers": ["API externa está retornando erro 500"],
    "meeting_health": "needs_attention"
  }
}
```

## Performance Optimization

### For RTX 3060

The script automatically detects and optimizes for CUDA:

```bash
# Automatic GPU detection
python standup_recorder_diarized.py --device auto

# Explicitly use GPU
python standup_recorder_diarized.py --device cuda
```

### Model Selection

- **large-v3**: Best accuracy, ~8GB VRAM recommended
- **large-v2**: Good accuracy, less VRAM usage
- **base**: Fastest, lower accuracy (for testing)

### Compute Types

- **float16**: Best performance on RTX 3060
- **int8**: Lower VRAM usage, slight accuracy loss
- **auto**: Automatic selection

## Speaker Accuracy Tips

### 1. Set Speaker Count
Always set `--min-speakers` and `--max-speakers` when you know the meeting size:

```bash
# For 2-3 person meetings
--min-speakers 2 --max-speakers 3

# For larger meetings
--min-speakers 3 --max-speakers 8
```

### 2. Audio Quality
- Use good quality microphone
- Avoid background noise when possible
- Ensure consistent volume levels

### 3. Speaker Mapping
After transcription, map speakers to real names:

```json
{
  "SPEAKER_00": "Yari",
  "SPEAKER_01": "Alice", 
  "SPEAKER_02": "Bob"
}
```

## n8n Integration

The `n8n_output.json` is designed for easy integration with n8n workflows:

### Sample n8n Workflow

1. **HTTP Request Trigger**: Receive webhook with recording path
2. **Execute Command**: Run transcription script
3. **Read Files**: Parse `n8n_output.json`
4. **Process Data**: Extract speaker summaries
5. **Send Notification**: Post to Slack/Teams with summary

### Key Data Paths

- Meeting info: `$.meeting_info`
- Speaker turns: `$.speaker_turns[*]`
- Statistics: `$.speaker_statistics`
- Transcript: `$.transcript`

## Troubleshooting

### Common Issues

1. **CUDA Out of Memory**
   ```bash
   # Use smaller model
   --model large-v2
   
   # Use int8 compute type
   --compute-type int8
   
   # Fall back to CPU
   --device cpu
   ```

2. **Diarization Fails**
   ```bash
   # Check audio quality
   ffmpeg -i input.wav -af "volumedetect" -f null -
   
   # Try with explicit speaker count
   --min-speakers 2 --max-speakers 4
   ```

3. **Poor Speaker Separation**
   - Ensure clear audio separation
   - Avoid people talking over each other
   - Set appropriate speaker count limits

### Fallback Mode

If diarization fails, the script automatically falls back to basic transcription with a single speaker label.

## Advanced Usage

### Custom Diarization Models

```bash
# Use different diarization model
--diarization-model pyannote/speaker-diarization-3.1
```

### Batch Processing

```bash
#!/bin/bash
for file in recordings/*/mixed.wav; do
  python standup_recorder_diarized.py \
    --transcribe-only "$file" \
    --model large-v3 \
    --language pt \
    --device cuda \
    --min-speakers 2 \
    --max-speakers 4
done
```

### Real-time Processing

For near real-time processing, use shorter recordings:

```bash
# 5-minute chunks
--max-minutes 5
```

## Comparison: Original vs Diarized

| Feature | Original | Diarized Version |
|---------|----------|-------------------|
| Transcription | faster-whisper | WhisperX |
| Speaker Labels | None | pyannote diarization |
| Output Format | Basic segments | n8n-ready JSON |
| Summaries | Basic | Standup-specific |
| GPU Support | Basic | Optimized |
| Speaker Stats | None | Detailed |

## Hardware Requirements

### Minimum
- CPU: 4+ cores
- RAM: 8GB
- Storage: 1GB free space

### Recommended (RTX 3060)
- GPU: RTX 3060 6GB+ VRAM
- CPU: 6+ cores
- RAM: 16GB
- Storage: 5GB free space

## License

This enhanced version maintains the same license as the original project.
