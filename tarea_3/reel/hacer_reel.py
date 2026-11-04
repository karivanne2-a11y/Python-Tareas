"""guion.json -> voz clonada -> reel vertical (adaptado de la sesión 15 del curso).

    uv run python reel/hacer_reel.py --muda                       # vista previa sin voz (revisar diseño)
    uv run --extra reel python reel/hacer_reel.py --voz reel/recursos/mi_voz.m4a

Guarda en reel/: reel.mp4, reel.wav, subtitulos.srt y portada.png (y añade el WER por escena a guion.json).
"""
import argparse
import json
import time

import reel

p = argparse.ArgumentParser()
p.add_argument("--voz", help="15 a 25 s de tu voz: wav, m4a, ogg o mp3")
p.add_argument("--muda", action="store_true", help="sin TTS: tiempos estimados, para revisar el diseño")
p.add_argument("--reusar", action="store_true", help="usa la narración ya generada (reel.wav) y solo rehace subtítulos y video")
p.add_argument("--autor", default="Karen Macedo")
p.add_argument("--fuente", default="UN Comtrade y BCRP")
p.add_argument("--device", default="cpu", help="cpu, mps (Mac) o cuda")
p.add_argument("--motor", default="qwen", choices=["qwen", "voxcpm"], help="voxcpm acepta estilo de locutor por escena")
p.add_argument("--tts", default="Qwen/Qwen3-TTS-12Hz-0.6B-Base", help="con --motor qwen; el 1.7B suena mejor pero es más lento")
p.add_argument("--sin-estilo", action="store_true", help="con --motor voxcpm: clona sin indicar estilo")
p.add_argument("--velocidad", type=float, default=1.0, help="1.08 = 8 %% más rápido, sin cambiar el tono")
a = p.parse_args()
if not (a.muda or a.reusar or a.voz):
    p.error("usa --voz con tu grabación, --reusar o --muda para la vista previa")

t0 = time.time()
salidas = reel.AQUI
archivo_guion = salidas / "guion.json"
guion = json.loads(archivo_guion.read_text(encoding="utf-8"))
for e in guion["escenas"]:
    print(f"   {e['cifra'] or '-':>12} | {e['frase']}")

if a.muda:
    narracion = reel.narracion_muda(guion)
    reel._reloj(f"vista previa: {narracion.duracion:.1f} s estimados", t0)
    reel.portada(guion, narracion, salidas / "portada_previa.png", a.fuente, a.autor)
    reel.video(guion, narracion, salidas / "reel_previa.mp4", a.fuente, a.autor)
    reel._reloj(f"listo: {salidas / 'reel_previa.mp4'}", t0)
    raise SystemExit

if a.reusar:
    narracion = reel.narracion_guardada(salidas / "reel.wav", len(guion["escenas"]))
    reel._reloj(f"narración reutilizada: {narracion.duracion:.1f} s, {len(narracion.escenas)} escenas", t0)
    reel.subtitulos(narracion, guion)
    reel.a_srt(narracion, salidas / "subtitulos.srt")
    reel.portada(guion, narracion, salidas / "portada.png", a.fuente, a.autor)
    reel.video(guion, narracion, salidas / "reel.mp4", a.fuente, a.autor)
    reel._reloj(f"listo: {salidas / 'reel.mp4'}", t0)
    raise SystemExit

if a.motor == "voxcpm":
    voz = reel.VozExpresiva(a.voz, device=a.device, con_estilo=not a.sin_estilo)
else:
    voz = reel.Voz(a.voz, modelo=a.tts, device=a.device)
reel._reloj(f"voz cargada; referencia: «{voz.texto_ref}»", t0)
narracion = reel.narrar(voz, guion, velocidad=a.velocidad)
archivo_guion.write_text(json.dumps(guion, ensure_ascii=False, indent=2), encoding="utf-8")
reel._reloj(f"narración: {narracion.duracion:.1f} s; WER por escena: "
            + ", ".join(f"{e['wer']:.2f}" for e in guion["escenas"]), t0)
if not 45 <= narracion.duracion <= 75:
    print(f"   ¡Ojo! La tarea pide 45 a 75 s y salió {narracion.duracion:.0f} s: ajusta --velocidad.")

reel.subtitulos(narracion, guion)
reel.a_srt(narracion, salidas / "subtitulos.srt")
reel._reloj(f"subtítulos: {len(narracion.palabras)} palabras", t0)

reel.portada(guion, narracion, salidas / "portada.png", a.fuente, a.autor)
reel.video(guion, narracion, salidas / "reel.mp4", a.fuente, a.autor)
reel._reloj(f"listo: {salidas / 'reel.mp4'}", t0)
