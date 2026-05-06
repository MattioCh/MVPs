"""TTS adapter — local macOS `say`. No network, no API key.

Kept behind this module so the loop stays provider-agnostic. To swap in a
cloud TTS later, replace the body of `speak()` and keep the signature.
"""

from __future__ import annotations

from functools import lru_cache
import shutil
import subprocess


def _parse_say_voices(raw: str) -> list[tuple[str, str]]:
    voices: list[tuple[str, str]] = []
    for line in raw.splitlines():
        left = line.split("#", 1)[0].strip()
        if not left:
            continue
        try:
            name, locale = left.rsplit(None, 1)
        except ValueError:
            continue
        voices.append((name.strip(), locale.strip()))
    return voices


@lru_cache(maxsize=1)
def _installed_say_voices() -> list[tuple[str, str]]:
    say_bin = shutil.which("say")
    if not say_bin:
        return []
    try:
        proc = subprocess.run(
            [say_bin, "-v", "?"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    return _parse_say_voices(proc.stdout)


def _voice_for_language(language: str) -> str | None:
    voices = _installed_say_voices()
    if not voices:
        return None

    name_to_locale = {name: locale for name, locale in voices}
    if language == "zh":
        preferred_names = [
            "Tingting",
            "Sin-ji",
            "Meijia",
            "Eddy (Chinese (China mainland))",
            "Flo (Chinese (China mainland))",
            "Eddy (Chinese (Taiwan))",
            "Flo (Chinese (Taiwan))",
        ]
        for name in preferred_names:
            if name in name_to_locale:
                return name
        for name, locale in voices:
            if locale.startswith("zh_"):
                return name
        return None

    if language == "en":
        preferred_names = [
            "Samantha",
            "Daniel",
            "Karen",
            "Eddy (English (US))",
            "Flo (English (US))",
            "Reed (English (US))",
            "Shelley (English (US))",
        ]
        for name in preferred_names:
            if name in name_to_locale:
                return name
        for name, locale in voices:
            if locale.startswith("en_"):
                return name

    return None


def speak(
    message: str,
    voice: str | None = None,
    language: str = "auto",
) -> None:
    """Speak `message` aloud using macOS `say` with optional language/voice selection."""
    message = message.strip()
    if not message:
        return
    say_bin = shutil.which("say")
    if not say_bin:
        # Non-macOS or `say` unavailable — stay quiet rather than crash the loop.
        return
    cmd = [say_bin]
    selected_voice = voice or _voice_for_language(language)
    if selected_voice:
        cmd += ["-v", selected_voice]
    cmd.append(message)
    try:
        subprocess.run(cmd, check=False)
    except OSError:
        # Quiet by default: never let TTS errors break the loop.
        return
