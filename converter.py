#dependencies:
# python3 -m venv .venv
# pip install pillow imageio-ffmpeg
# brew install ffmpeg
# primeira vez apenas


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
    "Alta":   {"x264":(20,"slow"),     "vp9":(30,2), "vt_bv":"8M", "ab":"192k"},
    "Normal": {"x264":(23,"veryfast"), "vp9":(35,6), "vt_bv":"5M", "ab":"160k"},
    "Rápido": {"x264":(28,"superfast"),"vp9":(40,8), "vt_bv":"3M", "ab":"128k"},
}

RES_PRESETS = [
    (3840,2160), (2560,1440), (1920,1080),
    (1600,1200), (1440,1080), (1280,720),
    (1280,960),  (1024,768),  (854,480),
    (800,600),   (640,360),   (426,240)
]

# ---------- FFmpeg paths ----------
def ffmpeg_path()->str:
    try:
        import imageio_ffmpeg as i
        return i.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"

def ffprobe_path()->str:
    try:
        import imageio_ffmpeg as i
        ff = i.get_ffmpeg_exe()
        base = os.path.dirname(ff)
        probe = "ffprobe.exe" if sys.platform.startswith("win") else "ffprobe"
        cand = os.path.join(base, probe)
        return cand if os.path.isfile(cand) else "ffprobe"
    except Exception:
        return "ffprobe"

