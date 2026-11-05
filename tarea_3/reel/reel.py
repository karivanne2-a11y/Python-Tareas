"""guion.json -> voz clonada -> reel vertical.

Basado en sessions/15-texto-a-reel/reel.py del curso (d2cml-ai/Data-Science-Python). Cambios para la Tarea 3:
    - cada escena puede traer "imagen" (gráfico o captura del dashboard) que se dibuja bajo la cifra
    - música de fondo generada por código (sin derechos de autor), más baja que la voz
    - créditos de gráficos y música en el pie
    - narracion_muda(): tiempos aproximados sin TTS, para revisar el diseño antes de clonar la voz

    Voz           Qwen3-TTS clona tu voz con 10 a 20 s de audio y narra cada escena
    VozExpresiva  VoxCPM2 clona tu voz y además acepta un estilo por escena (locutor, urgente, cálido)
    subtitulos()  Whisper transcribe la narración: subtítulos palabra por palabra y control de calidad
    video()       reel 1080x1920 con cifras, subtítulos y aviso de voz generada con IA

El paso 1 (texto largo -> guion.json) está en guion.py.
"""
import re
import subprocess
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

AQUI = Path(__file__).parent
FUENTES = AQUI / "fuentes"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

TTS = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
ASR = "large-v3-turbo"

ANCHO, ALTO, FPS = 1080, 1920, 30
MARGEN = 90
FONDO, TEXTO, SUAVE, ACENTO, CAJA = "#1C1A17", "#F7F3EC", "#B8AE9F", "#F08A4B", "#2A2723"
PAUSA, INICIO, FINAL = 0.35, 0.3, 0.8   # segundos de silencio entre escenas, al inicio y al final
# Estilos de VoxCPM2 por defecto; en inglés funcionan mejor que en español. Una escena puede traer su "estilo" en guion.json
ESTILOS = {"inicio": "urgent, dramatic news anchor, strong emphasis",
           "medio": "confident news anchor, energetic, clear emphasis on the numbers",
           "cierre": "warm, friendly, inviting tone"}


def _reloj(msg, t):
    print(f"[{time.time() - t:5.1f}s] {msg}", flush=True)


# Voz clonada ---------------------------------------------------------------

def cargar_audio(ruta, sr=16000):
    """Cualquier audio (wav, m4a, ogg de WhatsApp, mp3) a mono float32 con ffmpeg."""
    crudo = subprocess.run([FFMPEG, "-v", "error", "-i", str(ruta), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                           capture_output=True, check=True).stdout
    return np.frombuffer(crudo, np.float32)


class Voz:
    """Clona una voz a partir de 10 a 20 segundos de audio y su transcripción (la hace Whisper)."""

    def __init__(self, referencia, modelo=TTS, device="cpu"):
        import torch
        from qwen_tts import Qwen3TTSModel

        self.referencia = cargar_audio(referencia)
        self.texto_ref = _transcribir(self.referencia)
        self.tts = Qwen3TTSModel.from_pretrained(modelo, device_map=device, dtype=torch.float32)
        self.prompt = self.tts.create_voice_clone_prompt(ref_audio=(self.referencia, 16000), ref_text=self.texto_ref)

    def decir(self, frases, estilos=None):   # Qwen3-TTS no acepta estilo al clonar
        wavs, self.sr = self.tts.generate_voice_clone(text=frases, language=["Spanish"] * len(frases),
                                                      voice_clone_prompt=self.prompt)
        return wavs


class VozExpresiva:
    """VoxCPM2 (OpenBMB, Apache 2.0): clona la voz y sigue un estilo escrito entre paréntesis antes de la frase."""

    def __init__(self, referencia, device="cpu", con_estilo=True):
        import tempfile
        from voxcpm import VoxCPM

        audio = cargar_audio(referencia)
        self.ref = Path(tempfile.mkdtemp()) / "referencia.wav"
        sf.write(self.ref, audio, 16000)
        self.texto_ref = _transcribir(audio)
        self.con_estilo = con_estilo
        self.tts = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False, optimize=False, device=device)
        self.sr = self.tts.tts_model.sample_rate

    def decir(self, frases, estilos=None):
        estilos = estilos if self.con_estilo and estilos else [None] * len(frases)
        return [self.tts.generate(text=f"({e}){f}" if e else f, reference_wav_path=str(self.ref),
                                  cfg_value=2.0, inference_timesteps=10)
                for f, e in zip(frases, estilos)]


