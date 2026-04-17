#!/usr/bin/env python3
"""
Test script for WhisperX + pyannote diarization setup
"""
import sys
import torch
import warnings

warnings.filterwarnings("ignore")

def test_imports():
    """Test if all required packages can be imported"""
    print("[+] Testing imports...")
    
    try:
        import whisperx
        print("    whisperx: OK")
    except ImportError as e:
        print(f"    whisperx: FAILED - {e}")
        return False
    
    try:
        from pyannote.audio import Pipeline
        print("    pyannote.audio: OK")
    except ImportError as e:
        print(f"    pyannote.audio: FAILED - {e}")
        return False
    
    return True


def test_cuda():
    """Test CUDA availability"""
    print("[+] Testing CUDA...")
    
    if torch.cuda.is_available():
        print(f"    CUDA available: YES")
        print(f"    Device: {torch.cuda.get_device_name()}")
        print(f"    VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GB")
        return True
    else:
        print("    CUDA available: NO")
        print("    Will use CPU (slower)")
        return False


def test_whisperx():
    """Test WhisperX model loading"""
    print("[+] Testing WhisperX...")
    
    try:
        import whisperx
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Try loading a small model for testing
        print("    Loading tiny model (for testing)...")
        model = whisperx.load_model("tiny", device=device, compute_type="float16")
        print("    WhisperX: OK")
        return True
    except Exception as e:
        print(f"    WhisperX: FAILED - {e}")
        return False


def test_pyannote():
    """Test pyannote pipeline loading"""
    print("[+] Testing pyannote...")
    
    try:
        from pyannote.audio import Pipeline
        
        print("    Loading diarization pipeline...")
        print("    (This may download the model on first run)")
        
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-community-1.0",
            use_pytorch2_16=True if torch.cuda.is_available() else False
        )
        
        if torch.cuda.is_available():
            pipeline = pipeline.to(device)
        
        print("    pyannote: OK")
        return True
    except Exception as e:
        print(f"    pyannote: FAILED - {e}")
        return False


def main():
    print("=== WhisperX + pyannote Diarization Test ===\n")
    
    all_ok = True
    
    # Test imports
    if not test_imports():
        all_ok = False
    
    print()
    
    # Test CUDA
    test_cuda()
    
    print()
    
    # Test WhisperX
    if not test_whisperx():
        all_ok = False
    
    print()
    
    # Test pyannote
    if not test_pyannote():
        all_ok = False
    
    print()
    
    if all_ok:
        print("[+] All tests passed! Ready for diarized transcription.")
        print("\nExample usage:")
        print("python standup_recorder_diarized.py \\")
        print("  --monitor-source <monitor_source> \\")
        print("  --mic-source <mic_source> \\")
        print("  --language pt \\")
        print("  --device auto \\")
        print("  --min-speakers 2 \\")
        print("  --max-speakers 4")
    else:
        print("[!] Some tests failed. Check installation.")
        sys.exit(1)


if __name__ == "__main__":
    main()
