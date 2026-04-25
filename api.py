import os
import json
import tempfile
import yt_dlp
import gspread
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from faster_whisper import WhisperModel
from google.oauth2.service_account import Credentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Permitir que el HTML de cualquier sitio (GitHub Pages) hable con tu API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse('static/index.html')

# Modelo para recibir el link correctamente desde Flowise
class LinkInput(BaseModel):
    url: str

# --- CARGA DEL MODELO ---
MODEL_SIZE = "base"
model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")

# --- CONFIGURACIÓN DE GOOGLE SHEETS ---
SPREADSHEET_ID = "1Y2Y8rMZuPKy_NYW21POYL5-WSqGmWyLy5TnbWQM0VdQ"

def obtener_cliente_gspread():
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    google_creds_env = os.getenv("GOOGLE_CREDS")
    
    try:
        if google_creds_env:
            creds_info = json.loads(google_creds_env)
            creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
            return gspread.authorize(creds)
        else:
            return None
    except Exception as e:
        print(f"❌ Error Google: {e}")
        return None

def verificar_link_duplicado(link):
    try:
        gc = obtener_cliente_gspread()
        if not gc: return False
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.get_worksheet(0)
        links_guardados = worksheet.col_values(4) 
        return link in links_guardados
    except Exception as e:
        return False

def limpiar_texto(texto):
    return texto.replace("\n", " ").strip()

def descargar_audio(url, output_dir):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{output_dir}/%(id)s.%(ext)s',
        'quiet': True,
        'noplaylist': True,
        # Si tienes el archivo cookies.txt en la raíz, descomenta la siguiente línea:
        # 'cookiefile': 'cookies.txt', 
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

def transcribir_audio(ruta_audio):
    segments, _ = model.transcribe(ruta_audio, language="es")
    return " ".join([segment.text for segment in segments]).strip()

@app.post("/procesar-link")
async def procesar_link(input_data: LinkInput):
    link = input_data.url
    
    if verificar_link_duplicado(link):
        return {"resultado": "Este link ya fue procesado."}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            ruta_audio = descargar_audio(link, tmpdir)
            texto = transcribir_audio(ruta_audio)
            return {"resultado": texto}
        except Exception as e:
            return {"resultado": f"Error al procesar: {str(e)}"}

@app.post("/procesar-video")
async def procesar_video(file: UploadFile = File(...)):
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            file_path = os.path.join(tmpdir, file.filename)
            with open(file_path, "wb") as f:
                f.write(await file.read())
            texto = transcribir_audio(file_path)
            return {"resultado": texto}
        except Exception as e:
            return {"resultado": f"Error: {str(e)}"}