def _transcribir(audio16k):
    return " ".join(s.text.strip() for s in _whisper().transcribe(audio16k, language="es")[0])


def _acelerar(w, sr, factor):
    """Cambia el ritmo sin cambiar el tono (atempo de ffmpeg)."""
    crudo = subprocess.run([FFMPEG, "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-",
                            "-af", f"atempo={factor}", "-f", "f32le", "-"],
                           input=np.asarray(w, np.float32).tobytes(), capture_output=True, check=True).stdout
    return np.frombuffer(crudo, np.float32)


# Subtítulos y control de calidad --------------------------------------------

_ASR = None


def _whisper():
    global _ASR
    if _ASR is None:
        from faster_whisper import WhisperModel
        _ASR = WhisperModel(ASR, device="cpu", compute_type="int8")
    return _ASR


@dataclass
class Narracion:
    audio: np.ndarray
    sr: int
    escenas: list            # (inicio, fin) en segundos de cada escena
    palabras: list = field(default_factory=list)   # (inicio, fin, palabra) de Whisper

    @property
    def duracion(self):
        return len(self.audio) / self.sr


def narrar(voz, guion, max_wer=0.25, reintentos=1, velocidad=1.0):
    """Narra cada escena; si Whisper no entiende bien una escena (WER alto), la vuelve a generar."""
    frases = [e["frase"] for e in guion["escenas"]]
    n = len(frases)
    estilos = [e.get("estilo") or ESTILOS["inicio" if i == 0 else "cierre" if i == n - 1 else "medio"]
               for i, e in enumerate(guion["escenas"])]
    wavs = voz.decir(frases, estilos)
    if velocidad != 1:
        wavs = [_acelerar(w, voz.sr, velocidad) for w in wavs]
    for intento in range(reintentos + 1):
        for e, w in zip(guion["escenas"], wavs):
            e["wer"] = _wer(e["frase"], _a16k(w, voz.sr))
        malas = [i for i, e in enumerate(guion["escenas"]) if e["wer"] > max_wer]
        if not malas or intento == reintentos:
            break
        for i, w in zip(malas, voz.decir([frases[i] for i in malas], [estilos[i] for i in malas])):
            wavs[i] = _acelerar(w, voz.sr, velocidad) if velocidad != 1 else w

    sr, partes, escenas, t = voz.sr, [np.zeros(int(INICIO * voz.sr), np.float32)], [], INICIO
    for w in wavs:
        w = np.asarray(w, np.float32)
        escenas.append((t, t + len(w) / sr))
        partes += [w, np.zeros(int(PAUSA * sr), np.float32)]
        t += len(w) / sr + PAUSA
    partes.append(np.zeros(int(FINAL * sr), np.float32))
    return Narracion(np.concatenate(partes), sr, escenas)


def _a16k(w, sr):
    w = np.asarray(w, np.float32)
    return np.interp(np.arange(0, len(w), sr / 16000), np.arange(len(w)), w).astype(np.float32)


def _normalizar(s):
    """Para comparar lo escrito con lo que oyó Whisper: números en palabras, sin tildes ni puntuación."""
    from num2words import num2words
    s = s.lower().replace("%", " por ciento")
    s = re.sub(r"(?<=\d)[,.](?=\d{3}\b)", "", s)
    s = re.sub(r"\d+", lambda m: num2words(int(m.group()), lang="es"), s)
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^\w\s]", " ", s).split())


def _wer(referencia, audio16k):
    import jiwer
    oido = " ".join(s.text for s in _whisper().transcribe(audio16k, language="es")[0])
    return jiwer.wer(_normalizar(referencia), _normalizar(oido)) if _normalizar(oido) else 1.0


