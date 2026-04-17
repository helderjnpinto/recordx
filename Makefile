.PHONY: help install setup run run-fallback-bt run-fallback-cam run-gpu transcribe transcribe-gpu setup-cuda clean clean-recordings check-deps list-devices run-diarized run-diarized-gpu transcribe-diarized transcribe-diarized-gpu test-diarization

# Default target
help:
	@echo "Available commands:"
	@echo "  make setup      - Set up virtual environment and install dependencies"
	@echo "  make install    - Install dependencies in existing venv"
	@echo "  make run        - Run with primary devices (HD Pro Webcam + Bluetooth)"
	@echo "  make run-fallback-bt - Run with laptop speakers (fallback for Bluetooth)"
	@echo "  make run-fallback-cam - Run with laptop mic (fallback for HD Pro Webcam)"
	@echo "  make run-gpu     - Run with GPU for faster transcription"
	@echo "  make transcribe  - Transcribe most recent recording only"
	@echo "  make transcribe-gpu - Transcribe with GPU (much faster)"
	@echo "  make run-diarized - Run with speaker diarization (CPU)"
	@echo "  make run-diarized-gpu - Run with speaker diarization (GPU)"
	@echo "  make transcribe-diarized - Transcribe most recent with diarization (CPU)"
	@echo "  make transcribe-diarized-gpu - Transcribe most recent with diarization (GPU)"
	@echo "  make test-diarization - Test diarization setup"
	@echo "  make setup-cuda  - Install CUDA dependencies for GPU support"
	@echo "  make clean-recordings - Delete all recordings and transcripts"
	@echo "  make list-devices - List available audio devices"
	@echo "  make check-deps - Check if dependencies are installed"
	@echo "  make clean      - Clean virtual environment"
	@echo "  make help       - Show this help message"

# Setup virtual environment and install dependencies
setup:
	@echo "Setting up virtual environment..."
	python3 -m venv .venv
	@echo "Activating virtual environment..."
	. .venv/bin/activate && \
	pip install --upgrade pip && \
	pip install -r requirements.txt
	@echo "Setup complete! Use 'source .venv/bin/activate' to activate the environment."

# Install dependencies in existing virtual environment
install:
	@echo "Installing dependencies..."
	. .venv/bin/activate && \
	pip install --upgrade pip && \
	pip install -r requirements.txt
	@echo "Dependencies installed!"

# Run with primary devices (HD Pro Webcam + Bluetooth headphones)
run:
	@echo "Running with primary devices: HD Pro Webcam + Bluetooth headphones"
	. .venv/bin/activate && \
	python standup_recorder.py \
	  --monitor-source bluez_output.44_E1_61_91_CC_47.1.monitor \
	  --mic-source alsa_input.usb-046d_HD_Pro_Webcam_C920_7ACBEC1F-02.3.analog-stereo \
	  --model large-v3 \
	  --language pt \
	  --device cpu \
	  --compute-type int8

# Run with fallback for Bluetooth (use laptop speakers)
run-fallback-bt:
	@echo "Running with fallback: HD Pro Webcam + Laptop speakers"
	. .venv/bin/activate && \
	python standup_recorder.py \
	  --monitor-source alsa_output.pci-0000_05_00.6.3.analog-stereo.monitor \
	  --mic-source alsa_input.usb-046d_HD_Pro_Webcam_C920_7ACBEC1F-02.3.analog-stereo \
	  --model large-v3 \
	  --language pt \
	  --device cpu \
	  --compute-type int8

# Run with fallback for HD Pro Webcam (use laptop mic)
run-fallback-cam:
	@echo "Running with fallback: Laptop mic + Bluetooth headphones"
	. .venv/bin/activate && \
	python standup_recorder.py \
	  --monitor-source bluez_output.44_E1_61_91_CC_47.1.monitor \
	  --mic-source alsa_input.pci-0000_05_00.6.3.analog-stereo \
	  --model large-v3 \
	  --language pt \
	  --device cpu \
	  --compute-type int8

# Run with GPU for faster transcription
run-gpu:
	@echo "Running with primary devices: HD Pro Webcam + Bluetooth (GPU transcription)"
	. .venv/bin/activate && \
	python standup_recorder.py \
	  --monitor-source bluez_output.44_E1_61_91_CC_47.1.monitor \
	  --mic-source alsa_input.usb-046d_HD_Pro_Webcam_C920_7ACBEC1F-02.3.analog-stereo \
	  --model large-v3 \
	  --language pt \
	  --device cuda \
	  --compute-type float16

# Transcribe most recent recording only
transcribe:
	@echo "Transcribing most recent recording..."
	@if [ ! -d "recordings" ]; then echo "No recordings directory found!"; exit 1; fi
	@latest_dir=$$(ls -t recordings/ | head -1); \
	if [ -z "$$latest_dir" ]; then echo "No recordings found!"; exit 1; fi; \
	echo "Processing: recordings/$$latest_dir/mixed.wav"; \
	. .venv/bin/activate && \
	python standup_recorder.py \
	  --transcribe-only recordings/$$latest_dir/mixed.wav \
	  --model large-v3 \
	  --language pt \
	  --device cpu \
	  --compute-type int8

