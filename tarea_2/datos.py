"""Descarga reproducible de los corpus de la Tarea 2.

- Documentos: Wikimedia Commons (API, miniaturas de 1280 px; páginas de PDF vía `pageN-`).
- Audio: entrevistas de Wikimedia Commons + clips de OpenSLR 73 (es_pe, CC BY-SA 4.0)
  extraídos del zip remoto sin bajar el archivo completo (HTTP Range con `remotezip`).

Uso:  uv run python datos.py
Respeta una pausa de 1-2 s entre solicitudes y usa un User-Agent descriptivo.
"""
from __future__ import annotations

import csv
import hashlib
import random
import re
import subprocess
import time
from pathlib import Path

import imageio_ffmpeg
import requests

RAIZ = Path(__file__).parent
RAW_DOC = RAIZ / "datos" / "raw" / "documentos"
RAW_AUD = RAIZ / "datos" / "raw" / "audio"
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "Tarea2-DataSciencePython/1.0 (proyecto academico; contacto via GitHub d2cml-ai)"}
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# (titulo en Commons, tipo, pagina_pdf o None)
DOCUMENTOS = [
    # Impresos nítidos (escaneos de publicaciones peruanas)
    ("File:Constitución Política de la República Peruana (1828).pdf", "impreso", 5),
    ("File:Constitución Política de la República Peruana (1828).pdf", "impreso", 12),
    ("File:Constitución Política del Perú (1856).pdf", "impreso", 4),
    ("File:Constitución Política del Perú (1856).pdf", "impreso", 10),
    ("File:Constitución política del Perú reformada por el Congreso de 1860.pdf", "impreso", 5),
    ("File:Constitución política del Perú reformada por el Congreso de 1860.pdf", "impreso", 11),
    ("File:CODIGO DE ETICA PROFESIONAL DE LA PNP.pdf", "impreso", 6),
    ("File:CODIGO DE ETICA PROFESIONAL DE LA PNP.pdf", "impreso", 2),
    # Fotos con sombras, reflejos o inclinación (tomadas con cámara)
    ("File:Capitulación de Ayacucho1.jpg", "foto", None),
    ("File:Capitulacón de Ayacucho2.jpg", "foto", None),
    ("File:Palacio Iturregui - Placa.jpg", "foto", None),
    ("File:Placa del Palacio Iturregui de Trujillo.jpg", "foto", None),
    ("File:Huaca Las Balsas - Cartel informativo.jpg", "foto", None),
    ("File:Huaca Melgarejo (Fichero Informativo).jpg", "foto", None),
    ("File:Placa de inauguración de la biblioteca comunal JMA.jpg", "foto", None),
    ("File:Plaque of the Central Reserve Bank of Peru, Trujillo.jpg", "foto", None),
    ("File:Lambayeque, Cradle of Liberty.jpg", "foto", None),
    ("File:Peru revenue stamp on receipt.jpg", "foto", None),
    # Manuscritos
    ("File:Estado General de Miguel Grau.jpg", "manuscrito", None),
    ("File:Socgeolima.jpg", "manuscrito", None),
    ("File:Libro de Bautismos en la Gran Villa de Lampa 1655-1722.jpg", "manuscrito", None),
    ("File:Libro de Bautismos en la Gran Villa de Lampa 1832.jpg", "manuscrito", None),
    ("File:Libro de Bautismos en la Gran Villa de Lampa 1871.jpg", "manuscrito", None),
    ("File:Asiento de la partida de bautismo de Raúl Porras Barrenechea.jpg", "manuscrito", None),
    ("File:Joseolaya partida nacimiento chica.jpg", "manuscrito", None),
    ("File:Acta de Independencia Peru.jpg", "manuscrito", None),
    ("File:Peruvian Telephone Company receipt Lima 1895.JPG", "manuscrito", None),
    ("File:Estado General de Miguel Grau.jpg", "manuscrito", None),  # duplicado intencional: se elimina por hash
]