def subtitulos(narracion, guion):
    """Palabras con tiempo. El texto sale del guion; Whisper solo aporta los tiempos.

    Así un error de Whisper (oír «dos mil dos» en vez de «dos mil doce», o repetir una frase)
    no llega a los subtítulos: se alinean las palabras del guion con las que oyó Whisper y las
    que no coinciden se reparten entre las vecinas según su largo.
    """
    import difflib

    contexto = " ".join(e["frase"] for e in guion["escenas"])
    segs, _ = _whisper().transcribe(_a16k(narracion.audio, narracion.sr), language="es",
                                    word_timestamps=True, initial_prompt=contexto)
    oidas = [(w.start, w.end, w.word.strip()) for s in segs for w in s.words if w.word.strip()]
    palabras = []
    for e, (ini, fin) in zip(guion["escenas"], narracion.escenas):
        guion_k = e["frase"].split()
        oidas_k = [w for w in oidas if ini - 0.2 <= w[0] < fin + 0.2]
        tiempos = [None] * len(guion_k)
        m = difflib.SequenceMatcher(None, [_normalizar(w) for w in guion_k], [_normalizar(w[2]) for w in oidas_k], autojunk=False)
        for a, b, n in m.get_matching_blocks():
            for j in range(n):
                tiempos[a + j] = oidas_k[b + j][:2]
        # anclas en los bordes de la escena y relleno proporcional al largo de cada palabra
        t0 = oidas_k[0][0] if oidas_k else ini
        t1 = oidas_k[-1][1] if oidas_k else fin
        k = 0
        while k < len(guion_k):
            if tiempos[k]:
                k += 1
                continue
            j = k
            while j < len(guion_k) and not tiempos[j]:
                j += 1
            desde = tiempos[k - 1][1] if k else t0
            hasta = tiempos[j][0] if j < len(guion_k) else t1
            largos = [len(w) + 1 for w in guion_k[k:j]]
            t = desde
            for q, l in zip(range(k, j), largos):
                paso = (hasta - desde) * l / sum(largos)
                tiempos[q] = (t, t + paso)
                t += paso
            k = j
        palabras += [(a, b, w) for (a, b), w in zip(tiempos, guion_k)]
    narracion.palabras = palabras
    return palabras


def _bloques(palabras, max_palabras=4, max_letras=24):
    """Agrupa palabras en bloques cortos para leer en el celular; corta en signos de puntuación."""
    bloques, actual = [], []
    for p in palabras:
        actual.append(p)
        largo = sum(len(x[2]) + 1 for x in actual)
        if len(actual) >= max_palabras or largo >= max_letras or p[2][-1] in ".,;:?!":
            bloques.append(actual)
            actual = []
    if actual:
        bloques.append(actual)
    return bloques


def a_srt(narracion, ruta):
    def hms(t):
        return f"{int(t // 3600):02}:{int(t % 3600 // 60):02}:{int(t % 60):02},{int(t % 1 * 1000):03}"
    lineas = []
    for i, b in enumerate(_bloques(narracion.palabras), 1):
        lineas += [str(i), f"{hms(b[0][0])} --> {hms(b[-1][1])}", " ".join(p[2] for p in b), ""]
    Path(ruta).write_text("\n".join(lineas), encoding="utf-8")


# Video ---------------------------------------------------------------------

ARIAL = {"normal": Path("C:/Windows/Fonts/arial.ttf"), "negrita": Path("C:/Windows/Fonts/arialbd.ttf")}


def _fuente(nombre, tam, peso):
    """Arial (normal hasta peso 500, negrita desde 600). Si no está instalada, Oswald y Public Sans."""
    arial = ARIAL["negrita" if peso >= 600 else "normal"]
    if arial.exists():
        return ImageFont.truetype(str(arial), tam)
    ruta = FUENTES / f"{nombre}.ttf"
    if not ruta.exists():   # Oswald y Public Sans, de Google Fonts (licencia OFL)
        import urllib.request
        FUENTES.mkdir(exist_ok=True)
        urllib.request.urlretrieve(f"https://github.com/google/fonts/raw/main/ofl/{nombre.lower()}/{nombre}%5Bwght%5D.ttf", ruta)
    f = ImageFont.truetype(str(ruta), tam)
    f.set_variation_by_axes([peso])
    return f


