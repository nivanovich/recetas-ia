import os
import re
import json
import tempfile
import yt_dlp
import gspread
from fastapi import FastAPI, UploadFile, File, HTTPException
from faster_whisper import WhisperModel
from google.oauth2.service_account import Credentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse('static/index.html')
# --- CARGA DEL MODELO ---
MODEL_SIZE = "base"
model = WhisperModel(MODEL_SIZE)

# --- CONFIGURACIÓN DE GOOGLE SHEETS ---
SPREADSHEET_ID = "1Y2Y8rMZuPKy_NYW21POYL5-WSqGmWyLy5TnbWQM0VdQ"
GOOGLE_JSON_PATH = "flowise-494122-7af1b6e0d893.json" # Solo para uso local

def obtener_cliente_gspread():
    """Autoriza gspread usando variables de entorno o archivo local."""
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    # Intentar obtener credenciales de la variable de entorno (Railway)
    google_creds_env = os.getenv("GOOGLE_CREDS")
    
    try:
        if google_creds_env:
            # Caso: Producción en Railway
            creds_info = json.loads(google_creds_env)
            creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
            return gspread.authorize(creds)
        else:
            # Caso: Desarrollo local
            return gspread.service_account(filename=GOOGLE_JSON_PATH)
    except Exception as e:
        print(f"❌ Error crítico en la conexión con Google: {e}")
        return None

def verificar_link_duplicado(link):
    """Retorna True si el link ya existe en la Columna D de la hoja."""
    try:
        gc = obtener_cliente_gspread()
        if not gc:
            return False # Si no hay conexión, procesamos por precaución
            
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.get_worksheet(0)
        
        # Obtenemos todos los valores de la columna D (índice 4)
        links_guardados = worksheet.col_values(4) 
        
        return link in links_guardados
    except Exception as e:
        print(f"⚠️ Error al verificar Google Sheets: {e}")
        return False

def limpiar_texto(texto):
    return texto.replace("\n", " ").strip()

def descargar_audio(url, output_dir):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{output_dir}/%(id)s.%(ext)s',
        'quiet': True,
        'noplaylist': True,
        'restrictfilenames': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        archivo = ydl.prepare_filename(info)
    return archivo

def transcribir_audio(ruta_audio):
    segments, _ = model.transcribe(ruta_audio, language="es")
    texto = ""
    for segment in segments:
        texto += segment.text + " "
    return limpiar_texto(texto)

# =========================
# ENDPOINT 1: por link
# =========================
@app.post("/procesar-link")
def procesar_link(link: str):
    # --- VALIDACIÓN DE DUPLICADOS ---
    if verificar_link_duplicado(link):
        return {
            "status": "duplicado",
            "mensaje": "Este link ya fue procesado anteriormente.",
            "link": link
        }
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            ruta_audio = descargar_audio(link, tmpdir)
            texto = transcribir_audio(ruta_audio)

            return {
                "link": link,
                "descripcion": texto
            }

        except Exception as e:
            return {"error": str(e)}

# =========================
# ENDPOINT 2: subir video
# =========================
@app.post("/procesar-video")
async def procesar_video(file: UploadFile = File(...)):
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            file_path = os.path.join(tmpdir, file.filename)
            with open(file_path, "wb") as f:
                f.write(await file.read())
            texto = transcribir_audio(file_path)
            return {
                "link": "archivo_local",
                "descripcion": texto
            }
        except Exception as e:
            return {"error": str(e)}