ENTREVISTAS = [
    "File:Entrevista 1 en la Av. Rivagüero - El Agustino.ogg",
    "File:Entrevista 2 en la Av. Rivagüero - El Agustino.ogg",
    "File:Entrevista en el medio tiempo.opus",
    "File:Audio de la entrevista a una chica que participaba de la marcha.ogg",
    "File:UNMSM Entrevistas en la marcha 1 por Cristopher Serrano Pérez.wav",
    "File:UNMSM Entrevista realizada en la marcha por Cristopher Serrano Pérez.wav",
    "File:Entrevista a la señora Aurelia, mujer shuyasina.ogg",
    "File:Entrevista-Aurora Coronado-organización de mujeres indígenas-fiestas patrias.ogg",
    "File:Entrevista 1,.wav",
    "File:Entrevista 2.wav",
]

OPENSLR = "https://www.openslr.org/resources/73/{}"
N_CLIPS_OPENSLR = 14          # clips agrupados por hablante
UTT_POR_CLIP = 12             # ~5 s por enunciado -> ~60 s por clip


def limpiar_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def info_commons(titulo: str, ancho: int | None = 1280, pagina: int | None = None) -> dict:
    params = {"action": "query", "prop": "imageinfo", "titles": titulo, "format": "json",
              "iiprop": "url|size|extmetadata|sha1|mime"}
    if ancho:
        params["iiurlparam"] = f"page{pagina}-{ancho}px" if pagina else f"{ancho}px"
    for intento in range(6):
        r = requests.get(API, params=params, headers=UA, timeout=60)
        if r.status_code != 429:
            break
        time.sleep(int(r.headers.get("Retry-After", 10 * (intento + 1))))
    r.raise_for_status()
    pag = next(iter(r.json()["query"]["pages"].values()))
    ii = pag["imageinfo"][0]
    md = ii.get("extmetadata", {})
    return {
        "url_descarga": (ii.get("thumburl") or ii["url"]).split("?")[0],
        "url_original": ii["url"].split("?")[0],
        "fuente_url": f"https://commons.wikimedia.org/?curid={pag['pageid']}",  # enlace estable sin nombres en la URL
        "licencia": md.get("LicenseShortName", {}).get("value", ""),
        "autor": limpiar_html(md.get("Artist", {}).get("value", "")),
        "duracion": ii.get("duration"),
    }


def bajar(url: str, destino: Path) -> None:
    for intento in range(4):
        r = requests.get(url, headers=UA, timeout=120)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 10 * (intento + 1))))
            continue
        r.raise_for_status()
        destino.write_bytes(r.content)
        return
    r.raise_for_status()


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def descargar_documentos() -> list[dict]:
    RAW_DOC.mkdir(parents=True, exist_ok=True)
    filas = []
    for i, (titulo, tipo, pagina) in enumerate(DOCUMENTOS, start=1):
        doc_id = f"doc_{i:03d}"
        destino = RAW_DOC / f"{doc_id}.jpg"
        meta = info_commons(titulo, pagina=pagina)
        if not destino.exists():
            bajar(meta["url_descarga"], destino)
        time.sleep(1.5)
        filas.append({"id": doc_id, "modalidad": "documento", "tipo": tipo, "titulo": titulo,
                      "pagina": pagina or "", "archivo": destino.relative_to(RAIZ).as_posix(),
                      "fuente_url": meta["fuente_url"], "licencia": meta["licencia"],
                      "autor": meta["autor"], "sha256": sha256(destino)})
        print(doc_id, tipo, titulo, meta["licencia"])
    return filas


def a_wav16k(origen: Path, destino: Path) -> None:
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(origen), "-ac", "1", "-ar", "16000", str(destino)],
                   check=True)


