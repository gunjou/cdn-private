from fastapi import FastAPI, File, UploadFile, HTTPException, Header
from fastapi.staticfiles import StaticFiles
import os
import uuid
from datetime import datetime
from PIL import Image
import io
from dotenv import load_dotenv

# --------------------------
# LOAD ENV
# --------------------------
load_dotenv()

app = FastAPI()

# --------------------------
# CONFIG
# --------------------------

BASE_DIR = os.getenv("CDN_BASE_DIR")
MAX_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 500)) * 1024  # KB → bytes

# LOCAL ONLY: Allow GET /images/*
app.mount("/images", StaticFiles(directory=BASE_DIR), name="images")

# CDN URL per service
CDN_URL_MAP = {
    "ukaisyndrome": os.getenv("CDN_URL_UKAISYNDROME"),
    "absensi-berkah": os.getenv("CDN_URL_ABSENSIBERKAH"),
}

# Allowed API Keys per service
ALLOWED_KEYS = {
    "ukaisyndrome": os.getenv("API_KEY_UKAISYNDROME"),
    "absensi-berkah": os.getenv("API_KEY_ABSENSIBERKAH"),
}

# Allowed categories per service
ALLOWED_CATEGORIES = {
    "ukaisyndrome": ["tryout", "materi"],
    "absensi-berkah": ["wajah", "sakit", "izin", "lembur"],
}

# --------------------------
# HELPERS
# --------------------------

def sanitize_segment(value: str):
    if not value.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid folder name")
    return value


def compress_image(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    quality = 85
    while quality > 40:
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", optimize=True, quality=quality)

        if buffer.tell() <= MAX_SIZE:
            return buffer.getvalue()

        quality -= 5

    return buffer.getvalue()


# --------------------------
# UPLOAD API
# --------------------------

@app.post("/api/upload/{service_name}/{category}")
async def upload_image(
    service_name: str,
    category: str,
    file: UploadFile = File(...),
    api_key: str = Header(None, alias="X-API-KEY")
):

    # 1. API KEY WAJIB DIISI
    if not api_key:
        raise HTTPException(status_code=403, detail="API key required")

    # 2. SERVICE HARUS VALID
    if service_name not in ALLOWED_KEYS:
        raise HTTPException(status_code=403, detail="Invalid service")

    # 3. API KEY HARUS SAMA
    if api_key != ALLOWED_KEYS[service_name]:
        raise HTTPException(status_code=403, detail="Unauthorized API key")

    # 4. CATEGORY HARUS VALID
    if category not in ALLOWED_CATEGORIES.get(service_name, []):
        raise HTTPException(status_code=400, detail="Invalid category")

    # 5. SANITIZE INPUT
    service_name = sanitize_segment(service_name)
    category = sanitize_segment(category)

    # 6. FOLDER STRUCTURE
    year = datetime.now().year
    folder = f"{BASE_DIR}/{service_name}/{year}/{category}/"
    os.makedirs(folder, exist_ok=True)

    # 7. READ FILE
    original_bytes = await file.read()
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "jpg"

    # 8. PROCESS IMAGE
    if ext in ["jpg", "jpeg", "png"]:
        processed = compress_image(original_bytes)
        final_ext = "jpg"
    else:
        processed = original_bytes
        final_ext = ext

    # 9. FINAL FILENAME
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    unique = f"{timestamp}_{uuid.uuid4()}.{final_ext}"

    filepath = os.path.join(folder, unique)

    # 10. SAVE FILE
    with open(filepath, "wb") as f:
        f.write(processed)

    # 11. FINAL URL
    cdn_base_url = CDN_URL_MAP.get(service_name)
    if not cdn_base_url:
        raise HTTPException(status_code=500, detail="CDN URL not configured")

    url = f"{cdn_base_url}/{service_name}/{year}/{category}/{unique}"

    return {
        "status": True,
        "url": url,
        "size": len(processed),
        "file": unique
    }
    