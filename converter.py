import os, sys, subprocess, threading, time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional, Tuple

# ---------- Config ----------
IMG_EXT = {"png","jpg","jpeg","webp","bmp","tif","tiff","gif"}
VID_EXT = {"mp4","webm","avi","mov","mkv"}
ALL_EXT = sorted(list(IMG_EXT | VID_EXT))

IMG_FORMAT = {
    "png":"PNG","jpg":"JPEG","jpeg":"JPEG","webp":"WEBP",
    "bmp":"BMP","tif":"TIFF","tiff":"TIFF","gif":"GIF"
}

RATIO_OPTIONS = {
    "Original":None,"16:9":(16,9),"4:3":(4,3),"1:1":(1,1),
    "9:16":(9,16),"3:2":(3,2),"4:5":(4,5),
}

PRESET_OPTS = {
    "Alta":   {"x264":(26,"slow"),     "vp9":(38,2), "vt_bv":"6M",  "ab":"160k"},
    "Normal": {"x264":(30,"veryfast"), "vp9":(42,6), "vt_bv":"4M",  "ab":"128k"},
    "Rápido": {"x264":(34,"superfast"),"vp9":(46,8), "vt_bv":"2.5M","ab":"112k"},
}

# ---------- Helpers para subprocess no Windows  ----------
CREATE_NO_WINDOW = 0x08000000 if sys.platform.startswith("win") else 0

# Função: corre um comando e captura stdout/stderr 
def _run_no_window(cmd, **kwargs):
    # Condição: define pipes de saída por defeito
    kwargs.setdefault("stdout", subprocess.PIPE)
    kwargs.setdefault("stderr", subprocess.PIPE)
    kwargs.setdefault("text", True)
    # Condição: no Windows, esconde a janela do processo
    if sys.platform.startswith("win"):
        kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs.setdefault("startupinfo", si)
    return subprocess.run(cmd, **kwargs)

# Função: inicia um processo persistente e devolve Popen
def _popen_no_window(cmd, **kwargs):
    # Condição: define pipes e buffer line-based
    kwargs.setdefault("stdout", subprocess.PIPE)
    kwargs.setdefault("stderr", subprocess.STDOUT)
    kwargs.setdefault("text", True)
    kwargs.setdefault("bufsize", 1)
    # Condição: no Windows, esconde a janela do processo
    if sys.platform.startswith("win"):
        kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs.setdefault("startupinfo", si)
    return subprocess.Popen(cmd, **kwargs)

# ---------- FFmpeg paths ----------

# Função: gera diretórios candidatos onde o ffmpeg pode estar
def _candidate_dirs():
    # Condição: se for executável "frozen" (PyInstaller), tenta pasta do exe e _MEIPASS
    if getattr(sys, "frozen", False):
        yield os.path.dirname(sys.executable)
        base = getattr(sys, "_MEIPASS", None)
        if base: yield base
    # Condição: tenta diretório do script e subpasta ffmpeg-bin
    here = os.path.dirname(os.path.abspath(__file__))
    yield here
    yield os.path.join(here, "ffmpeg-bin")
    # Condição: tenta caminho do imageio-ffmpeg se existir
    try:
        import imageio_ffmpeg as i
        ff = i.get_ffmpeg_exe()
        yield os.path.dirname(ff)
    except Exception:
        pass
    # Condição: permite PATH do sistema
    yield ""

# Função: procura binário local no conjunto de diretórios candidatos
def _which_local(name: str) -> Optional[str]:
    for d in _candidate_dirs():
        cand = os.path.join(d, name) if d else name
        # Condição: encontrou nome exato
        if os.path.isfile(cand): return cand
        # Condição: no Windows, tenta sufixo .exe
        if sys.platform.startswith("win") and not name.lower().endswith(".exe"):
            cand_exe = (cand + ".exe") if d else (name + ".exe")
            if os.path.isfile(cand_exe): return cand_exe
    return None

# Função: devolve caminho do ffmpeg ou fallback "ffmpeg"
def ffmpeg_path() -> str:
    # Condição: tenta binários locais primeiro
    p = _which_local("ffmpeg") or _which_local("ffmpeg.exe")
    if p: return p
    # Condição: tenta imageio-ffmpeg
    try:
        import imageio_ffmpeg as i
        return i.get_ffmpeg_exe()
    except Exception:
        # Condição: fallback para comando no PATH
        return "ffmpeg"