def descargar_entrevistas() -> list[dict]:
    (RAW_AUD / "originales").mkdir(parents=True, exist_ok=True)
    filas = []
    for i, titulo in enumerate(ENTREVISTAS, start=1):
        clip_id = f"clip_{i:03d}"
        meta = info_commons(titulo, ancho=None)
        ext = Path(meta["url_original"].split("?")[0]).suffix
        orig = RAW_AUD / "originales" / f"{clip_id}{ext}"
        wav = RAW_AUD / f"{clip_id}.wav"
        if not orig.exists():
            bajar(meta["url_original"], orig)
        if not wav.exists():
            a_wav16k(orig, wav)
        time.sleep(1.5)
        filas.append({"id": clip_id, "modalidad": "audio", "tipo": "entrevista_commons", "titulo": titulo,
                      "archivo": wav.relative_to(RAIZ).as_posix(), "fuente_url": meta["fuente_url"],
                      "licencia": meta["licencia"], "autor": meta["autor"], "sha256": sha256(orig),
                      "texto_referencia_fuente": ""})
        print(clip_id, titulo, meta["licencia"])
    return filas


def descargar_openslr(inicio: int) -> list[dict]:
    """Agrupa enunciados de un mismo hablante en clips de ~60 s.

    La referencia es la transcripción humana publicada por OpenSLR (line_index.tsv).
    """
    import soundfile as sf
    import numpy as np
    from remotezip import RemoteZip

    random.seed(73)
    filas = []
    import io
    k = inicio
    for zipname in ["es_pe_female.zip", "es_pe_male.zip"]:
        with RemoteZip(OPENSLR.format(zipname), headers=UA) as z:
            idx = next(n for n in z.namelist() if n.endswith("line_index.tsv"))
            lineas = z.read(idx).decode("utf-8").strip().splitlines()
            por_hablante: dict[str, list[tuple[str, str]]] = {}
            for ln in lineas:
                utt, texto = ln.split("\t", 1)
                hablante = "_".join(utt.split("_")[:2])
                por_hablante.setdefault(hablante, []).append((utt, texto.strip()))
            hablantes = sorted(h for h, u in por_hablante.items() if len(u) >= UTT_POR_CLIP)
            elegidos = random.sample(hablantes, N_CLIPS_OPENSLR // 2)
            nombres = {Path(n).stem: n for n in z.namelist() if n.endswith(".wav")}
            for h in elegidos:
                utts = sorted(por_hablante[h])[:UTT_POR_CLIP]
                partes, textos = [], []
                for utt, texto in utts:
                    y, sr = sf.read(io.BytesIO(z.read(nombres[utt])))  # en memoria (rutas largas en Windows)
                    if sr != 16000:
                        import librosa
                        y = librosa.resample(y, orig_sr=sr, target_sr=16000)
                    partes += [y, np.zeros(int(0.4 * 16000))]
                    textos.append(texto)
                clip_id = f"clip_{k:03d}"
                wav = RAW_AUD / f"{clip_id}.wav"
                sf.write(wav, np.concatenate(partes), 16000)
                filas.append({"id": clip_id, "modalidad": "audio", "tipo": "openslr73",
                              "titulo": f"OpenSLR 73 {zipname} hablante {h} ({len(utts)} enunciados)",
                              "archivo": wav.relative_to(RAIZ).as_posix(),
                              "fuente_url": OPENSLR.format(zipname), "licencia": "CC BY-SA 4.0",
                              "autor": "Google / Guevara-Rukoz et al. (2020)", "sha256": sha256(wav),
                              "texto_referencia_fuente": " ".join(textos)})
                print(clip_id, h)
                k += 1
                time.sleep(1)
    return filas


def guardar(filas: list[dict], ruta: Path) -> None:
    claves = list(dict.fromkeys(c for f in filas for c in f))
    with ruta.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=claves)
        w.writeheader()
        w.writerows(filas)


if __name__ == "__main__":
    (RAIZ / "datos").mkdir(exist_ok=True)
    docs = descargar_documentos()
    guardar(docs, RAW_DOC / "manifiesto.csv")
    aud = descargar_entrevistas()
    aud += descargar_openslr(inicio=len(aud) + 1)
    guardar(aud, RAW_AUD / "manifiesto.csv")
