"""Utilidades de audio y texto: VAD + ASR (faster-whisper), diarización ligera, exportación y seudonimización."""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SR = 16000


# ----------------------------------------------------------------------------- ASR
_modelos: dict[str, object] = {}


def cargar_whisper(tamano: str = "small"):
    from faster_whisper import WhisperModel
    if tamano not in _modelos:
        _modelos[tamano] = WhisperModel(tamano, device="cpu", compute_type="int8", cpu_threads=4)
    return _modelos[tamano]


@dataclass
class Segmento:
    inicio: float
    fin: float
    texto: str
    hablante: str | None = None


def transcribir(ruta: str | Path, tamano: str = "small", vad: bool = True, beam_size: int = 1) -> tuple[list[Segmento], dict]:
    """Transcribe en español con VAD (Silero, integrado en faster-whisper). Devuelve segmentos y metadatos."""
    modelo = cargar_whisper(tamano)
    t0 = time.perf_counter()
    segs, info = modelo.transcribe(
        str(ruta), language="es", beam_size=beam_size, vad_filter=vad,
        vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=False,  # reduce alucinaciones en bucle
        no_speech_threshold=0.6,
    )
    salida = [Segmento(s.start, s.end, s.text.strip()) for s in segs]
    meta = {"duracion": info.duration, "duracion_voz": info.duration_after_vad,
            "segundos_proceso": time.perf_counter() - t0, "idioma": info.language}
    return salida, meta


# ----------------------------------------------------------------------- Diarización
_ecapa = None


def _embedding(y: np.ndarray) -> np.ndarray:
    global _ecapa
    import torch
    from speechbrain.inference.speaker import EncoderClassifier
    if _ecapa is None:
        from speechbrain.utils.fetching import LocalStrategy
        _ecapa = EncoderClassifier.from_hparams("speechbrain/spkrec-ecapa-voxceleb",
                                                savedir=str(Path("modelos/ecapa").absolute()),
                                                local_strategy=LocalStrategy.COPY)  # sin symlinks (Windows)
    with torch.no_grad():
        e = _ecapa.encode_batch(torch.tensor(y, dtype=torch.float32).unsqueeze(0)).squeeze().numpy()
    return e / (np.linalg.norm(e) + 1e-9)


def diarizar(ruta: str | Path, segmentos: list[Segmento], umbral: float = 0.70, max_hablantes: int = 4) -> int:
    """Asigna hablantes a los segmentos del ASR: embeddings ECAPA + clustering aglomerativo (coseno).

    Devuelve el número de hablantes. Segmentos < 0.8 s heredan el hablante del anterior.
    """
    import soundfile as sf
    from sklearn.cluster import AgglomerativeClustering

    y, sr = sf.read(str(ruta))
    if y.ndim > 1:
        y = y.mean(axis=1)
    idx, embs = [], []
    for i, s in enumerate(segmentos):
        trozo = y[int(s.inicio * sr): int(s.fin * sr)]
        if len(trozo) >= 0.8 * sr:
            idx.append(i)
            embs.append(_embedding(trozo))
    if len(embs) < 2:
        for s in segmentos:
            s.hablante = "HABLANTE_1"
        return 1
    cl = AgglomerativeClustering(n_clusters=None, metric="cosine", linkage="average",
                                 distance_threshold=umbral).fit(np.vstack(embs))
    etiquetas = cl.labels_
    # renumerar por orden de aparición y limitar
    orden: dict[int, int] = {}
    for e in etiquetas:
        orden.setdefault(e, len(orden) + 1)
    previo = None
    mapa = dict(zip(idx, etiquetas))
    for i, s in enumerate(segmentos):
        if i in mapa:
            previo = f"HABLANTE_{min(orden[mapa[i]], max_hablantes)}"
        s.hablante = previo or "HABLANTE_1"
    return len({s.hablante for s in segmentos})


# ------------------------------------------------------------------------ Exportación
def texto_con_hablantes(segmentos: list[Segmento]) -> str:
    partes, actual = [], None
    for s in segmentos:
        if s.hablante and s.hablante != actual:
            partes.append(f"[{s.hablante}]")
            actual = s.hablante
        partes.append(s.texto)
    return " ".join(partes).strip()


