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
IMAGE_DIR = os.getenv("CDN_IMAGE_DIR")
DOCUMENT_DIR = os.getenv("CDN_DOCUMENT_DIR")

MAX_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 500)) * 1024

# Static Files
app.mount(
    "/images",
    StaticFiles(directory=IMAGE_DIR),
    name="images"
)

app.mount(
    "/documents",
    StaticFiles(directory=DOCUMENT_DIR),
    name="documents"
)

# CDN URL per service image
CDN_URL_MAP = {
    "ukaisyndrome": os.getenv("CDN_URL_UKAISYNDROME"),
    "absensi-berkah": os.getenv("CDN_URL_ABSENSIBERKAH"),
}

# API KEY image service
ALLOWED_KEYS = {
    "ukaisyndrome": os.getenv("API_KEY_UKAISYNDROME"),
    "absensi-berkah": os.getenv("API_KEY_ABSENSIBERKAH"),
}

# Category image
ALLOWED_CATEGORIES = {
    "ukaisyndrome": [
        "tryout",
        "materi",
        "assets"
    ],
    "absensi-berkah": [
        "wajah",
        "sakit",
        "izin",
        "lembur"
    ],
}

# --------------------------
# DOCUMENT CONFIG
# --------------------------

DOCUMENT_API_KEY = os.getenv(
    "API_KEY_WEBBERKAH_DOCUMENT"
)

DOCUMENT_BASE_URL = os.getenv(
    "CDN_URL_WEBBERKAH_DOCUMENT"
)

DOCUMENT_CATEGORIES = [
    "invoice",
    "kontrak",
    "penawaran"
]

DOCUMENT_EXTENSIONS = [
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx"
]

MAX_DOCUMENT_SIZE = 10 * 1024 * 1024

# --------------------------
# HELPERS
# --------------------------

def sanitize_segment(value: str):
    if not value.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid folder name")
    return value


def compress_image(image_bytes: bytes, ext: str) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    
    save_format = "PNG" if ext == "png" else "JPEG"
    if save_format == "JPEG" and img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    quality = 85
    while quality > 40:
        buffer = io.BytesIO()
        
        if save_format == "PNG":
            img.save(buffer, format=save_format, optimize=True)
            return buffer.getvalue()
        else:
            img.save(buffer, format=save_format, optimize=True, quality=quality)

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

    if not api_key:
        raise HTTPException(status_code=403, detail="API key required")

    if service_name not in ALLOWED_KEYS:
        raise HTTPException(status_code=403, detail="Invalid service")

    if api_key != ALLOWED_KEYS[service_name]:
        raise HTTPException(status_code=403, detail="Unauthorized API key")

    if category not in ALLOWED_CATEGORIES.get(service_name, []):
        raise HTTPException(status_code=400, detail="Invalid category")

    service_name = sanitize_segment(service_name)
    category = sanitize_segment(category)

    year = datetime.now().year

    folder = f"{IMAGE_DIR}/{service_name}/{year}/{category}/"
    os.makedirs(folder, exist_ok=True)

    original_bytes = await file.read()

    original_ext = (
        file.filename.split(".")[-1].lower()
        if "." in file.filename
        else "jpg"
    )

    if original_ext in ["jpg", "jpeg", "png"]:
        final_ext = "png" if original_ext == "png" else "jpg"
        processed = compress_image(
            original_bytes,
            final_ext
        )
    else:
        processed = original_bytes
        final_ext = original_ext

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    unique = (
        f"{timestamp}_{uuid.uuid4()}.{final_ext}"
    )

    filepath = os.path.join(
        folder,
        unique
    )

    with open(filepath, "wb") as f:
        f.write(processed)

    cdn_base_url = CDN_URL_MAP.get(
        service_name
    )

    url = (
        f"{cdn_base_url}/"
        f"{service_name}/"
        f"{year}/"
        f"{category}/"
        f"{unique}"
    )

    return {
        "status": True,
        "url": url,
        "size": len(processed),
        "file": unique
    }



@app.post("/api/upload-document/{category}")
async def upload_document(
    category: str,
    file: UploadFile = File(...),
    api_key: str = Header(
        None,
        alias="X-API-KEY"
    )
):

    # API KEY
    if not api_key:
        raise HTTPException(
            status_code=403,
            detail="API key required"
        )

    if api_key != DOCUMENT_API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized API key"
        )

    # CATEGORY
    category = sanitize_segment(category)

    if category not in DOCUMENT_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail="Invalid category"
        )

    # EXTENSION
    ext = (
        file.filename.split(".")[-1].lower()
        if "." in file.filename
        else ""
    )

    if ext not in DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Invalid document type"
        )

    # READ FILE
    contents = await file.read()

    # SIZE LIMIT
    if len(contents) > MAX_DOCUMENT_SIZE:
        raise HTTPException(
            status_code=400,
            detail="Document exceeds maximum size"
        )

    # FOLDER
    year = datetime.now().year

    folder = os.path.join(
        DOCUMENT_DIR,
        "webberkah",
        category,
        str(year)
    )

    os.makedirs(
        folder,
        exist_ok=True
    )

    # FILE NAME
    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    unique = (
        f"{timestamp}_{uuid.uuid4()}.{ext}"
    )

    filepath = os.path.join(
        folder,
        unique
    )

    # SAVE
    with open(filepath, "wb") as f:
        f.write(contents)

    # URL
    url = (
        f"{DOCUMENT_BASE_URL}/"
        f"webberkah/"
        f"{category}/"
        f"{year}/"
        f"{unique}"
    )

    return {
        "status": True,
        "url": url,
        "size": len(contents),
        "file": unique
    }