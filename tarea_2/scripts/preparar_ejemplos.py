"""Copia una muestra ligera y publicable a datos/ejemplos/ para el dashboard.

- Imágenes: todos los documentos del corpus final (dominio público / CC0 / CC BY / CC BY-SA, atribuidos en fuentes.csv),
  reducidas a 900 px de ancho, excepto doc_015 (contiene el nombre de una persona privada).
- Audio: clips de OpenSLR 73 (hablantes anónimos con ID, CC BY-SA 4.0) y dos entrevistas breves de Commons
  en las que no se mencionan nombres (CC BY-SA 4.0), en MP3 de 48 kbps.
"""
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
import pandas as pd
from PIL import Image

raiz = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
ej = raiz / "datos" / "ejemplos"
ej.mkdir(parents=True, exist_ok=True)
docs = pd.read_csv(raiz / "datos" / "documentos.csv")
SIN_PUBLICAR = {"doc_015"}  # placa con el nombre de un dirigente vecinal (persona privada)
for r in docs[~docs.id.isin(SIN_PUBLICAR)].itertuples():
    im = Image.open(raiz / r.archivo).convert("RGB")
    im.thumbnail((900, 1400))
    im.save(ej / f"{r.id}.jpg", quality=80)

aud = pd.read_csv(raiz / "datos" / "transcripciones.csv")
publicables = list(aud[aud.fuente.str.contains("OpenSLR")].id) + ["clip_003", "clip_004"]
ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
for r in aud[aud.id.isin(publicables)].itertuples():
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(raiz / r.archivo_audio), "-b:a", "48k",
                    str(ej / f"{r.id}.mp3")], check=True)
total = sum(f.stat().st_size for f in ej.iterdir()) / 1e6
print(f"{len(list(ej.iterdir()))} archivos, {total:.1f} MB")