def _ts(t: float) -> str:
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"


def exportar(segmentos: list[Segmento], base: Path) -> None:
    base.parent.mkdir(parents=True, exist_ok=True)
    srt = []
    for i, s in enumerate(segmentos, 1):
        pref = f"[{s.hablante}] " if s.hablante else ""
        srt.append(f"{i}\n{_ts(s.inicio)} --> {_ts(s.fin)}\n{pref}{s.texto}\n")
    base.with_suffix(".srt").write_text("\n".join(srt), encoding="utf-8")
    base.with_suffix(".txt").write_text(texto_con_hablantes(segmentos), encoding="utf-8")


# --------------------------------------------------------------------- Seudonimización
PATRONES = {
    "DNI": re.compile(r"\b(?:DNI\s*[:N°º.]*\s*)?\d{8}\b"),
    "TELEFONO": re.compile(r"\b9\d{2}[\s-]?\d{3}[\s-]?\d{3}\b"),
    "CORREO": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
}
DISPARADORES = re.compile(
    r"\b((?i:me llamo|mi nombre es|yo soy|soy la señora|soy el señor|señora|señor))\s+"
    r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,2})")


_VOCALES = {"a": "[aá]", "e": "[eé]", "i": "[ií]", "o": "[oó]", "u": "[uúü]"}


def _sin_tildes(nombre: str) -> str:
    """Patrón que acepta el nombre con o sin tildes (el ASR escribe "Durán" aunque la fuente diga "Duran")."""
    base = "".join(c for c in unicodedata.normalize("NFKD", nombre) if not unicodedata.combining(c))
    return "".join(_VOCALES.get(c.lower(), re.escape(c)) for c in base)


def seudonimizar(texto: str, nombres: list[str] | None = None, tabla: dict[str, str] | None = None,
                 disparadores: bool = True) -> tuple[str, int, dict[str, str]]:
    """Reemplaza datos personales por seudónimos estables. Devuelve (texto, n_reemplazos, tabla).

    - `nombres`: lista de nombres reales conocidos por los metadatos (entrevistados privados).
    - Patrones: DNI (8 dígitos), teléfonos móviles peruanos, correos y nombres tras disparadores.
    La tabla de correspondencias NO se publica (queda en datos/raw/).
    """
    tabla = {} if tabla is None else tabla
    n = 0
    if not isinstance(texto, str) or not texto:
        return texto, 0, tabla

    def seud(real: str, clase: str) -> str:
        if real not in tabla:
            k = sum(1 for v in tabla.values() if v.startswith(f"[{clase}_")) + 1
            tabla[real] = f"[{clase}_{k}]"
        return tabla[real]

    for nombre in sorted(nombres or [], key=len, reverse=True):
        partes = [nombre] + ([nombre.split()[0]] if " " in nombre and len(nombre.split()[0]) > 3 else [])
        for parte in partes:  # primero el nombre completo, luego el nombre de pila
            patron = re.compile(rf"\b{_sin_tildes(parte)}\b", re.IGNORECASE)
            texto, k = patron.subn(lambda m, nm=nombre: seud(nm, "PERSONA"), texto)
            n += k
    for clase, patron in PATRONES.items():
        texto, k = patron.subn(lambda m, c=clase: seud(m.group(0), c), texto)
        n += k

    def _disp(m):
        return f"{m.group(1)} {seud(m.group(2), 'PERSONA')}"
    if disparadores:  # solo en habla espontánea; en documentos históricos tacharía "Señor General", etc.
        texto, k = DISPARADORES.subn(_disp, texto)
        n += k
    return texto, n, tabla


# ---------------------------------------------------------------------- Normalización
def normalizar(texto: str, quitar_hablantes: bool = True) -> str:
    """Criterio común para CER/WER: minúsculas, sin tildes, sin puntuación, espacios simples."""
    if not isinstance(texto, str):
        return ""
    if quitar_hablantes:
        texto = re.sub(r"\[(HABLANTE|PERSONA|DNI|TELEFONO|CORREO)_\d+\]", " ", texto)
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9ñ\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()