# Transcribe most recent recording with GPU (much faster)
transcribe-gpu:
	@echo "Transcribing most recent recording with GPU..."
	@if [ ! -d "recordings" ]; then echo "No recordings directory found!"; exit 1; fi
	@latest_dir=$$(ls -t recordings/ | head -1); \
	if [ -z "$$latest_dir" ]; then echo "No recordings found!"; exit 1; fi; \
	echo "Processing: recordings/$$latest_dir/mixed.wav"; \
	. .venv/bin/activate && \
	python standup_recorder.py \
	  --transcribe-only recordings/$$latest_dir/mixed.wav \
	  --model large-v3 \
	  --language pt \
	  --device cuda \
	  --compute-type float16

# Install CUDA dependencies for GPU support
setup-cuda:
	@echo "Installing PyTorch with CUDA support..."
	. .venv/bin/activate && \
	pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 && \
	pip install --upgrade faster-whisper
	@echo "CUDA dependencies installed! Try: make transcribe-gpu"

# List available audio devices
list-devices:
	@echo "Available audio sources:"
	pactl list short sources

# Check if dependencies are installed
check-deps:
	@echo "Checking dependencies..."
	. .venv/bin/activate && \
	python -c "import faster_whisper; print('faster-whisper: OK')" || echo "faster-whisper: MISSING"

# Clean virtual environment
clean:
	@echo "Removing virtual environment..."
	rm -rf .venv
	@echo "Virtual environment removed!"

# Run with speaker diarization (CPU)
run-diarized:
	@echo "Running with speaker diarization: HD Pro Webcam + Bluetooth (CPU)"
	. .venv/bin/activate && \
	python standup_recorder_diarized.py \
	  --monitor-source bluez_output.44_E1_61_91_CC_47.1.monitor \
	  --mic-source alsa_input.usb-046d_HD_Pro_Webcam_C920_7ACBEC1F-02.3.analog-stereo \
	  --model large-v3 \
	  --language pt \
	  --device cpu \
	  --compute-type int8 \
	  --min-speakers 2 \
	  --max-speakers 4

# Run with speaker diarization (GPU)
run-diarized-gpu:
	@echo "Running with speaker diarization: HD Pro Webcam + Bluetooth (GPU)"
	. .venv/bin/activate && \
	python standup_recorder_diarized.py \
	  --monitor-source bluez_output.44_E1_61_91_CC_47.1.monitor \
	  --mic-source alsa_input.usb-046d_HD_Pro_Webcam_C920_7ACBEC1F-02.3.analog-stereo \
	  --model large-v3 \
	  --language pt \
	  --device cuda \
	  --compute-type float16 \
	  --min-speakers 2 \
	  --max-speakers 4

# Transcribe most recent recording with diarization (CPU)
transcribe-diarized:
	@echo "Transcribing most recent recording with diarization (CPU)..."
	@if [ ! -d "recordings" ]; then echo "No recordings directory found!"; exit 1; fi
	@latest_dir=$$(ls -t recordings/ | head -1); \
	if [ -z "$$latest_dir" ]; then echo "No recordings found!"; exit 1; fi; \
	echo "Processing: recordings/$$latest_dir/mixed.wav"; \
	. .venv/bin/activate && \
	python standup_recorder_diarized.py \
	  --transcribe-only recordings/$$latest_dir/mixed.wav \
	  --model large-v3 \
	  --language pt \
	  --device cpu \
	  --compute-type int8 \
	  --min-speakers 2 \
	  --max-speakers 4

# Transcribe most recent recording with diarization (GPU)
transcribe-diarized-gpu:
	@echo "Transcribing most recent recording with diarization (GPU)..."
	@if [ ! -d "recordings" ]; then echo "No recordings directory found!"; exit 1; fi
	@latest_dir=$$(ls -t recordings/ | head -1); \
	if [ -z "$$latest_dir" ]; then echo "No recordings found!"; exit 1; fi; \
	echo "Processing: recordings/$$latest_dir/mixed.wav"; \
	. .venv/bin/activate && \
	python standup_recorder_diarized.py \
	  --transcribe-only recordings/$$latest_dir/mixed.wav \
	  --model large-v3 \
	  --language pt \
	  --device cuda \
	  --compute-type float16 \
	  --min-speakers 2 \
	  --max-speakers 4

# Test diarization setup
test-diarization:
	@echo "Testing diarization setup..."
	. .venv/bin/activate && \
	python test_diarization.py

# Clean all recordings and transcripts
clean-recordings:
	@echo "Removing all recordings and transcripts..."
	rm -rf recordings/
	@echo "All recordings deleted!"
