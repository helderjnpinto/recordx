#!/usr/bin/env python3
"""Device configuration: pactl source discovery and config.json profiles."""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"


class ConfigError(RuntimeError):
    pass


def load_config():
    if not CONFIG_PATH.exists():
        return None
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[!] Warning: config.json is corrupt or unreadable ({e}); re-running setup.")
        return None


def save_config(cfg):
    tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_path, CONFIG_PATH)


def get_profile(cfg, profile_name=None):
    name = profile_name or cfg.get("active_profile")
    if not name or name not in cfg.get("profiles", {}):
        available = ", ".join(cfg.get("profiles", {}).keys()) or "(none)"
        raise ConfigError(
            f"Profile '{name}' not found in config.json. Available profiles: {available}. "
            f"Run `python recorder.py --configure` to add one."
        )
    return cfg["profiles"][name]


def list_pactl_sources():
    """Return pactl sources, flagging likely monitor/default-monitor sources."""
    try:
        result = subprocess.run(
            ["pactl", "list", "short", "sources"],
            check=True, capture_output=True, text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise ConfigError(f"Could not run `pactl list short sources`: {e}")

    default_sink = None
    try:
        sink_result = subprocess.run(
            ["pactl", "get-default-sink"], check=True, capture_output=True, text=True,
        )
        default_sink = sink_result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    default_monitor = f"{default_sink}.monitor" if default_sink else None

    sources = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        index, name, driver, sample_spec = parts[0], parts[1], parts[2], parts[3]
        state = parts[4] if len(parts) > 4 else ""
        is_monitor = name.endswith(".monitor")
        sources.append({
            "index": int(index),
            "name": name,
            "state": state,
            "is_monitor": is_monitor,
            "is_likely_default_monitor": name == default_monitor,
        })
    return sources


def _prompt_choice(prompt, sources):
    while True:
        raw = input(prompt).strip()
        if not raw.isdigit():
            print("    Please enter a number from the list above.")
            continue
        choice = int(raw)
        for s in sources:
            if s["index"] == choice:
                return s["name"]
        print("    Number not in the list, try again.")


def interactive_configure(existing_cfg):
    if not sys.stdin.isatty():
        raise ConfigError(
            "No config found and no TTY available for interactive setup. "
            "Run `python recorder.py --configure` interactively first, "
            "or create config.json from config.example.json."
        )

    sources = list_pactl_sources()
    if not sources:
        raise ConfigError("No PulseAudio/PipeWire sources found (is pactl working?).")

    mic_candidates = [s for s in sources if not s["is_monitor"]]
    monitor_candidates = [s for s in sources if s["is_monitor"]]

    print("\nMicrophone candidates:")
    for s in mic_candidates:
        print(f"  [{s['index']}] {s['name']} ({s['state']})")

    print("\nSystem-audio monitor candidates:")
    for s in monitor_candidates:
        marker = "  <- likely default" if s["is_likely_default_monitor"] else ""
        print(f"  [{s['index']}] {s['name']} ({s['state']}){marker}")

    print()
    mic_source = _prompt_choice("Select microphone source [number]: ", mic_candidates)
    monitor_source = _prompt_choice("Select system-audio monitor source [number]: ", monitor_candidates)

    profile_name = input("Profile name [default]: ").strip() or "default"
    label = input("Label (human description, optional): ").strip()

    cfg = existing_cfg or {"version": 1, "active_profile": profile_name, "profiles": {}}
    cfg["profiles"][profile_name] = {
        "label": label,
        "mic_source": mic_source,
        "monitor_source": monitor_source,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    cfg["active_profile"] = profile_name
    cfg.setdefault("version", 1)
    save_config(cfg)

    print(f"\n[+] Saved profile '{profile_name}' to {CONFIG_PATH}")
    print(f"    mic_source:     {mic_source}")
    print(f"    monitor_source: {monitor_source}")
    print(f"    Re-run setup any time with: python recorder.py --configure")
    print(f"    Use a different saved profile with: python recorder.py --profile <name>")
    return cfg


def ensure_config(profile_name=None):
    cfg = load_config()
    if cfg is None:
        print("[i] No configuration found - let's set up your audio devices.")
        cfg = interactive_configure(None)
    return cfg
