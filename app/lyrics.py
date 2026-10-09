"""Módulo de extracción y comparación de letras (Lyrics) en idioma nativo."""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Optional

# Palabras vacías comunes en español e inglés para filtrar antes de comparar
_STOPWORDS: frozenset[str] = frozenset({
    # Español
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del",
    "a", "al", "en", "con", "por", "para", "y", "o", "que", "se", "no",
    "si", "su", "sus", "mi", "mis", "tu", "tus", "lo", "le", "les", "me",
    "te", "nos", "como", "mas", "pero",
    # Inglés
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of",
    "with", "is", "it", "that", "this", "you", "i", "me", "my", "we",
    "our", "your", "he", "she", "they", "them", "was", "be", "so", "but",
})


def read_lyrics(file_path: Path) -> Optional[str]:
    """Extrae la letra de un archivo de audio (ID3 USLT / Vorbis) o archivo homónimo (.txt/.lrc).

    Sin dependencias externas ni llamadas de red. Retorna el texto limpio o None si no hay letra.
    """
    path = Path(file_path)
    if not path.is_file():
        return None

    # 1. Fallback local prioritario: archivo acompañante .txt o .lrc homónimo en la carpeta
    for ext in (".txt", ".lrc"):
        sidecar = path.with_suffix(ext)
        if sidecar.is_file():
            try:
                content = sidecar.read_text(encoding="utf-8", errors="ignore").strip()
                if content:
                    return content
            except Exception:
                pass

    # 2. Extracción de tag ID3v2 USLT (Unsynchronized lyrics) en archivos .mp3
    if path.suffix.lower() == ".mp3":
        try:
            with open(path, "rb") as f:
                header = f.read(10)
                if header[:3] == b"ID3":
                    # Tamaño syncsafe integer
                    tag_size = (
                        ((header[6] & 0x7F) << 21)
                        | ((header[7] & 0x7F) << 14)
                        | ((header[8] & 0x7F) << 7)
                        | (header[9] & 0x7F)
                    )
                    data = f.read(tag_size)
                    idx = data.find(b"USLT")
                    if idx != -1:
                        fsize = int.from_bytes(data[idx + 4 : idx + 8], "big")
                        frame_data = data[idx + 10 : idx + 10 + fsize]
                        if len(frame_data) > 4:
                            enc = frame_data[0]
                            codec = "latin1" if enc == 0 else "utf-16" if enc in (1, 2) else "utf-8"
                            rest = frame_data[4:].decode(codec, errors="ignore")
                            # La estructura es: [Descriptor\0] [Texto de la letra]
                            parts = rest.split("\x00", 1)
                            lyrics_text = parts[-1].strip() if len(parts) > 1 else rest.strip()
                            if lyrics_text:
                                return lyrics_text
        except Exception:
            pass

    return None


def clean_words(text: str) -> list[str]:
    """Tokeniza el texto en palabras en minúsculas y excluye stopwords."""
    words = re.findall(r"\b[a-zA-ZáéíóúÁÉÍÓÚñÑ0-9]+\b", text.lower())
    return [w for w in words if w not in _STOPWORDS]


def lyrics_similarity(text1: Optional[str], text2: Optional[str]) -> float:
    """Calcula la similitud de letra entre 0.0 y 1.0 en idioma nativo (sin traducción).

    Combina el coeficiente de Jaccard sobre palabras clave con coincidencia de secuencia.
    """
    if not text1 or not text2:
        return 0.0

    w1 = clean_words(text1)
    w2 = clean_words(text2)

    # Exigir al menos 5 palabras clave significativas para considerar una letra válida
    if len(w1) < 5 or len(w2) < 5:
        return 0.0

    s1, s2 = set(w1), set(w2)
    union = s1 | s2
    if not union:
        return 0.0

    jaccard = len(s1 & s2) / len(union)
    containment = len(s1 & s2) / min(len(s1), len(s2))
    seq_ratio = difflib.SequenceMatcher(None, " ".join(w1), " ".join(w2)).ratio()

    # Ponderación favoreciendo solapamiento de vocabulario y estructura de versos
    return max(jaccard, (containment * 0.7 + seq_ratio * 0.3))
