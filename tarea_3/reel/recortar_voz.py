"""Transcribe la grabación con tiempos y recorta un tramo de 15 a 25 s como voz de referencia.

    uv run --extra reel python reel/recortar_voz.py audio.ogg                 # solo muestra segmentos
    uv run --extra reel python reel/recortar_voz.py audio.ogg --desde 3.2 --hasta 24.8

El recorte se guarda en reel/recursos/mi_voz.wav (no se sube al repositorio).
"""
import argparse
import subprocess

import reel

p = argparse.ArgumentParser()
p.add_argument("audio")
p.add_argument("--desde", type=float)
p.add_argument("--hasta", type=float)
a = p.parse_args()

if a.desde is None:
    audio = reel.cargar_audio(a.audio)
    segs, _ = reel._whisper().transcribe(audio, language="es", vad_filter=True)
    for s in segs:
        print(f"{s.start:6.1f} - {s.end:6.1f}  {s.text.strip()}")
else:
    salida = reel.AQUI / "recursos" / "mi_voz.wav"
    subprocess.run([reel.FFMPEG, "-v", "error", "-y", "-i", a.audio, "-ss", str(a.desde), "-to", str(a.hasta),
                    "-ac", "1", "-ar", "24000", "-af", "afade=t=in:d=0.05,areverse,afade=t=in:d=0.1,areverse",
                    str(salida)], check=True)
    print(f"guardado {salida} ({a.hasta - a.desde:.1f} s)")