def _envolver(draw, texto, fuente, ancho):
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if draw.textlength(prueba, font=fuente) <= ancho:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    return lineas + [actual]


def _ajustar(draw, texto, nombre, peso, ancho, maximo, minimo=80):
    for tam in range(maximo, minimo, -10):
        f = _fuente(nombre, tam, peso)
        if draw.textlength(texto, font=f) <= ancho:
            return f
    return _fuente(nombre, minimo, peso)


def _espaciado(d, xy, texto, fuente, color, extra, anchor="la"):
    """Texto con espaciado entre letras (para títulos en mayúsculas); devuelve el ancho. Sin xy solo mide."""
    ancho = sum(d.textlength(c, font=fuente) + extra for c in texto) - extra
    if xy:
        x, y = xy
        for c in texto:
            d.text((x, y), c, font=fuente, fill=color, anchor=anchor)
            x += d.textlength(c, font=fuente) + extra
    return ancho


def _base(titulo, fuente_datos, autor):
    """Lo que no cambia en todo el video: título, aviso de IA y fuente. Capa transparente sobre el fondo."""
    img = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _espaciado(d, (MARGEN, 250), titulo.upper(), _fuente("PublicSans", 36, 700), ACENTO, 4)
    aviso = "VOZ GENERADA CON IA"
    f = _fuente("PublicSans", 24, 500)
    x1 = MARGEN + _espaciado(d, None, aviso, f, None, 2) + 40
    d.rounded_rectangle((MARGEN, 315, x1, 361), radius=23, outline=SUAVE, width=2)
    _espaciado(d, (MARGEN + 20, 338), aviso, f, SUAVE, 2, anchor="lm")
    pie = _fuente("PublicSans", 30, 400)
    texto = (f"{autor} · Fuente: {fuente_datos} · Gráficos: elaboración propia · "
             "Fotos: Wikimedia Commons · Música: generada por código")
    for i, linea in enumerate(_envolver(d, texto, pie, ANCHO - 2 * MARGEN)):
        d.text((MARGEN, 1500 + i * 44), linea, font=pie, fill=SUAVE)
    return img


# Música --------------------------------------------------------------------

def musica(duracion, sr=48000, bpm=84):
    """Fondo suave hecho con senos (acordes Am-F-C-G): no tiene derechos de autor que licenciar."""
    acordes = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]   # notas MIDI
    compas = 4 * 60 / bpm
    t = np.arange(int(duracion * sr)) / sr
    out = np.zeros_like(t)
    for k in range(int(duracion / compas) + 1):
        ini = k * compas
        m = (t >= ini) & (t < ini + compas + 1.0)
        tt = t[m] - ini
        env = np.minimum(1, tt / 0.8) * np.exp(-tt / 3.5)          # entrada lenta, cola larga
        for nota in acordes[k % 4]:
            f = 440 * 2 ** ((nota - 69) / 12)
            out[m] += env * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt))
        bajo = 440 * 2 ** ((acordes[k % 4][0] - 12 - 69) / 12)
        out[m] += 0.8 * env * np.sin(2 * np.pi * bajo * tt)
    fade = np.minimum(1, np.minimum(t / 1.5, (duracion - t) / 2.0))
    out *= np.clip(fade, 0, 1)
    return (0.9 * out / np.abs(out).max()).astype(np.float32), sr