def check_binaries_or_die():
    def _ok(bin_name):
        try:
            subprocess.run([bin_name, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except Exception:
            return False
    if not _ok(ffmpeg_path()):
        sys.exit("FFmpeg não encontrado. Instala e adiciona ao PATH.")
    if not _ok(ffprobe_path()):
        sys.exit("ffprobe não encontrado. Instala FFmpeg (inclui ffprobe).")

# ---------- Execução com progresso + ETA ----------
def video_duration_seconds(path: str) -> float:
    cmd = [
        ffprobe_path(), "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except:
        return 0.0

def _fmt_eta(s: float) -> str:
    # formata segundos em hh:mm:ss
    s = max(0, int(round(s)))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"

def run_ffmpeg_with_progress(cmd_base:list, final_out:str, on_progress=None):
    """
    Escreve para tmp (video.part.mp4), emite (percent, eta_secs) e faz replace final.
    """
    out_dir = os.path.dirname(final_out) or "."
    os.makedirs(out_dir, exist_ok=True)
    base, ext = os.path.splitext(final_out)
    tmp_out = base + ".part" + ext if ext else final_out + ".part"

    try: os.remove(tmp_out)
    except FileNotFoundError: pass

    cmd = cmd_base + ["-nostdin", "-progress", "pipe:1", tmp_out]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    # duração alvo e cronómetro
    duration = 0.0
    try:
        if "-i" in cmd:
            i_idx = cmd.index("-i")
            if i_idx + 1 < len(cmd):
                duration = video_duration_seconds(cmd[i_idx + 1])
    except Exception:
        pass
    t0 = time.time()

    try:
        last_pct = -1
        if on_progress: on_progress(0, None)
        if proc.stdout:
            for line in proc.stdout:
                s = line.strip()
                if s.startswith("out_time_ms=") and duration > 0:
                    # deriva percentagem pelo tempo processado vs duração
                    try:
                        ms = int(s.split("=",1)[1] or "0")
                        cur = ms/1_000_000.0
                        pct = int(min(100, max(0, round(cur/duration*100))))
                        # ETA por extrapolação linear do tempo decorrido
                        eta = None
                        if pct > 0 and pct < 100:
                            elapsed = time.time() - t0
                            eta = max(0.0, elapsed * (100 - pct) / pct)
                        if pct != last_pct:
                            last_pct = pct
                            if on_progress: on_progress(pct, eta)
                    except:
                        pass
                elif s.startswith("progress=") and s.endswith("end"):
                    if on_progress: on_progress(100, 0.0)
        ret = proc.wait()
        if ret != 0:
            try: os.remove(tmp_out)
            except FileNotFoundError: pass
            raise RuntimeError("FFmpeg falhou.")
        os.replace(tmp_out, final_out)
    finally:
        try:
            if proc and proc.poll() is None:
                proc.terminate()
        except Exception:
            pass

# ---------- Utils ----------
def detect_kind(path:str)->str:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in IMG_EXT: return "image"
    if ext in VID_EXT: return "video"
    return ""

def run_text(cmd:list)->str:
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.stdout

def img_dims(path:str)->Tuple[int,int]:
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        return im.size

def vid_dims(path:str)->Tuple[int,int]:
    out = run_text([ffprobe_path(),"-v","error","-select_streams","v:0",
                    "-show_entries","stream=width,height","-of","csv=s=x:p=0",path]).strip()
    if "x" not in out: raise RuntimeError("Não consegui ler dimensões do vídeo")
    w,h = out.split("x"); return int(w), int(h)

def parse_res(s:str)->Optional[Tuple[int,int]]:
    try:
        w,h = s.lower().replace(" ","").split("x"); return int(w), int(h)
    except: return None

def simplify_ratio(w:int,h:int)->Tuple[int,int]:
    from math import gcd
    g = gcd(w,h)
    return (max(1,w//g), max(1,h//g))

def fit_preset_to_ratio_within(preset_w:int, preset_h:int, num:int, den:int)->Optional[Tuple[int,int]]:
    h1 = int(round(preset_w * den / num))
    if 1 <= h1 <= preset_h:
        return preset_w, h1
    w2 = int(round(preset_h * num / den))
    if 1 <= w2 <= preset_w:
        return w2, preset_h
    return None

def make_res_list_for_source(src_w:int, src_h:int, ratio_key:str, allow_upscale:bool)->list:
    if not src_w or not src_h:
        return []
    vals = set()
    def add(w, h):
        if allow_upscale or (w <= src_w and h <= src_h):
            if w > 0 and h > 0:
                vals.add(f"{int(w)}x{int(h)}")
    if ratio_key == "Original":
        src_num, src_den = simplify_ratio(src_w, src_h)
        for W, H in RES_PRESETS:
            for w, h in ((W, H), (H, W)):
                n, d = simplify_ratio(w, h)
                if (n, d) == (src_num, src_den):
                    add(w, h)
        if not vals or (len(vals) == 1 and f"{src_w}x{src_h}" in vals):
            for f in (0.90, 0.75, 2/3, 0.5, 1/3):
                w = int(round(src_w * f))
                h = int(round(w * src_den / src_num))
                add(w, h)
        if allow_upscale:
            have_above = any(int(v.split("x")[0]) > src_w for v in vals)
            if not have_above:
                for f in (1.25, 1.5, 2.0):
                    w = int(round(src_w * f))
                    h = int(round(w * src_den / src_num))
                    add(w, h)
        add(src_w, src_h)
    else:
        num, den = (RATIO_OPTIONS[ratio_key])
        for W, H in RES_PRESETS:
            for cw, ch in ((W, H), (H, W)):
                fit = fit_preset_to_ratio_within(cw, ch, num, den)
                if fit:
                    add(*fit)
    return sorted(vals, key=lambda s: int(s.split("x")[0]), reverse=True)

def build_vf(ratio_key:str, tgt_W:int, tgt_H:int)->str:
    if ratio_key=="Original":
        return f"scale={tgt_W}:{tgt_H}:force_original_aspect_ratio=decrease"
    return (f"scale={tgt_W}:{tgt_H}:force_original_aspect_ratio=increase,"
            f"crop={tgt_W}:{tgt_H}:(iw-{tgt_W})/2:(ih-{tgt_H})/2")

def even(v:int)->int:
    return v if v % 2 == 0 else v-1

# ---------- Encoders ----------
def ff_has_encoder(name:str)->bool:
    out = run_text([ffmpeg_path(),"-hide_banner","-loglevel","error","-encoders"])
    return name in out

def choose_hw_h264()->Optional[str]:
    plat = sys.platform
    if plat=="darwin" and ff_has_encoder("h264_videotoolbox"):
        return "h264_videotoolbox"
    if plat.startswith("win"):
        for enc in ("h264_nvenc","h264_qsv","h264_amf"):
            if ff_has_encoder(enc): return enc
    if plat.startswith("linux"):
        for enc in ("h264_nvenc","h264_qsv"):
            if ff_has_encoder(enc): return enc
    return None

def hw_encode_args(encoder:str, v_bitrate:str, a_bitrate:str):
    base = ["-c:v",encoder,"-pix_fmt","yuv420p","-c:a","aac","-b:a",a_bitrate,"-movflags","+faststart"]
    if encoder == "h264_videotoolbox":
        return base + ["-allow_sw","1","-b:v", v_bitrate]
    if encoder in ("h264_nvenc","h264_qsv","h264_amf"):
        return base + ["-b:v", v_bitrate]
    return None

# ---------- Conversões ----------
def convert_image(src:str, dst:str, target_ext:str, tgt_W:int, tgt_H:int, ratio_key:str, allow_upscale:bool):
    from PIL import Image, ImageOps
    fmt = IMG_FORMAT.get(target_ext)
    if not fmt: raise ValueError(f"Formato de imagem não suportado: {target_ext}")
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        sw,sh = im.size
        if ratio_key=="Original":
            scale = min(tgt_W/sw, tgt_H/sh)
            if not allow_upscale: scale = min(1.0, scale)
            new_w, new_h = max(1,int(sw*scale)), max(1,int(sh*scale))
            im = im.resize((new_w,new_h), Image.LANCZOS)
        else:
            scale = max(tgt_W/sw, tgt_H/sh)
            if not allow_upscale: scale = min(scale, 1.0)
            new_w, new_h = max(1,int(sw*scale)), max(1,int(sh*scale))
            im = im.resize((new_w,new_h), Image.LANCZOS)
            x = max(0, (new_w - tgt_W)//2)
            y = max(0, (new_h - tgt_H)//2)
            im = im.crop((x, y, x + tgt_W, y + tgt_H))
        if fmt=="JPEG" and im.mode in ("RGBA","LA","P"):
            im = im.convert("RGB")
        kwargs = {"quality":90,"optimize":True} if fmt=="JPEG" else {}
        im.save(dst, fmt, **kwargs)

def convert_video(src:str, dst:str, target_ext:str, tgt_W:int, tgt_H:int, ratio_key:str, quality:str, allow_upscale:bool, on_progress=None):
    if target_ext not in VID_EXT:
        raise ValueError("Extensão de vídeo não suportada")
    p = PRESET_OPTS.get(quality, PRESET_OPTS["Normal"])
    x264_crf, x264_preset = p["x264"]
    vp9_crf, vp9_speed   = p["vp9"]
    vtbv, a_bitrate      = p["vt_bv"], p["ab"]
    sw,sh = vid_dims(src)
    if not allow_upscale:
        tgt_W, tgt_H = min(tgt_W, sw), min(tgt_H, sh)
    tgt_W, tgt_H = even(tgt_W), even(tgt_H)
    if os.path.abspath(src) == os.path.abspath(dst):
        raise ValueError("Output não pode ser o mesmo ficheiro do input.")
    can_copy = (ratio_key=="Original" and tgt_W==sw and tgt_H==sh and target_ext in {"mp4","mov","mkv","avi"})
    if can_copy:
        cmd = [ffmpeg_path(),"-y","-hide_banner","-loglevel","error","-i",src,"-map","0:v:0","-map","0:a:0?","-c:v","copy","-c:a","copy"]
        run_ffmpeg_with_progress(cmd, dst, on_progress)
        return
    vf = build_vf(ratio_key,tgt_W,tgt_H)
    base = [ffmpeg_path(),"-y","-hide_banner","-loglevel","error",
            "-i",src,"-map","0:v:0","-map","0:a:0?","-sn","-vf",vf]
    if target_ext=="webm":
        cmd = base + ["-c:v","libvpx-vp9","-pix_fmt","yuv420p","-row-mt","1","-speed",str(vp9_speed),
                      "-deadline","realtime","-crf",str(vp9_crf),"-b:v","0","-threads","4",
                      "-c:a","libopus","-b:a",a_bitrate]
        run_ffmpeg_with_progress(cmd, dst, on_progress)
        return
    hw = choose_hw_h264()
    if hw:
        cmd = base + hw_encode_args(hw, vtbv, a_bitrate)
        try:
            run_ffmpeg_with_progress(cmd, dst, on_progress)
            return
        except Exception:
            pass  # fallback CPU
    cmd = base + ["-c:v","libx264","-preset",x264_preset,"-crf",str(x264_crf),
                  "-pix_fmt","yuv420p","-c:a","aac","-b:a",a_bitrate,"-movflags","+faststart"]
    run_ffmpeg_with_progress(cmd, dst, on_progress)

# ---------- UI (Tkinter) ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Conversor")
        self.geometry("820x390")
        self.resizable(False, False)

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.ext_target = tk.StringVar(value="mp4")
        self.res_text = tk.StringVar(value="1920x1080")
        self.ratio = tk.StringVar(value="Original")
        self.quality = tk.StringVar(value="Normal")
        self.allow_up = tk.BooleanVar(value=False)
        self.src_info = tk.StringVar(value="Sem ficheiro")

        self.src_w = None
        self.src_h = None

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Button(frm, text="Escolher ficheiro", command=self.pick_file).grid(row=0, column=0, sticky="w")
        ttk.Label(frm, textvariable=self.src_info).grid(row=0, column=1, columnspan=4, sticky="w", padx=8)

        ttk.Label(frm, text="Formato de saída:").grid(row=1, column=0, sticky="w", pady=(10,0))
        self.ext_combo = ttk.Combobox(frm, textvariable=self.ext_target, values=list(VID_EXT), width=8, state="readonly")
        self.ext_combo.grid(row=1, column=1, sticky="w", padx=8, pady=(10,0))
        self.ext_combo.bind("<<ComboboxSelected>>", self.on_ext_change)

        ttk.Button(frm, text="Guardar como...", command=self.pick_save).grid(row=1, column=2, sticky="w", pady=(10,0))
        self.out_entry = ttk.Entry(frm, textvariable=self.output_path, width=44)
        self.out_entry.grid(row=1, column=3, columnspan=2, sticky="we", padx=8, pady=(10,0))

        ttk.Label(frm, text="Aspect Ratio:").grid(row=2, column=0, sticky="w", pady=(10,0))
        ratio_cb = ttk.Combobox(frm, textvariable=self.ratio, values=list(RATIO_OPTIONS.keys()), width=10, state="readonly")
        ratio_cb.grid(row=2, column=1, sticky="w", padx=8, pady=(10,0))
        ratio_cb.bind("<<ComboboxSelected>>", self.on_ratio_change)

        ttk.Label(frm, text="Resolução:").grid(row=2, column=2, sticky="w", pady=(10,0))
        self.res_cb = ttk.Combobox(frm, textvariable=self.res_text, width=16, state="normal")
        self.res_cb.grid(row=2, column=3, sticky="w", padx=8, pady=(10,0))

        ttk.Label(frm, text="Qualidade (vídeo):").grid(row=3, column=0, sticky="w", pady=(10,0))
        ttk.Combobox(frm, textvariable=self.quality, values=list(PRESET_OPTS.keys()), width=10, state="readonly").grid(row=3, column=1, sticky="w", padx=8, pady=(10,0))
        ttk.Checkbutton(frm, text="Permitir upscaling", variable=self.allow_up).grid(row=3, column=2, sticky="w", pady=(10,0))

        self.btn_convert = ttk.Button(frm, text="Converter", command=self.on_convert)
        self.btn_convert.grid(row=4, column=0, sticky="w", pady=(16,0))
        self.status = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.status).grid(row=4, column=1, columnspan=4, sticky="w", padx=8, pady=(16,0))

        # Barra de progresso + percentagem
        self.pbar = ttk.Progressbar(frm, orient="horizontal", mode="determinate", length=360, maximum=100)
        self.pbar.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8,0))
        self.pbar_lbl = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.pbar_lbl).grid(row=5, column=3, columnspan=2, sticky="w", padx=8)

        # ETA (por baixo da percentagem)
        self.eta_lbl = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.eta_lbl, foreground="#555").grid(row=6, column=0, columnspan=5, sticky="w", pady=(4,0))

        for c in range(5):
            frm.columnconfigure(c, weight=1 if c in (3,) else 0)

        self.allow_up.trace_add("write", lambda *args: self.refresh_presets())

    # atualiza percentagem e ETA
    def ui_progress(self, pct: int, eta_secs: Optional[float]):
        self.pbar["value"] = pct
        self.pbar_lbl.set(f"{pct}%")
        if eta_secs is None:
            self.eta_lbl.set("")
        else:
            self.eta_lbl.set(f"Tempo restante ~ {_fmt_eta(eta_secs)}")
        self.update_idletasks()

    def suggest_output_path(self, in_path: str, ext: str) -> str:
        base = os.path.splitext(os.path.basename(in_path))[0]
        folder = os.path.dirname(in_path)
        return os.path.join(folder, f"{base}_out.{ext}")

    def set_ext_combo_values_for_kind(self, kind: str):
        if kind == "image":
            vals = sorted(list(IMG_EXT))
        elif kind == "video":
            vals = sorted(list(VID_EXT))
        else:
            vals = list(ALL_EXT)
        self.ext_combo["values"] = vals

    def refresh_presets(self):
        if not (self.src_w and self.src_h):
            self.res_cb["values"] = []
            return
        vals = make_res_list_for_source(self.src_w, self.src_h, self.ratio.get(), self.allow_up.get())
        self.res_cb["values"] = vals
        if vals and self.res_text.get() not in vals:
            self.res_text.set(vals[0])

    def pick_file(self):
        path = filedialog.askopenfilename(
            title="Escolher ficheiro",
            filetypes=[("Imagens/Vídeos", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.gif *.mp4 *.webm *.avi *.mov *.mkv"),
                       ("Todos", "*.*")]
        )
        if not path:
            return
        self.input_path.set(path)
        kind = detect_kind(path)
        try:
            if kind=="image":
                self.src_w, self.src_h = img_dims(path)
            elif kind=="video":
                self.src_w, self.src_h = vid_dims(path)
            else:
                raise ValueError("Tipo não suportado")

            self.src_info.set(f"{os.path.basename(path)} — {kind} {self.src_w}x{self.src_h}")
            self.set_ext_combo_values_for_kind(kind)

            cur_ext = os.path.splitext(path)[1].lower().lstrip(".")
            if kind=="video":
                new_ext = "mp4"
            else:
                new_ext = "jpg" if cur_ext!="jpg" else "png"
            self.ext_target.set(new_ext)

            out_now = self.output_path.get().strip()
            if out_now:
                folder = os.path.dirname(out_now)
                base = os.path.splitext(os.path.basename(out_now))[0]
                self.output_path.set(os.path.join(folder, f"{base}.{new_ext}"))
            else:
                self.output_path.set(self.suggest_output_path(path, new_ext))

            self.refresh_presets()
            self.res_text.set(f"{self.src_w}x{self.src_h}")  # resolução nativa
        except Exception as e:
            self.src_w = self.src_h = None
            self.src_info.set("Erro ao ler dimensões")
            messagebox.showerror("Erro", str(e))

    def pick_save(self):
        ext = self.ext_target.get().lower().strip()
        if not ext:
            messagebox.showerror("Erro", "Escolhe o formato de saída.")
            return
        out = filedialog.asksaveasfilename(
            title="Guardar como",
            defaultextension=f".{ext}",
            filetypes=[(f".{ext}", f"*.{ext}"), ("Todos", "*.*")]
        )
        if out:
            self.output_path.set(out)

    def on_ratio_change(self, event=None):
        self.refresh_presets()

    def on_ext_change(self, event=None):
        ext = self.ext_target.get().strip().lower()
        out = self.output_path.get().strip()
        if out:
            folder = os.path.dirname(out)
            base = os.path.splitext(os.path.basename(out))[0]
            self.output_path.set(os.path.join(folder, f"{base}.{ext}"))

    def on_convert(self):
        check_binaries_or_die()

        inp = self.input_path.get().strip()
        out = self.output_path.get().strip()
        ext = self.ext_target.get().strip().lower()
        if not inp or not os.path.isfile(inp):
            messagebox.showerror("Erro", "Escolhe um ficheiro válido.")
            return
        if not out:
            messagebox.showerror("Erro", "Define o ficheiro de saída.")
            return
        if not ext:
            messagebox.showerror("Erro", "Escolhe o formato de saída.")
            return
        if os.path.abspath(inp) == os.path.abspath(out):
            messagebox.showerror("Erro", "O ficheiro de saída não pode ser o mesmo que o de entrada.")
            return

        dims = parse_res(self.res_text.get().strip()) if self.res_text.get().strip() else None
        if not dims:
            messagebox.showerror("Erro", "Resolução inválida. Usa WxH, ex.: 1920x1080.")
            return

        tgt_W, tgt_H = dims
        ratio = self.ratio.get()
        quality = self.quality.get()
        allow_up = self.allow_up.get()

        base_out, cur_ext = os.path.splitext(out)
        if not cur_ext or cur_ext.lower().lstrip(".") != ext:
            out = f"{base_out}.{ext}"
            self.output_path.set(out)

        kind = detect_kind(inp)
        if kind not in {"image","video"}:
            messagebox.showerror("Erro", "Tipo de ficheiro não suportado.")
            return
        if kind == "video" and ext in IMG_EXT:
            messagebox.showerror("Erro", "Converter vídeo para imagem não é suportado aqui.")
            return
        if kind == "image" and ext in VID_EXT:
            messagebox.showerror("Erro", "Converter imagem para vídeo não é suportado aqui.")
            return

        self.btn_convert.config(state="disabled")
        self.status.set("A converter...")
        self.eta_lbl.set("")  # limpa ETA

        def _task():
            try:
                if kind=="image":
                    self.pbar.config(mode="indeterminate")
                    self.pbar.start(10)
                    convert_image(inp, out, ext, tgt_W, tgt_H, ratio, allow_up)
                else:
                    self.pbar.config(mode="determinate")
                    self.ui_progress(0, None)
                    convert_video(
                        inp, out, ext, tgt_W, tgt_H, ratio, quality, allow_up,
                        on_progress=lambda p, eta: self.ui_progress(p, eta)
                    )
                self.status.set(f"OK: {out}")
                messagebox.showinfo("Concluído", f"Conversão concluída:\n{out}")
            except Exception as e:
                self.status.set("Falhou")
                messagebox.showerror("Erro", str(e))
            finally:
                try: self.pbar.stop()
                except Exception: pass
                self.pbar["value"] = 0
                self.pbar_lbl.set("")
                self.eta_lbl.set("")
                self.pbar.config(mode="determinate")
                self.btn_convert.config(state="normal")

        threading.Thread(target=_task, daemon=True).start()

# ---------- arrancar ----------
if __name__ == "__main__":
    app = App()
    app.mainloop()


# Executar o programa:
# source .venv/bin/activate
# python converter.py
