.PHONY: help setup install setup-devices run run-gpu transcribe transcribe-gpu setup-cuda clean clean-recordings check-deps list-devices

PROFILE ?=
ARGS ?=
PROFILE_FLAG := $(if $(PROFILE),--profile $(PROFILE),)

help:
	@echo "Available commands:"
	@echo "  make setup           - Set up virtual environment and install dependencies"
	@echo "  make install         - Install dependencies in existing venv"
	@echo "  make setup-devices   - Interactively pick your mic + system-audio devices"
	@echo "  make run             - Record + transcribe with diarization (CPU)"
	@echo "  make run-gpu         - Record + transcribe with diarization (GPU)"
	@echo "  make transcribe      - Transcribe most recent recording only (CPU)"
	@echo "  make transcribe-gpu  - Transcribe most recent recording only (GPU)"
	@echo "  make list-devices    - Raw pactl source listing (debug)"
	@echo "  make check-deps      - Check if dependencies are installed"
	@echo "  make setup-cuda      - Install CUDA dependencies for GPU support"
	@echo "  make clean-recordings - Delete all recordings"
	@echo "  make clean           - Remove the virtual environment"
	@echo ""
	@echo "  Pass PROFILE=<name> to use a non-default device profile."
	@echo "  Pass ARGS=\"...\" to forward extra flags, e.g. ARGS=\"--no-diarize\""

setup:
	@echo "Setting up virtual environment..."
	python3 -m venv .venv
	. .venv/bin/activate && \
	pip install --upgrade pip && \
	pip install -r requirements.txt
	@echo "Setup complete! Run 'make setup-devices' next."

install:
	@echo "Installing dependencies..."
	. .venv/bin/activate && \
	pip install --upgrade pip && \
	pip install -r requirements.txt

setup-devices:
	. .venv/bin/activate && \
	python recorder.py --configure

run:
	. .venv/bin/activate && \
	python recorder.py $(PROFILE_FLAG) \
	  --model large-v3 \
	  --language pt \
	  --device cpu \
	  --compute-type int8 \
	  --min-speakers 2 \
	  --max-speakers 4 \
	  $(ARGS)

run-gpu:
	. .venv/bin/activate && \
	export LD_LIBRARY_PATH="/usr/local/lib/ollama/cuda_v12:$$LD_LIBRARY_PATH" && \
	python recorder.py $(PROFILE_FLAG) \
	  --model large-v3 \
	  --language pt \
	  --device cuda \
	  --compute-type float16 \
	  --min-speakers 2 \
	  --max-speakers 4 \
	  $(ARGS)

transcribe:
	@if [ ! -d "recordings" ]; then echo "No recordings directory found!"; exit 1; fi
	@latest_dir=$$(ls -t recordings/ | head -1); \
	if [ -z "$$latest_dir" ]; then echo "No recordings found!"; exit 1; fi; \
	echo "Processing: recordings/$$latest_dir/mixed.wav"; \
	. .venv/bin/activate && \
	python recorder.py \
	  --transcribe-only recordings/$$latest_dir/mixed.wav \
	  --model large-v3 \
	  --language pt \
	  --device cpu \
	  --compute-type int8 \
	  --min-speakers 2 \
	  --max-speakers 4 \
	  $(ARGS)

transcribe-gpu:
	@if [ ! -d "recordings" ]; then echo "No recordings directory found!"; exit 1; fi
	@latest_dir=$$(ls -t recordings/ | head -1); \
	if [ -z "$$latest_dir" ]; then echo "No recordings found!"; exit 1; fi; \
	echo "Processing: recordings/$$latest_dir/mixed.wav"; \
	. .venv/bin/activate && \
	python recorder.py \
	  --transcribe-only recordings/$$latest_dir/mixed.wav \
	  --model large-v3 \
	  --language pt \
	  --device cuda \
	  --compute-type float16 \
	  --min-speakers 2 \
	  --max-speakers 4 \
	  $(ARGS)

setup-cuda:
	@echo "Installing PyTorch with CUDA support..."
	. .venv/bin/activate && \
	pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 && \
	pip install --upgrade faster-whisper
	@echo "CUDA dependencies installed! Try: make transcribe-gpu"

list-devices:
	@echo "Available audio sources:"
	pactl list short sources

check-deps:
	@echo "Checking dependencies..."
	. .venv/bin/activate && \
	python -c "import faster_whisper; print('faster-whisper: OK')" || echo "faster-whisper: MISSING"
	. .venv/bin/activate && \
	python -c "import whisperx; print('whisperx: OK')" || echo "whisperx: MISSING"
	. .venv/bin/activate && \
	python -c "from pyannote.audio import Pipeline; print('pyannote.audio: OK')" || echo "pyannote.audio: MISSING"

clean:
	@echo "Removing virtual environment..."
	rm -rf .venv

clean-recordings:
	@echo "Removing all recordings..."
	rm -rf recordings/