# Função: devolve caminho do ffprobe ou fallback "ffprobe"
def ffprobe_path() -> str:
    ff = ffmpeg_path()
    base = os.path.dirname(ff) if os.path.isabs(ff) else ""
    # Condição: se souber a pasta do ffmpeg, tenta o ffprobe ao lado
    if base:
        cand = os.path.join(base, "ffprobe.exe" if sys.platform.startswith("win") else "ffprobe")
        if os.path.isfile(cand): return cand
    # Condição: tenta procurar localmente
    p = _which_local("ffprobe") or _which_local("ffprobe.exe")
    return p or "ffprobe"

# Função: valida existência de ffmpeg/ffprobe e aborta se faltarem
def check_binaries_or_die():
    # Função interna: testa se o binário responde a "-version"
    def _ok(bin_name: str) -> bool:
        try:
            r = _run_no_window([bin_name, "-version"])
            return r.returncode == 0
        except Exception:
            return False
    # Condição: falha se ffmpeg não existir
    if not _ok(ffmpeg_path()):
        sys.exit("FFmpeg não encontrado. Coloca ffmpeg(.exe) em ffmpeg-bin/ ou adiciona ao PATH.")
    # Condição: falha se ffprobe não existir
    if not _ok(ffprobe_path()):
        sys.exit("ffprobe não encontrado. Coloca ffprobe(.exe) em ffmpeg-bin/ ou instala FFmpeg completo.")

# ---------- Execução com progresso + ETA ----------

