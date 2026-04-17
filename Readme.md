# RecordX - AI-Powered Standup Meeting Recorder

**RecordX** is an intelligent audio recording and transcription system designed specifically for standup meetings. It captures both system audio (Discord calls) and microphone input, then uses advanced AI to provide accurate transcription with speaker identification and automated summaries.

## 🎯 Overview

RecordX transforms your daily standup meetings into actionable insights by:
- **Dual-source audio recording** - Captures Discord/system audio and microphone simultaneously
- **AI-powered transcription** - State-of-the-art speech recognition with WhisperX
- **Speaker diarization** - Automatically identifies and labels different speakers
- **Intelligent summaries** - Extracts progress, plans, and blockers automatically
- **Workflow integration** - n8n-ready JSON outputs for automation

## ✨ Key Features

### 🎙️ Advanced Audio Processing
- **Simultaneous dual-source recording**: System audio + microphone
- **Device flexibility**: Supports Bluetooth headphones, USB webcams, and built-in devices
- **Audio optimization**: Automatic mixing, noise reduction, and format conversion
- **Cross-platform**: Optimized for Linux with PulseAudio/PipeWire support

### 🤖 AI-Powered Intelligence
- **WhisperX integration**: Industry-leading speech recognition accuracy
- **Speaker diarization**: Automatic speaker identification and labeling
- **Multi-language support**: Optimized for Portuguese with configurable language options
- **GPU acceleration**: CUDA support for RTX 3060 and compatible GPUs

### 📊 Rich Output Formats
- **Structured JSON**: n8n-compatible for workflow automation
- **Standup summaries**: Automatic extraction of progress, plans, and blockers
- **Multiple formats**: Transcript, SRT subtitles, speaker segments, metadata
- **Speaker analytics**: Talk time, word count, and participation metrics

## 🚀 Quick Start

### Prerequisites
- Linux system with PulseAudio or PipeWire
- Python 3.8+
- FFmpeg installed system-wide
- Optional: NVIDIA GPU with CUDA for faster processing

### Installation

```bash
# Clone and set up the environment
git clone <repository-url>
cd recordx

# Automatic setup (recommended)
make setup

# Or manual setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Basic Usage

#### With Speaker Diarization (Recommended)
```bash
# Run with speaker identification and GPU acceleration
make run-diarized-gpu

# Or CPU-only version
make run-diarized
```

#### Basic Recording (No Speaker Identification)
```bash
# Run with GPU acceleration
make run-gpu

# Or CPU-only version
make run
```

#### Transcribe Existing Recording
```bash
# Transcribe most recent recording with diarization
make transcribe-diarized-gpu

# Or without diarization
make transcribe-gpu
```

## 🛠️ Configuration

### Audio Device Setup

#### List Available Devices
```bash
make list-devices
```

#### Primary Device Configuration
The system is pre-configured for:
- **Monitor Source**: Bluetooth headphones (`bluez_output.44_E1_61_91_CC_47.1.monitor`)
- **Microphone**: HD Pro Webcam (`alsa_input.usb-046d_HD_Pro_Webcam_C920_7ACBEC1F-02.3.analog-stereo`)

#### Fallback Options
```bash
# Use laptop speakers instead of Bluetooth
make run-fallback-bt

# Use laptop microphone instead of webcam
make run-fallback-cam
```

### GPU Acceleration Setup

#### Install CUDA Support
```bash
make setup-cuda
```

#### Manual GPU Configuration
```bash
# Enable GPU acceleration
python standup_recorder_diarized.py \
  --monitor-source bluez_output.44_E1_61_91_CC_47.1.monitor \
  --mic-source alsa_input.usb-046d_HD_Pro_Webcam_C920_7ACBEC1F-02.3.analog-stereo \
  --model large-v3 \
  --language pt \
  --device cuda \
  --compute-type float16 \
  --min-speakers 2 \
  --max-speakers 4
