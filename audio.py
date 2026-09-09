#!/usr/bin/env python3
"""ffmpeg recording: command building and the stop-on-Enter-or-Ctrl+C record loop."""
import subprocess
import sys
import threading
import time
from datetime import datetime


def run_cmd(cmd, check=True, capture_output=False, text=True):
    return subprocess.run(cmd, check=check, capture_output=capture_output, text=text)


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
    Record desktop/system audio from a Pulse/PipeWire monitor source
    and microphone from another source, then mix both into a mono WAV.
    """
    filter_complex = (
        "[0:a]volume=1.0,aresample={sr},aformat=sample_fmts=s16:channel_layouts=mono[a0];"
        "[1:a]volume=1.0,aresample={sr},aformat=sample_fmts=s16:channel_layouts=mono[a1];"
        "[a0][a1]amix=inputs=2:duration=longest:dropout_transition=2,"
        "loudnorm=I=-16:TP=-1.5:LRA=11[out]"
    ).format(sr=sample_rate)

    return [
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


class StopController:
    """A single stop signal that Enter, Ctrl+C, and a timeout can all raise."""

    def __init__(self):
        self._event = threading.Event()
        self._reason = None

    def request_stop(self, reason):
        if not self._event.is_set():
            self._reason = reason
            self._event.set()

    def is_set(self):
        return self._event.is_set()

    def reason(self):
        return self._reason


def _enter_listener(controller):
    try:
        sys.stdin.readline()
    except Exception:
        return
    controller.request_stop("enter_key")


def _timeout_watcher(controller, proc, max_minutes):
    time.sleep(max_minutes * 60)
    if proc.poll() is None:
        controller.request_stop("max_minutes")


def record_until_stopped(ffmpeg_cmd, max_minutes=None):
    print("[+] Starting recording...")
    print("    Press ENTER to stop (or Ctrl+C).\n")
    print("    FFmpeg command:")
    print("    " + " ".join(ffmpeg_cmd))
    print("\n[=] Initializing audio sources...")

    proc = subprocess.Popen(ffmpeg_cmd)
    time.sleep(1)

    if proc.poll() is not None:
        print("[!] ERROR: FFmpeg failed to start")
        return proc.returncode

    print("[=] Recording started successfully!")
    print("[=] Audio capture in progress...")

    controller = StopController()
    start_time = time.time()

    if sys.stdin.isatty():
        threading.Thread(target=_enter_listener, args=(controller,), daemon=True).start()
    if max_minutes:
        threading.Thread(target=_timeout_watcher, args=(controller, proc, max_minutes), daemon=True).start()

    try:
        while proc.poll() is None and not controller.is_set():
            elapsed = int(time.time() - start_time)
            print(f"[=] Recording time: {elapsed:03d}s", end="\r", flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        controller.request_stop("sigint")

    if proc.poll() is None:
        print(f"\n[+] Stopping recording ({controller.reason()})...")
        print("    Waiting for FFmpeg to finalize...")
        time.sleep(2)
        proc.terminate()
        time.sleep(1)
        if proc.poll() is None:
            print("    Force stopping FFmpeg...")
            proc.kill()

    proc.wait()

    total_duration = int(time.time() - start_time)
    print(f"\n[=] Recording completed! Duration: {total_duration:03d}s")

    if proc.returncode not in (0, 255):
        print(f"WARNING: ffmpeg exited with code {proc.returncode}")

    return proc.returncode