# Função: devolve duração do vídeo em segundos via ffprobe
def video_duration_seconds(path: str) -> float:
    r = _run_no_window([
        ffprobe_path(), "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ])
    out = (r.stdout or "").strip()
    # Condição: parse da duração ou 0.0 se falhar
    try:
        return float(out)
    except:
        return 0.0

# Função: formata segundos em HH:MM:SS
def _fmt_eta(s: float) -> str:
    s = max(0, int(round(s)))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"

# Função: corre ffmpeg com ficheiro temporário, lê progresso e permite cancelar
def run_ffmpeg_with_progress(cmd_base:list, final_out:str, on_progress=None, set_proc=None):
    """
    Escreve para tmp (video.part.mp4), emite (percent, eta_secs) e faz replace final.
    Suporta cancelamento via terminate()/kill().
    """
    out_dir = os.path.dirname(final_out) or "."
    os.makedirs(out_dir, exist_ok=True)
    base, ext = os.path.splitext(final_out)
    tmp_out = base + ".part" + ext if ext else final_out + ".part"

    # Condição: remove tmp antigo se existir
    try: os.remove(tmp_out)
    except FileNotFoundError: pass

    # Condição: remove '-loglevel' para garantir progress no Windows
    cleaned, skip = [], False
    for a in cmd_base:
        if skip: 
            skip=False
            continue
        if a == "-loglevel":
            skip = True
            continue
        cleaned.append(a)

    cmd = cleaned + ["-nostdin", "-progress", "pipe:1", tmp_out]
    proc = _popen_no_window(cmd)
    # Condição: expõe o processo ao chamador para cancelar
    if set_proc:
        set_proc(proc)

    duration = 0.0
    # Condição: tenta obter duração do input
    try:
        if "-i" in cleaned:
            i_idx = cleaned.index("-i")
            if i_idx + 1 < len(cleaned):
                duration = video_duration_seconds(cleaned[i_idx + 1])
    except Exception:
        pass
    t0 = time.time()

    canceled = False
    try:
        last_pct = -1
        # Condição: emite progresso inicial 0%
        if on_progress: on_progress(0, None)
        # Condição: lê linhas do progresso
        if proc.stdout:
            for line in proc.stdout:
                s = (line or "").strip()
                # Condição: quando há out_time_ms e conhecemos a duração, calcula percentagem
                if s.startswith("out_time_ms=") and duration > 0:
                    try:
                        ms = int(s.split("=",1)[1] or "0")
                        cur = ms/1_000_000.0
                        pct = int(min(100, max(0, round(cur/duration*100))))
                        eta = None
                        # Condição: calcula ETA apenas entre 1% e 99%
                        if 0 < pct < 100:
                            elapsed = time.time() - t0
                            eta = max(0.0, elapsed * (100 - pct) / pct)
                        # Condição: só atualiza se percentagem mudar
                        if pct != last_pct:
                            last_pct = pct
                            if on_progress: on_progress(pct, eta)
                    except:
                        pass
                # Condição: fim do progresso
                elif s.startswith("progress=") and s.endswith("end"):
                    if on_progress: on_progress(100, 0.0)
        ret = proc.wait()
        # Condição: se retorno diferente de zero, cancelou ou falhou
        if ret != 0:
            try: os.remove(tmp_out)
            except FileNotFoundError: pass
            if ret == -15 or ret == -9:
                canceled = True
            raise RuntimeError("Cancelado" if canceled else "FFmpeg falhou.")
        # Condição: sucesso — substitui ficheiro final
        os.replace(tmp_out, final_out)
    finally:
        # Condição: garante término do processo pendente
        try:
            if proc and proc.poll() is None:
                proc.terminate()
        except Exception:
            pass

# ---------- Utils ----------

# Função: identifica se o caminho é imagem, vídeo ou desconhecido
def detect_kind(path:str)->str:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    # Condição: extensão é de imagem
    if ext in IMG_EXT: return "image"
    # Condição: extensão é de vídeo
    if ext in VID_EXT: return "video"
    return ""

# Função: corre comando e devolve stdout como texto
def run_text(cmd:list)->str:
    r = _run_no_window(cmd)
    return r.stdout or ""

# Função: devolve dimensões de uma imagem respeitando rotação EXIF
def img_dims(path:str)->Tuple[int,int]:
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        return im.size

# Função: devolve dimensões do primeiro stream de vídeo
def vid_dims(path:str)->Tuple[int,int]:
    out = run_text([ffprobe_path(),"-v","error","-select_streams","v:0",
                    "-show_entries","stream=width,height","-of","csv=s=x:p=0",path]).strip()
    # Condição: falha se não vier no formato W x H
    if not out or "x" not in out:
        raise RuntimeError("Não encontrei stream de vídeo no ficheiro.")
    w_str, h_str = out.split("x", 1)
    # Condição: valida se são números
    if not w_str.isdigit() or not h_str.isdigit():
        raise RuntimeError(f"Dimensões inválidas do vídeo: '{out}'.")
    return int(w_str), int(h_str)

# Função: simplifica razão LxA pelo gcd
def simplify_ratio(w:int,h:int)->Tuple[int,int]:
    from math import gcd
    g = gcd(w,h)
    return (max(1,w//g), max(1,h//g))

# Função: constrói filtro de vídeo para manter/cortar aspeto conforme selecionado
def build_vf(ratio_key:str, tgt_W:int, tgt_H:int)->str:
    # Condição: se ratio "Original", ajusta dentro do alvo sem crop
    if ratio_key=="Original":
        return f"scale={tgt_W}:{tgt_H}:force_original_aspect_ratio=decrease"
    # Condição: caso contrário, expande e faz crop central
    return (f"scale={tgt_W}:{tgt_H}:force_original_aspect_ratio=increase,"
            f"crop={tgt_W}:{tgt_H}:(iw-{tgt_W})/2:(ih-{tgt_H})/2")

# Função: força valores pares (exigência de alguns encoders)
def even(v:int)->int:
    return v if v % 2 == 0 else v-1

# ---------- Encoders ----------

# Função: testa se o encoder existe no ffmpeg
def ff_has_encoder(name:str)->bool:
    out = run_text([ffmpeg_path(),"-hide_banner","-loglevel","error","-encoders"])
    return name in out

# Função: escolhe melhor encoder h264 por hardware disponível
def choose_hw_h264()->Optional[str]:
    plat = sys.platform
    # Condição: macOS com VideoToolbox
    if plat=="darwin" and ff_has_encoder("h264_videotoolbox"):
        return "h264_videotoolbox"
    # Condição: Windows tenta NVENC, QSV, AMF
    if plat.startswith("win"):
        for enc in ("h264_nvenc","h264_qsv","h264_amf"):
            if ff_has_encoder(enc): return enc
    # Condição: Linux tenta NVENC e QSV
    if plat.startswith("linux"):
        for enc in ("h264_nvenc","h264_qsv"):
            if ff_has_encoder(enc): return enc
    return None

# Função: devolve argumentos de encoding por hardware
def hw_encode_args(encoder:str, v_bitrate:str, a_bitrate:str):
    base = ["-c:v",encoder,"-pix_fmt","yuv420p","-c:a","aac","-b:a",a_bitrate,"-movflags","+faststart"]
    # Condição: VideoToolbox permite fallback a software e bitrate alvo
    if encoder == "h264_videotoolbox":
        return base + ["-allow_sw","1","-b:v", v_bitrate]
    # Condição: NVENC/QSV/AMF com bitrate alvo
    if encoder in ("h264_nvenc","h264_qsv","h264_amf"):
        return base + ["-b:v", v_bitrate]
    return None

# ---------- Conversões ----------

# Função: converte imagens com upscaling sempre permitido
def convert_image(src:str, dst:str, target_ext:str, tgt_W:int, tgt_H:int, ratio_key:str):
    from PIL import Image, ImageOps
    fmt = IMG_FORMAT.get(target_ext)
    # Condição: formato de imagem suportado
    if not fmt: raise ValueError(f"Formato de imagem não suportado: {target_ext}")

    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        sw, sh = im.size

        # Condição: ratio "Original" — encaixa com barras transparentes/preto
        if ratio_key == "Original":
            scale = min(tgt_W / sw, tgt_H / sh)
            new_w, new_h = max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))
            im = im.resize((new_w, new_h), Image.LANCZOS)

            # Condição: JPEG não suporta alpha, cria canvas RGB
            if fmt == "JPEG":
                canvas = Image.new("RGB", (tgt_W, tgt_H), (0, 0, 0))
                if im.mode in ("RGBA", "LA", "P"):
                    im = im.convert("RGB")
                x = (tgt_W - new_w) // 2
                y = (tgt_H - new_h) // 2
                canvas.paste(im, (x, y))
                out_img = canvas
            # Condição: formatos com alpha — cria canvas transparente
            else:
                canvas = Image.new("RGBA", (tgt_W, tgt_H), (0, 0, 0, 0))
                if im.mode not in ("RGBA", "LA"):
                    im = im.convert("RGBA")
                x = (tgt_W - new_w) // 2
                y = (tgt_H - new_h) // 2
                canvas.paste(im, (x, y), im)
                out_img = canvas
        # Condição: ratio diferente de "Original" — expande e corta ao centro
        else:
            scale = max(tgt_W / sw, tgt_H / sh)
            new_w, new_h = max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))
            im = im.resize((new_w, new_h), Image.LANCZOS)
            x = max(0, (new_w - tgt_W) // 2)
            y = max(0, (new_h - tgt_H) // 2)
            out_img = im.crop((x, y, x + tgt_W, y + tgt_H))

        # Condição: normaliza para RGB se for salvar como JPEG
        if fmt == "JPEG" and out_img.mode in ("RGBA", "LA", "P"):
            out_img = out_img.convert("RGB")
        kwargs = {"quality": 90, "optimize": True} if fmt == "JPEG" else {}
        out_img.save(dst, fmt, **kwargs)

# Função: converte vídeos com upscaling sempre permitido e progresso
def convert_video(src:str, dst:str, target_ext:str, tgt_W:int, tgt_H:int, ratio_key:str, quality:str, on_progress=None, set_proc=None):
    # Condição: verifica extensão alvo
    if target_ext not in VID_EXT:
        raise ValueError("Extensão de vídeo não suportada")
    p = PRESET_OPTS.get(quality, PRESET_OPTS["Normal"])
    x264_crf, x264_preset = p["x264"]
    vp9_crf, vp9_speed   = p["vp9"]
    vtbv, a_bitrate      = p["vt_bv"], p["ab"]
    sw,sh = vid_dims(src)

    # Condição: sempre permite upscaling, apenas força paridade
    tgt_W, tgt_H = even(tgt_W), even(tgt_H)
    # Condição: output não pode ser o mesmo ficheiro do input
    if os.path.abspath(src) == os.path.abspath(dst):
        raise ValueError("Output não pode ser o mesmo ficheiro do input.")
    # Condição: cópia direta se ratio=Original e resolução igual e contentor suportado
    can_copy = (ratio_key=="Original" and tgt_W==sw and tgt_H==sh and target_ext in {"mp4","mov","mkv","avi"})
    if can_copy:
        cmd = [ffmpeg_path(),"-y","-hide_banner","-i",src,"-map","0:v:0","-map","0:a:0?","-c:v","copy","-c:a","copy"]
        run_ffmpeg_with_progress(cmd, dst, on_progress, set_proc=set_proc)
        return
    vf = build_vf(ratio_key,tgt_W,tgt_H)
    base = [ffmpeg_path(),"-y","-hide_banner","-i",src,"-map","0:v:0","-map","0:a:0?","-sn","-vf",vf]
    # Condição: alvo webm usa VP9 + Opus
    if target_ext=="webm":
        cmd = base + ["-c:v","libvpx-vp9","-pix_fmt","yuv420p","-row-mt","1","-speed",str(vp9_speed),
                      "-deadline","realtime","-crf",str(vp9_crf),"-b:v","0","-threads","4",
                      "-c:a","libopus","-b:a",a_bitrate]
        run_ffmpeg_with_progress(cmd, dst, on_progress, set_proc=set_proc)
        return
    # Condição: tenta encoder por hardware se disponível
    hw = choose_hw_h264()
    if hw:
        cmd = base + hw_encode_args(hw, vtbv, a_bitrate)
        try:
            run_ffmpeg_with_progress(cmd, dst, on_progress, set_proc=set_proc)
            return
        except Exception:
            pass
    # Condição: fallback para libx264 software
    cmd = base + ["-c:v","libx264","-preset",x264_preset,"-crf",str(x264_crf),
                  "-pix_fmt","yuv420p","-c:a","aac","-b:a",a_bitrate,"-movflags","+faststart"]
    run_ffmpeg_with_progress(cmd, dst, on_progress, set_proc=set_proc)

# ---------- UI (Tkinter) ----------

# Classe: janela principal com UI e lógica de eventos
class App(tk.Tk):
    # Função: inicializa estado e constrói UI
    def __init__(self):
        super().__init__()
        self.title("Conversor")
        self.geometry("900x350")
        self.resizable(False, False)

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.ext_target = tk.StringVar(value="mp4")
        self.ratio = tk.StringVar(value="Original")
        self.quality = tk.StringVar(value="Normal")
        self.src_info = tk.StringVar(value="Sem ficheiro")

        # Condição: valores default de resolução
        self.res_w = tk.StringVar(value="1920")
        self.res_h = tk.StringVar(value="1080")

        # Condição: flags para sincronização de LxA
        self._syncing = False
        self._last_edited = "w"

        # Condição: checkbox para manter resolução original
        self.keep_src = tk.BooleanVar(value=False)

        self.src_w = None
        self.src_h = None

        # Condição: referência ao processo ffmpeg para cancelamento
        self._proc = None

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Button(frm, text="Escolher ficheiro", command=self.pick_file).grid(row=0, column=0, sticky="w")
        ttk.Label(frm, textvariable=self.src_info).grid(row=0, column=1, columnspan=6, sticky="w", padx=8)

        ttk.Label(frm, text="Formato de saída:").grid(row=1, column=0, sticky="w", pady=(10,0))
        self.ext_combo = ttk.Combobox(frm, textvariable=self.ext_target, values=list(VID_EXT), width=8, state="readonly")
        self.ext_combo.grid(row=1, column=1, sticky="w", padx=8, pady=(10,0))
        # Condição: atualiza extensão do caminho ao mudar no combo
        self.ext_combo.bind("<<ComboboxSelected>>", self.on_ext_change)

        ttk.Button(frm, text="Guardar como...", command=self.pick_save).grid(row=1, column=2, sticky="w", pady=(10,0))
        self.out_entry = ttk.Entry(frm, textvariable=self.output_path, width=49)
        self.out_entry.grid(row=1, column=3, columnspan=4, sticky="w", padx=8, pady=(10,0))

        ttk.Checkbutton(frm, text="Manter resolução original", variable=self.keep_src, command=self.apply_keep_src).grid(row=2, column=0, columnspan=2, sticky="w", pady=(10,0))

        ttk.Label(frm, text="Aspect Ratio:").grid(row=3, column=0, sticky="w", pady=(10,0))
        self.ratio_cb = ttk.Combobox(frm, textvariable=self.ratio, values=list(RATIO_OPTIONS.keys()), width=10, state="readonly")
        self.ratio_cb.grid(row=3, column=1, sticky="w", padx=8, pady=(10,0))
        # Condição: ao mudar ratio, volta a sincronizar dimensões
        self.ratio_cb.bind("<<ComboboxSelected>>", lambda e: self._sync_dims(self._last_edited))

        # Campo Largura
        ttk.Label(frm, text="Largura:").grid(row=3, column=2, sticky="w", pady=(10,0), padx=(12,4))
        self.res_w_entry = ttk.Entry(frm, textvariable=self.res_w, width=10)
        self.res_w_entry.grid(row=3, column=3, sticky="w", pady=(10,0), padx=(0,12))
        # Condição: ao editar largura, sincroniza altura
        self.res_w_entry.bind("<KeyRelease>", lambda e: (setattr(self, "_last_edited", "w"), self._sync_dims("w")))
        self.res_w_entry.bind("<FocusOut>",  lambda e: (setattr(self, "_last_edited", "w"), self._sync_dims("w")))

        # Campo Altura
        ttk.Label(frm, text="Altura:").grid(row=3, column=4, sticky="w", pady=(10,0), padx=(0,4))
        self.res_h_entry = ttk.Entry(frm, textvariable=self.res_h, width=10)
        self.res_h_entry.grid(row=3, column=5, sticky="w", pady=(10,0), padx=0)
        # Condição: ao editar altura, sincroniza largura
        self.res_h_entry.bind("<KeyRelease>", lambda e: (setattr(self, "_last_edited", "h"), self._sync_dims("h")))
        self.res_h_entry.bind("<FocusOut>",  lambda e: (setattr(self, "_last_edited", "h"), self._sync_dims("h")))

        ttk.Label(frm, text="Qualidade (vídeo):").grid(row=4, column=0, sticky="w", pady=(10,0))
        ttk.Combobox(frm, textvariable=self.quality, values=list(PRESET_OPTS.keys()), width=10, state="readonly").grid(row=4, column=1, sticky="w", padx=8, pady=(10,0))

        self.btn_convert = ttk.Button(frm, text="Converter", command=self.on_convert)
        self.btn_convert.grid(row=5, column=0, sticky="w", pady=(16,0))

        # Botão: cancelar conversão em curso
        self.btn_cancel = ttk.Button(frm, text="Cancelar", command=self.on_cancel, state="disabled")
        self.btn_cancel.grid(row=5, column=1, sticky="w", pady=(16,0), padx=(8,0))

        self.status = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.status).grid(row=5, column=2, columnspan=5, sticky="w", padx=8, pady=(16,0))

        # Barra de progresso + percentagem
        pfrm = ttk.Frame(frm)
        pfrm.grid(row=6, column=0, columnspan=7, sticky="w", pady=(8,0))

        self.pbar = ttk.Progressbar(
            pfrm,
            orient="horizontal",
            mode="determinate",
            length=520,
            maximum=100,
        )
        self.pbar.pack(side="left")

        self.pbar_lbl = tk.StringVar(value="")
        ttk.Label(pfrm, textvariable=self.pbar_lbl).pack(side="left", padx=8)   

        # ETA estimado
        self.eta_lbl = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.eta_lbl, foreground="#555").grid(row=7, column=0, columnspan=7, sticky="w", pady=(4,0))

        # Condição: colunas sem expansão automática
        for c in range(7):
            frm.columnconfigure(c, weight=0)

        # Condição: sincronização inicial e aplicação do "manter original"
        self._sync_dims("w")
        self.apply_keep_src()

    # Função: devolve par (num, den) do aspeto atual
    def _get_aspect(self) -> Optional[Tuple[int,int]]:
        key = self.ratio.get()
        # Condição: se "Original" e temos src_w/h, simplifica aspeto da origem
        if key == "Original":
            if self.src_w and self.src_h and self.src_w > 0 and self.src_h > 0:
                from math import gcd
                g = gcd(self.src_w, self.src_h)
                return (self.src_w // g, self.src_h // g)
            return None
        return RATIO_OPTIONS.get(key)

    # Função: sincroniza LxA mantendo aspeto, com base no último campo editado
    def _sync_dims(self, from_field: str):
        # Condição: evita reentrância ou se "manter original" estiver ativo
        if self._syncing or self.keep_src.get():
            return
        asp = self._get_aspect()
        # Condição: sem aspeto válido, não altera
        if not asp:
            return
        num, den = asp
        try:
            if from_field == "w":
                w_txt = self.res_w.get().strip()
                # Condição: ignora se não for número
                if not w_txt.isdigit(): return
                w = int(w_txt)
                # Condição: ignora se não positivo
                if w <= 0: return
                h = max(1, int(round(w * den / num)))
                self._syncing = True
                self.res_h.set(str(h))
            else:
                h_txt = self.res_h.get().strip()
                # Condição: ignora se não for número
                if not h_txt.isdigit(): return
                h = int(h_txt)
                # Condição: ignora se não positivo
                if h <= 0: return
                w = max(1, int(round(h * num / den)))
                self._syncing = True
                self.res_w.set(str(w))
        finally:
            self._syncing = False

    # Função: atualiza progresso na UI de forma segura (thread principal)
    def ui_progress_safe(self, pct: int, eta_secs: Optional[float]):
        self.after(0, lambda: self._ui_progress_main(pct, eta_secs))

    # Função: aplica valores de progresso no main thread
    def _ui_progress_main(self, pct: int, eta_secs: Optional[float]):
        self.pbar["value"] = pct
        self.pbar_lbl.set(f"{pct}%")
        self.eta_lbl.set("" if eta_secs is None else f"Tempo restante ~ {_fmt_eta(eta_secs)}")

    # Função: sugere caminho de saída baseado no input e extensão
    def suggest_output_path(self, in_path: str, ext: str) -> str:
        base = os.path.splitext(os.path.basename(in_path))[0]
        folder = os.path.dirname(in_path)
        return os.path.join(folder, f"{base}_out.{ext}")

    # Função: ajusta as opções do combo de formato conforme tipo do ficheiro
    def set_ext_combo_values_for_kind(self, kind: str):
        if kind == "image":
            vals = sorted(list(IMG_EXT))
        elif kind == "video":
            vals = sorted(list(VID_EXT))
        else:
            vals = list(ALL_EXT)
        self.ext_combo["values"] = vals

    # Função: ativa/desativa campos quando "manter resolução original" está ativo
    def apply_keep_src(self):
        keep = self.keep_src.get()
        # Condição: desabilita inputs e combo de ratio quando ativo
        state = "disabled" if keep else "normal"
        self.res_w_entry.config(state=state)
        self.res_h_entry.config(state=state)
        self.ratio_cb.config(state="disabled" if keep else "readonly")
        # Condição: ao ativar e já termos dimensões de origem, força esses valores
        if keep and self.src_w and self.src_h:
            self.ratio.set("Original")
            self.res_w.set(str(self.src_w))
            self.res_h.set(str(self.src_h))

    # Função: abre dialog de ficheiro e preenche estado inicial
    def pick_file(self):
        path = filedialog.askopenfilename(
            title="Escolher ficheiro",
            filetypes=[("Imagens/Vídeos", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.gif *.mp4 *.webm *.avi *.mov *.mkv"),
                       ("Todos", "*.*")]
        )
        # Condição: cancelou seleção
        if not path:
            return
        self.input_path.set(path)
        kind = detect_kind(path)
        try:
            # Condição: mede dimensões conforme o tipo
            if kind=="image":
                self.src_w, self.src_h = img_dims(path)
            elif kind=="video":
                self.src_w, self.src_h = vid_dims(path)
            else:
                raise ValueError("Tipo não suportado")

            self.src_info.set(f"{os.path.basename(path)} — {kind} {self.src_w}x{self.src_h}")
            self.set_ext_combo_values_for_kind(kind)

            cur_ext = os.path.splitext(path)[1].lower().lstrip(".")
            # Condição: default de vídeo para mp4
            if kind=="video":
                new_ext = "mp4"
            # Condição: para imagens mantém jpg como default
            else:
                new_ext = "jpg" if cur_ext not in ("jpg","jpeg") else "jpg"
            self.ext_target.set(new_ext)

            # Condição: preenche resolução a partir da origem
            self.res_w.set(str(self.src_w))
            self.res_h.set(str(self.src_h))
            self._sync_dims("w")
            self.apply_keep_src()

            out_now = self.output_path.get().strip()
            # Condição: atualiza extensão do caminho de saída
            if out_now:
                folder = os.path.dirname(out_now)
                base = os.path.splitext(os.path.basename(out_now))[0]
                self.output_path.set(os.path.join(folder, f"{base}.{new_ext}"))
            else:
                self.output_path.set(self.suggest_output_path(path, new_ext))

        except Exception as e:
            # Condição: erro ao ler dimensões — limpa estado e avisa
            self.src_w = self.src_h = None
            self.src_info.set("Erro ao ler dimensões")
            messagebox.showerror("Erro", str(e))

    # Função: abre dialog para escolher caminho de saída
    def pick_save(self):
        ext = self.ext_target.get().lower().strip()
        # Condição: exige extensão selecionada
        if not ext:
            messagebox.showerror("Erro", "Escolhe o formato de saída.")
            return
        out = filedialog.asksaveasfilename(
            title="Guardar como",
            defaultextension=f".{ext}",
            filetypes=[(f".{ext}", f"*.{ext}"), ("Todos", "*.*")]
        )
        # Condição: apenas aplica se não cancelou
        if out:
            self.output_path.set(out)

    # Função: sincroniza extensão do caminho de saída quando muda o combo
    def on_ext_change(self, event=None):
        ext = self.ext_target.get().strip().lower()
        out = self.output_path.get().strip()
        # Condição: só muda se já houver caminho
        if out:
            folder = os.path.dirname(out)
            base = os.path.splitext(os.path.basename(out))[0]
            self.output_path.set(os.path.join(folder, f"{base}.{ext}"))

    # Função: lê LxA dos campos e valida números positivos
    def _read_dims(self) -> Optional[Tuple[int,int]]:
        w_txt = self.res_w.get().strip()
        h_txt = self.res_h.get().strip()
        # Condição: ambos têm de ser dígitos
        if not w_txt.isdigit() or not h_txt.isdigit():
            return None
        w = int(w_txt); h = int(h_txt)
        # Condição: têm de ser positivos
        if w <= 0 or h <= 0:
            return None
        return w, h

    # Função: tenta cancelar o processo ffmpeg em curso
    def on_cancel(self):
        p = self._proc
        # Condição: se existir processo ativo, envia terminate e kill de segurança
        if p and p.poll() is None:
            try:
                p.terminate()
                self.after(1000, lambda: (p.kill() if p.poll() is None else None))
            except Exception:
                pass

    # Função: prepara UI antes de uma operação longa
    def _before_long_task(self):
        self.btn_convert.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.status.set("A converter...")
        self.eta_lbl.set("")
        self.pbar["value"] = 0
        self.pbar_lbl.set("")
        self.pbar.config(mode="determinate")

    # Função: repõe UI após terminar a operação longa
    def _after_long_task(self):
        self.btn_convert.config(state="normal")
        self.btn_cancel.config(state="disabled")
        self._proc = None
        try: self.pbar.stop()
        except Exception: pass
        self.pbar["value"] = 0
        self.pbar_lbl.set("")
        self.eta_lbl.set("")
        self.pbar.config(mode="determinate")

    # Função: valida inputs e inicia conversão em thread
    def on_convert(self):
        check_binaries_or_die()

        inp = self.input_path.get().strip()
        out = self.output_path.get().strip()
        ext = self.ext_target.get().strip().lower()
        # Condição: tem de haver ficheiro de entrada válido
        if not inp or not os.path.isfile(inp):
            messagebox.showerror("Erro", "Escolhe um ficheiro válido.")
            return
        # Condição: tem de haver destino
        if not out:
            messagebox.showerror("Erro", "Define o ficheiro de saída.")
            return
        # Condição: tem de haver extensão alvo
        if not ext:
            messagebox.showerror("Erro", "Escolhe o formato de saída.")
            return
        # Condição: input e output não podem coincidir
        if os.path.abspath(inp) == os.path.abspath(out):
            messagebox.showerror("Erro", "O ficheiro de saída não pode ser o mesmo que o de entrada.")
            return

        dims = self._read_dims()
        # Condição: validação de LxA
        if not dims:
            messagebox.showerror("Erro", "Largura/Altura inválidas. Usa inteiros positivos.")
            return
        tgt_W, tgt_H = dims

        # Condição: quando mantém resolução original, força usar src_w/src_h e ratio Original
        if self.keep_src.get():
            if not (self.src_w and self.src_h):
                messagebox.showerror("Erro", "Dimensões de origem desconhecidas.")
                return
            tgt_W, tgt_H = self.src_w, self.src_h
            self.ratio.set("Original")

        ratio = self.ratio.get()
        quality = self.quality.get()

        base_out, cur_ext = os.path.splitext(out)
        # Condição: garante que a extensão do caminho bate com a escolhida
        if not cur_ext or cur_ext.lower().lstrip(".") != ext:
            out = f"{base_out}.{ext}"
            self.output_path.set(out)

        kind = detect_kind(inp)
        # Condição: só suporta imagem ou vídeo
        if kind not in {"image","video"}:
            messagebox.showerror("Erro", "Tipo de ficheiro não suportado.")
            return
        # Condição: não converte vídeo para imagem
        if kind == "video" and ext in IMG_EXT:
            messagebox.showerror("Erro", "Converter vídeo para imagem não é suportado aqui.")
            return
        # Condição: não converte imagem para vídeo
        if kind == "image" and ext in VID_EXT:
            messagebox.showerror("Erro", "Converter imagem para vídeo não é suportado aqui.")
            return

        # Condição: confirma overwrite se destino já existir
        if os.path.exists(out):
            if not messagebox.askyesno("Confirmar", "O ficheiro de saída já existe. Substituir?"):
                return

        self._before_long_task()

        # Função interna: corre conversão em thread e atualiza UI de forma segura
        def _task():
            try:
                if kind=="image":
                    # Condição: imagens usam progress indeterminado
                    self.pbar.config(mode="indeterminate")
                    self.after(0, self.pbar.start, 10)
                    convert_image(inp, out, ext, tgt_W, tgt_H, ratio)
                else:
                    # Condição: vídeos usam progress determinado com ETA
                    self.pbar.config(mode="determinate")
                    self.ui_progress_safe(0, None)
                    convert_video(
                        inp, out, ext, tgt_W, tgt_H, ratio, quality,
                        on_progress=lambda p, eta: self.ui_progress_safe(p, eta),
                        set_proc=lambda pr: setattr(self, "_proc", pr)
                    )
                self.after(0, lambda: self.status.set(f"OK: {out}"))
                self.after(0, lambda: messagebox.showinfo("Concluído", f"Conversão concluída:\n{out}"))
            except Exception as e:
                self.after(0, lambda: self.status.set("Falhou"))
                # Condição: mensagem específica se foi cancelado
                msg = "Conversão cancelada." if "Cancelado" in str(e) else str(e)
                self.after(0, lambda: messagebox.showerror("Erro", msg))
            finally:
                self.after(0, self._after_long_task)

        threading.Thread(target=_task, daemon=True).start()

# ---------- arrancar ----------
# Condição: se correr como script principal, abre a app
if __name__ == "__main__":
    app = App()
    app.mainloop()

# Executar o programa:
#   macOS:
#     source .venv/bin/activate
#     python converter.py
#   Windows:
#     .\.venv\Scripts\Activate.ps1
#     python converter.py
