# Conversor -- Image e Video Converter

Aplicação Tkinter em Python para converter imagens e vídeos. Usa FFmpeg
para vídeo e Pillow para imagens. Suporta mudança de formato,
redimensionamento, preservação de proporções, qualidade, barra de
progresso e ETA.

## Funcionalidades

-   Suporta imagens: png, jpg, jpeg, webp, bmp, tif, tiff, gif
-   Suporta vídeos: mp4, webm, avi, mov, mkv
-   Sugestão automática de resoluções compatíveis
-   Aspect ratio: Original, 16:9, 4:3, 1:1, 9:16, 3:2, 4:5
-   Presets de qualidade para vídeo: Alta, Normal, Rápido
-   Upscaling opcional
-   Barra de progresso + percentagem + tempo restante
-   Evita sobrescrever o ficheiro original
-   Usa hardware encoding quando disponível (NVENC, AMF, QSV,
    VideoToolbox)

## Dependências

Python 3.11+ Pillow imageio-ffmpeg FFmpeg (inclui ffprobe)

## Instalação (macOS)

python3 -m venv .venv source .venv/bin/activate pip install --upgrade
pip pip install pillow imageio-ffmpeg brew install ffmpeg

Executar: python converson.py

## Instalação (Windows)

py -3.12 -m venv .venv ..venv`\Scripts`{=tex}`\Activate`{=tex}.ps1 pip
install --upgrade pip pip install pillow imageio-ffmpeg

Instalar FFmpeg estático para Windows (x64). Garantir que ffmpeg.exe e
ffprobe.exe estão no PATH ou na pasta do projeto.

Executar: py converson.py

## Uso

1.  Abrir a aplicação
2.  Carregar um ficheiro (imagem ou vídeo)
3.  Escolher formato, resolução, qualidade e ratio
4.  Definir destino do output
5.  Carregar "Converter"
6.  Para vídeos: acompanhar percentagem e ETA

## Comportamento interno

-   Imagens redimensionadas com LANCZOS
-   JPEG converte RGBA/Palette para RGB automaticamente
-   Vídeos MP4/MOV/MKV/AVI mantêm stream copy se a resolução + ratio
    forem iguais
-   Caso contrário usa H.264 (hardware encoder se existir; fallback
    libx264)
-   WebM usa VP9 + Opus
-   Dimensões de vídeo são forçadas a valores pares
-   ffprobe é usado para ler duração e dimensões

## Criar executável para Windows (.exe)

Não é possível compilar um .exe no macOS com PyInstaller. A build tem de
ser feita num Windows.

1.  Criar requirements.txt\
    pillow\
    imageio-ffmpeg\
    pyinstaller

2.  Colocar ffmpeg.exe e ffprobe.exe em ffmpeg-bin 

3.  No Windows:

py -3.12 -m venv .venv\
..venv`\Scripts`{=tex}`\pip `{=tex}install --upgrade pip\
..venv`\Scripts`{=tex}`\pip `{=tex}install -r requirements.txt

..venv`\Scripts`{=tex}`\pyinstaller `{=tex}--windowed --onefile --name
Conversor \^ --add-binary "ffmpeg-bin`\ffmpeg`{=tex}.exe;." \^
--add-binary "ffmpeg-bin`\ffprobe`{=tex}.exe;." \^ converson.py

O executável final aparece em dist`\Conversor`{=tex}.exe

## Problemas comuns

FFmpeg não encontrado: falta ffmpeg.exe ou ffprobe.exe\
Erro 0xc000007b: mistura 32/64 bits\
WebM lento: VP9 é pesado\
NVENC/QSV/AMF não aparecem: build de FFmpeg sem hardware encoders

## Estrutura recomendada

converson.py\
requirements.txt\
ffmpeg-bin/ffmpeg.exe\
ffmpeg-bin/ffprobe.exe

## Licença

MIT (ou outra à tua escolha)