```

## 📁 Output Structure

Each recording session generates a comprehensive set of files in the `recordings/` directory:

```
recordings/standup_YYYYMMDD_HHMMSS/
├── mixed.wav                    # Combined audio file
├── speaker_segments.json        # Speaker-labeled segments
├── n8n_output.json             # Structured automation output
├── standup_summary.json        # Standup-specific analysis
├── transcript.txt              # Human-readable transcript
├── transcript.srt              # Subtitle format with speakers
└── metadata.json               # Processing metadata
```

### Key Output Examples

#### Speaker Segments
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

#### Standup Summary
```json
{
  "meeting_type": "standup",
  "timestamp": "20260416_221042",
  "duration_minutes": 30.1,
  "participants": ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"],
  "overall_summary": {
    "total_progress_points": 8,
    "blockers_identified": 2,
    "blockers": ["API externa está retornando erro 500"],
    "meeting_health": "needs_attention"
  }
}
```

## 🔧 Advanced Configuration

### Command Line Options

#### Core Options
- `--monitor-source`: Pulse/PipeWire monitor source for Discord/system audio
- `--mic-source`: Pulse/PipeWire microphone source
- `--outdir`: Output directory (default: recordings)
- `--model`: WhisperX model (default: large-v3)
- `--language`: Language code (default: pt)
- `--device`: Device (auto/cuda/cpu, default: auto)
- `--compute-type`: Computation type (float16/int8/auto, default: float16)

#### Diarization Options
- `--min-speakers`: Minimum number of speakers (improves accuracy)
- `--max-speakers`: Maximum number of speakers (improves accuracy)
- `--diarization-model`: Diarization model (default: pyannote/speaker-diarization-community-1.0)

#### Additional Options
- `--max-minutes`: Maximum recording duration
- `--skip-transcription`: Record only, don't transcribe
- `--transcribe-only`: Transcribe existing audio file

### Performance Optimization

#### Model Selection
- **large-v3**: Best accuracy, ~8GB VRAM recommended
- **large-v2**: Good accuracy, less VRAM usage
- **base**: Fastest, lower accuracy (for testing)

#### Compute Types
- **float16**: Best performance on RTX 3060
- **int8**: Lower VRAM usage, slight accuracy loss
- **auto**: Automatic selection

## 🔌 Integration & Automation

### n8n Workflow Integration

The `n8n_output.json` is designed for seamless integration with n8n workflows:

#### Sample Workflow
1. **HTTP Request Trigger**: Receive webhook with recording path
2. **Execute Command**: Run transcription script
3. **Read Files**: Parse `n8n_output.json`
4. **Process Data**: Extract speaker summaries
5. **Send Notification**: Post to Slack/Teams with summary

#### Key Data Paths
- Meeting info: `$.meeting_info`
- Speaker turns: `$.speaker_turns[*]`
- Statistics: `$.speaker_statistics`
- Transcript: `$.transcript`

### Custom Integrations

#### Speaker Mapping
After transcription, map speakers to real names:
```json
{
  "SPEAKER_00": "Alice",
  "SPEAKER_01": "Bob", 
  "SPEAKER_02": "Charlie"
}
```

## 🛠️ Maintenance & Troubleshooting

### Common Commands

```bash
# Check dependency installation
make check-deps

# Clean all recordings
make clean-recordings

# Clean virtual environment
make clean

# Test diarization setup
make test-diarization
```

### Common Issues

#### CUDA Out of Memory
```bash
# Use smaller model
--model large-v2

# Use int8 compute type
--compute-type int8

# Fall back to CPU
--device cpu
```

#### Poor Speaker Separation
- Ensure clear audio separation
- Avoid people talking over each other
- Set appropriate speaker count limits
- Use `--min-speakers` and `--max-speakers` for better accuracy

#### Audio Device Issues
```bash
# List all available sources
pactl list short sources

# Test with fallback devices
make run-fallback-bt
make run-fallback-cam
```

## 💻 System Requirements

### Minimum Requirements
- **CPU**: 4+ cores
- **RAM**: 8GB
- **Storage**: 1GB free space
- **OS**: Linux with PulseAudio/PipeWire

### Recommended Configuration
- **GPU**: RTX 3060 6GB+ VRAM
- **CPU**: 6+ cores
- **RAM**: 16GB
- **Storage**: 5GB free space
- **Audio**: USB microphone + Bluetooth headphones

## 📚 Technical Architecture

### Audio Pipeline
1. **Capture**: FFmpeg records dual audio sources
2. **Mix**: Combines system audio and microphone
3. **Process**: Resamples to 16kHz mono for optimal transcription
4. **Transcribe**: WhisperX processes audio with speaker diarization
5. **Analyze**: Extracts standup-specific insights
6. **Output**: Generates multiple format outputs

### AI Models Used
- **WhisperX**: Advanced speech recognition
- **pyannote.audio**: Speaker diarization
- **PyTorch**: Deep learning framework with CUDA support

## 🤝 Contributing

We welcome contributions from the community! Whether you're fixing bugs, adding features, improving documentation, or suggesting enhancements, your input is valuable.

### How to Contribute

1. **Fork the repository** and create your feature branch
2. **Make your changes** following the existing code style and patterns
3. **Test thoroughly** using `make test-diarization` and ensure all tests pass
4. **Document your changes** in the appropriate sections
5. **Submit a pull request** with a clear description of your changes

### Areas for Contribution

- **Audio Processing**: Improve recording quality, add device compatibility
- **AI Models**: Enhance transcription accuracy, add language support
- **User Experience**: Better error handling, UI improvements
- **Documentation**:完善文档, add examples, translate to other languages
- **Integration**: Expand n8n workflows, add new automation options
- **Performance**: Optimize GPU usage, reduce memory footprint

### Getting Started

If you're new to the project, start by:
- Reading through the existing codebase
- Running the application locally
- Checking existing issues for good first contributions
- Joining discussions by creating a issue!

**All contributions are welcome!** Whether it's a small bug fix, documentation improvement, or a major feature enhancement, we appreciate your effort to make RecordX better for everyone.

## 📄 License

This project maintains the same license as the original standup recorder implementation.

---

**RecordX** - Transform your standup meetings into actionable insights with AI-powered transcription and analysis.