def narracion_guardada(ruta, n_escenas):
    """Recupera una narración ya hecha: los cortes entre escenas son los silencios exactos (ceros) que puso narrar()."""
    audio, sr = sf.read(ruta, dtype="float32")
    cero = np.abs(audio) < 1e-7
    cambios = np.flatnonzero(np.diff(np.r_[0, cero.astype(np.int8), 0]))
    silencios = [(i, f) for i, f in zip(cambios[::2], cambios[1::2]) if (f - i) / sr >= 0.3]
    # el primero es el silencio inicial y el último el final; los del medio separan escenas
    bordes = [f for _, f in silencios[:-1]]
    finales = [i for i, _ in silencios[1:]]
    escenas = [(b / sr, e / sr) for b, e in zip(bordes, finales)]
    if len(escenas) != n_escenas:
        raise ValueError(f"se detectaron {len(escenas)} escenas en {ruta}, se esperaban {n_escenas}")
    return Narracion(audio, sr, escenas)


def renarrar(voz, guion, narracion, k, velocidad=1.0):
    """Vuelve a narrar solo la escena k (por ejemplo, si cambió su frase) y la inserta en la narración guardada."""
    e = guion["escenas"][k]
    w = np.asarray(voz.decir([e["frase"]])[0], np.float32)
    if velocidad != 1:
        w = _acelerar(w, voz.sr, velocidad)
    if voz.sr != narracion.sr:
        w = np.interp(np.arange(0, len(w), voz.sr / narracion.sr), np.arange(len(w)), w).astype(np.float32)
    e["wer"] = _wer(e["frase"], _a16k(w, narracion.sr))
    sr = narracion.sr
    ini, fin = narracion.escenas[k]
    audio = np.concatenate([narracion.audio[:int(ini * sr)], w, narracion.audio[int(fin * sr):]])
    delta = len(w) / sr - (fin - ini)
    escenas = [(a, b) if j < k else (ini, ini + len(w) / sr) if j == k else (a + delta, b + delta)
               for j, (a, b) in enumerate(narracion.escenas)]
    return Narracion(audio, sr, escenas)


def narracion_muda(guion, palabras_por_seg=2.6, sr=24000):
    """Tiempos estimados (sin voz) para revisar diseño y duración antes de correr el TTS."""
    escenas, palabras, t = [], [], INICIO
    for e in guion["escenas"]:
        ws = e["frase"].split()
        dur = len(ws) / palabras_por_seg
        paso = dur / len(ws)
        palabras += [(t + i * paso, t + (i + 1) * paso - 0.05, w) for i, w in enumerate(ws)]
        escenas.append((t, t + dur))
        t += dur + PAUSA
    audio = np.zeros(int((t + FINAL) * sr), np.float32)
    return Narracion(audio, sr, escenas, palabras)


CONTEO, BARRIDO = 0.9, 1.1   # segundos que tarda la cifra en contar y el gráfico en aparecer
PASOS_CONTEO = 18


def _suave(p):
    p = min(1.0, max(0.0, p))
    return 1 - (1 - p) ** 3


def _cifra_en(cifra, p):
    """La cifra a mitad de su conteo: «US$ 2,455 M» con p = 0.5 es «US$ 1,228 M»."""
    m = re.search(r"\d[\d,]*", cifra)
    if not m or p >= 1:
        return cifra
    n = int(m.group().replace(",", ""))
    v = round(n * p)
    txt = f"{v:,}" if "," in m.group() else str(v)
    return cifra[:m.start()] + txt + cifra[m.end():]


def _escena_con_imagen(e):
    """Cifra y etiqueta arriba y el gráfico debajo, separados para poder animarlos.

    Devuelve un dict: textos (una capa por paso del conteo), la imagen y dónde va.
    """
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    ancho = ANCHO - 2 * MARGEN
    f = _ajustar(tmp, e["cifra"], "Oswald", 700, ancho, 150) if e.get("cifra") else None
    fe = _fuente("PublicSans", 44 if e.get("cifra") else 60, 400 if e.get("cifra") else 700)
    fd = _fuente("PublicSans", 34, 400)
    lineas = _envolver(tmp, e["etiqueta"], fe, ancho)
    datos = _envolver(tmp, e["dato"], fd, ancho) if e.get("dato") else []
    alto_cifra = tmp.textbbox((0, 0), e["cifra"], font=f, anchor="lt")[3] + 18 if f else 0
    y0 = 400
    alto_txt = alto_cifra + len(lineas) * int(fe.size * 1.25) + (10 + len(datos) * int(fd.size * 1.3) if datos else 0)

    def capa_texto(p):
        capa = Image.new("RGBA", (ANCHO, alto_txt + 10), (0, 0, 0, 0))
        d = ImageDraw.Draw(capa)
        y = 0
        if f:
            d.text((MARGEN, y), _cifra_en(e["cifra"], p), font=f, fill=ACENTO, anchor="lt")
            y += alto_cifra
        for linea in lineas:
            d.text((MARGEN, y), linea, font=fe, fill=TEXTO, anchor="lt")
            y += int(fe.size * 1.25)
        if datos:   # dato de contexto, más chico; la raya naranja lo separa de la etiqueta
            y += 10
            d.rectangle((MARGEN, y + 4, MARGEN + 5, y + len(datos) * int(fd.size * 1.3) - 8), fill=ACENTO)
            for linea in datos:
                d.text((MARGEN + 22, y), linea, font=fd, fill=SUAVE, anchor="lt")
                y += int(fd.size * 1.3)
        return capa

    textos = [capa_texto(k / PASOS_CONTEO) for k in range(PASOS_CONTEO + 1)] if f else [capa_texto(1)]
    caja = (MARGEN - 30, y0 + alto_txt + 24, ANCHO - MARGEN + 30, 1250)   # hasta donde empiezan los subtítulos
    img = Image.open(AQUI / e["imagen"]).convert("RGB")
    # ocupa todo el espacio disponible (las capturas del dashboard se amplían hasta 1.6 veces)
    s = min((caja[2] - caja[0]) / img.width, (caja[3] - caja[1]) / img.height, 1.6)
    img = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
    # esquinas redondeadas: el gráfico queda como una tarjeta sobre la foto
    mascara = Image.new("L", img.size, 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=24, fill=255)
    img = img.convert("RGBA")
    img.putalpha(mascara)
    pos = ((ANCHO - img.width) // 2, caja[1] + (caja[3] - caja[1] - img.height) // 2)
    credito = None
    if e.get("credito_foto"):
        fc = _fuente("PublicSans", 24, 400)
        credito = Image.new("RGBA", (ANCHO, 40), (0, 0, 0, 0))
        ImageDraw.Draw(credito).text((ANCHO - MARGEN, 4), e["credito_foto"], font=fc, fill=SUAVE, anchor="ra")
    return {"textos": textos, "y_texto": y0, "img": img, "pos": pos, "credito": credito}


ZOOM_FONDO = 0.06


def _fondo(e):
    """Foto de la escena recortada a 9:16, desenfocada y oscurecida para que el texto se lea; o el color de fondo."""
    from PIL import ImageFilter
    w, h = int(ANCHO * (1 + ZOOM_FONDO)), int(ALTO * (1 + ZOOM_FONDO))
    if not e.get("foto"):
        return Image.new("RGB", (w, h), FONDO)
    foto = Image.open(AQUI / e["foto"]).convert("RGB")
    s = max(w / foto.width, h / foto.height)
    foto = foto.resize((int(foto.width * s) + 1, int(foto.height * s) + 1), Image.LANCZOS)
    x, y = (foto.width - w) // 2, (foto.height - h) // 2
    foto = foto.crop((x, y, x + w, y + h)).filter(ImageFilter.GaussianBlur(3))
    return Image.blend(foto, Image.new("RGB", (w, h), FONDO), 0.70)


def _fondo_en(fondo, q):
    """Zoom lento: q = 0 muestra la foto completa y q = 1 un 6 % más cerca."""
    W, H = fondo.size
    z = 1 + ZOOM_FONDO * min(1.0, max(0.0, q))
    w, h = int(W / z), int(H / z)
    x, y = (W - w) // 2, (H - h) // 2
    return fondo.crop((x, y, x + w, y + h)).resize((ANCHO, ALTO), Image.BILINEAR)


def _pegar_animada(img, esc, t, ini, fin, a):
    """Cifra que cuenta, gráfico que aparece de izquierda a derecha y un zoom lento durante la escena."""
    dy = int(40 * (1 - a))
    textos = esc["textos"]
    txt = textos[min(len(textos) - 1, int(_suave((t - ini) / CONTEO) * (len(textos) - 1)))]
    if a < 1:
        txt = txt.copy()
        txt.putalpha(txt.getchannel("A").point(lambda v: int(v * a)))
    img.paste(txt, (0, esc["y_texto"] + dy), txt)

    g = esc["img"]
    z = 1 + 0.04 * min(1.0, max(0.0, (t - ini) / max(fin - ini, 1)))   # zoom de 1.00 a 1.04
    if z > 1.001:
        w, h = g.size
        g = g.resize((int(w * z), int(h * z)), Image.BILINEAR)
        dx, dz = (g.width - w) // 2, (g.height - h) // 2
        g = g.crop((dx, dz, dx + w, dz + h))
    r = _suave((t - ini - 0.15) / BARRIDO)
    ancho = int(g.width * r)
    if ancho > 0:
        trozo = g.crop((0, 0, ancho, g.height))
        img.paste(trozo, (esc["pos"][0], esc["pos"][1] + dy), trozo)
    if esc.get("credito"):
        cr = esc["credito"]
        if a < 1:
            cr = cr.copy()
            cr.putalpha(cr.getchannel("A").point(lambda v: int(v * a)))
        img.paste(cr, (0, 1448), cr)


def _escena(e):
    """Capa transparente con la cifra grande y su etiqueta."""
    if e.get("imagen"):
        return _escena_con_imagen(e)
    capa = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    ancho = ANCHO - 2 * MARGEN
    def alto(texto, f):   # altura sobre la línea base
        return -d.textbbox((0, 0), texto, font=f, anchor="ls")[1]

    # (texto, fuente, color, alto, espacio después); el bloque se centra entre el aviso de IA y los subtítulos
    lineas = []
    if e.get("cifra"):
        f = _ajustar(d, e["cifra"], "Oswald", 700, ancho, 300)
        lineas.append((e["cifra"], f, TEXTO, alto(e["cifra"], f), 70))
        fe, color = _fuente("PublicSans", 58, 600), SUAVE
    else:
        fe, color = _fuente("Oswald", 104, 600), TEXTO
    lineas += [(x, fe, color, alto("H", fe), int(fe.size * 0.45)) for x in _envolver(d, e["etiqueta"], fe, ancho)]
    y = (420 + 1220 - sum(h + g for *_, h, g in lineas) + lineas[-1][4]) / 2
    for texto, f, color, h, g in lineas:
        y += h
        d.text((MARGEN, y), texto, font=f, fill=color, anchor="ls")
        y += g
    return capa


def _cuadro(base, capas, narracion, t, bloques, fuente_sub, fondos=None):
    # escena actual, con una entrada suave (aparece y sube) en sus primeros 0.35 s
    i = max([k for k, (ini, _) in enumerate(narracion.escenas) if ini - PAUSA <= t] or [0])
    a = min(1.0, max(0.0, (t - narracion.escenas[i][0] + PAUSA) / 0.35))
    if fondos:
        # fondo de la escena con zoom lento; al cambiar de escena, fundido con el anterior
        ini, fin = narracion.escenas[i]
        img = _fondo_en(fondos[i], (t - ini + PAUSA) / (fin - ini + 2 * PAUSA))
        if a < 1 and i > 0:
            pini, pfin = narracion.escenas[i - 1]
            img = Image.blend(_fondo_en(fondos[i - 1], (t - pini + PAUSA) / (pfin - pini + 2 * PAUSA)), img, a)
    else:
        img = Image.new("RGB", (ANCHO, ALTO), FONDO)
    img.paste(base, (0, 0), base)
    capa = capas[i]
    if isinstance(capa, dict):
        _pegar_animada(img, capa, t, *narracion.escenas[i], a)
    else:
        if a < 1:
            capa = capa.copy()
            capa.putalpha(capa.getchannel("A").point(lambda v: int(v * a)))
        img.paste(capa, (0, int(40 * (1 - a))), capa)

    d = ImageDraw.Draw(img)
    # barra de avance arriba, como en las historias
    d.rounded_rectangle((MARGEN, 180, ANCHO - MARGEN, 188), radius=4, fill=CAJA)
    d.rounded_rectangle((MARGEN, 180, MARGEN + (ANCHO - 2 * MARGEN) * t / narracion.duracion, 188), radius=4, fill=ACENTO)

    # subtítulo: el bloque que se está diciendo, con la palabra actual resaltada
    b = next((b for b in bloques if b[0][0] - 0.1 <= t <= b[-1][1] + 0.25), None)
    if b:
        texto = " ".join(p[2] for p in b)
        w = d.textlength(texto, font=fuente_sub)
        x, y = (ANCHO - w) / 2, 1290
        d.rounded_rectangle((x - 36, y - 26, x + w + 36, y + fuente_sub.size + 34), radius=28, fill=CAJA)
        for ini, fin, palabra in b:
            d.text((x, y), palabra, font=fuente_sub, fill=ACENTO if ini <= t <= fin + 0.05 else TEXTO)
            x += d.textlength(palabra + " ", font=fuente_sub)
    return img


def video(guion, narracion, ruta, fuente_datos, autor, volumen_musica=0.12):
    """Dibuja cada cuadro con Pillow y se los pasa a ffmpeg: voz a -14 LUFS y música unos 18 dB debajo."""
    ruta = Path(ruta)
    wav = ruta.with_suffix(".wav")
    sf.write(wav, narracion.audio, narracion.sr)
    wav_musica = ruta.with_name("musica.wav")
    sf.write(wav_musica, *musica(narracion.duracion))
    base = _base(guion["titulo"], fuente_datos, autor)
    capas = [_escena(e) for e in guion["escenas"]]
    fondos = [_fondo(e) for e in guion["escenas"]]
    bloques = _bloques(narracion.palabras)
    fuente_sub = _fuente("PublicSans", 58, 700)
    cmd = [FFMPEG, "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ANCHO}x{ALTO}", "-r", str(FPS), "-i", "-",
           "-i", str(wav), "-i", str(wav_musica),
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-filter_complex", f"[1:a]aresample=48000,loudnorm=I=-14:TP=-1.5:LRA=11[voz];"
                              f"[2:a]volume={volumen_musica}[mus];"
                              f"[voz][mus]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.89[a]",
           "-map", "0:v", "-map", "[a]", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
           "-shortest", "-movflags", "+faststart", str(ruta)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for k in range(int(narracion.duracion * FPS)):
        proc.stdin.write(_cuadro(base, capas, narracion, k / FPS, bloques, fuente_sub, fondos).tobytes())
    proc.stdin.close()
    proc.wait()
    return ruta


def portada(guion, narracion, ruta, fuente_datos, autor, escena=1):
    """Un cuadro fijo para revisar el diseño o usar como miniatura."""
    t = narracion.escenas[escena][0] + 1.0
    img = _cuadro(_base(guion["titulo"], fuente_datos, autor), [_escena(e) for e in guion["escenas"]],
                  narracion, t, _bloques(narracion.palabras), _fuente("PublicSans", 58, 700),
                  [_fondo(e) for e in guion["escenas"]])
    img.save(ruta)
    return ruta


def posts(guion, ruta):
    h = " ".join("#" + x.lstrip("#") for x in guion.get("hashtags", []))
    p = guion["posts"]
    Path(ruta).write_text(
        f"# {guion['titulo']}\n\n## LinkedIn\n\n{p['linkedin']}\n\n{h}\n\n"
        f"## X ({len(p['x'])} caracteres)\n\n{p['x']}\n\n## Facebook\n\n{p['facebook']}\n\n{h}\n",
        encoding="utf-8")
    return ruta
