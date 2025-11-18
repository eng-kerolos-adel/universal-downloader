# backend/main.py
import os
import re
import shutil
import tempfile
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import yt_dlp

app = FastAPI(title="Universal Downloader API")

# Important: expose Content-Disposition and Content-Length so frontend can read them via fetch()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Type", "Content-Length"],
)


def sanitize_filename(name: str) -> str:
    """Remove characters not allowed in filenames on most platforms."""
    return re.sub(r'[\\/*?:"<>|]', "", name)


@app.get("/formats")
def get_formats(url: str = Query(...)):
    """
    Return title, thumbnail, and a filtered set of formats (mp4, mp3, webp)
    Each format includes id, ext, resolution, size (bytes)
    """
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)

        thumbnail = info.get("thumbnail")
        allowed_exts = {"mp4", "mp3", "webp"}
        formats = []

        for f in info.get("formats", []):
            ext = (f.get("ext") or "").lower()
            if ext not in allowed_exts:
                continue
            size = f.get("filesize") or f.get("filesize_approx") or 0
            formats.append({
                "id": f.get("format_id"),
                "ext": ext,
                "resolution": f.get("resolution") or f.get("height") or "N/A",
                "size": size
            })

        return {
            "title": info.get("title"),
            "thumbnail": thumbnail,
            "formats": formats
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/download")
def download(
    url: str = Query(...),
    format_id: str = Query(...),
    background_tasks: BackgroundTasks = None
):
    """
    Download the requested format to a temporary directory, then return a FileResponse.
    Important: we set Content-Disposition header with filename* (RFC5987) and we DO NOT pass `filename=` param
    to FileResponse (some frameworks may override). FileResponse will still set content-length.
    """
    tmp_dir = tempfile.mkdtemp(prefix="udl_")
    outtmpl = os.path.join(tmp_dir, "%(title)s.%(ext)s")

    try:
        ydl_opts = {
            "quiet": True,
            "format": format_id,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "outtmpl": outtmpl,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        req = info.get("requested_downloads")
        if not req or not req[0].get("filepath"):
            raise Exception("Could not find downloaded file!")

        file_path = req[0]["filepath"]

        original_name = sanitize_filename(os.path.basename(file_path))
        encoded_name = quote(original_name)

        ext = os.path.splitext(original_name)[1].lower()
        mime = {
            ".mp4": "video/mp4",
            ".webm": "video/webm",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".wav": "audio/wav",
            ".webp": "image/webp",
        }.get(ext, "application/octet-stream")

        # schedule cleanup after response
        if background_tasks:
            background_tasks.add_task(shutil.rmtree, tmp_dir, True)

        headers = {
            # RFC 5987 format:
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"
        }

        # Return FileResponse without passing filename= param (we rely on our custom header)
        return FileResponse(path=file_path, media_type=mime, headers=headers)

    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))

# @app.get("/download")
# def download(
#     url: str = Query(...),
#     background_tasks: BackgroundTasks = None
# ):
#     tmp_dir = tempfile.mkdtemp(prefix="udl_")
#     outtmpl = os.path.join(tmp_dir, "%(title)s.%(ext)s")

#     try:
#         ydl_opts = {
#             "quiet": True,
#             "format": "bestvideo+bestaudio/best",  # <<<<< أهم سطر
#             "merge_output_format": "mp4",          # <<<<< دمج تلقائي + خروج mp4
#             "outtmpl": outtmpl,
#             "no_warnings": True,
#         }

#         with yt_dlp.YoutubeDL(ydl_opts) as ydl:
#             info = ydl.extract_info(url, download=True)

#         filepath = ydl.prepare_filename(info)
#         if not os.path.exists(filepath):
#             raise Exception("Merged file not found!")

#         filename = sanitize_filename(os.path.basename(filepath))
#         encoded = quote(filename)

#         if background_tasks:
#             background_tasks.add_task(shutil.rmtree, tmp_dir, True)

#         headers = {
#             "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"
#         }

#         return FileResponse(filepath, media_type="video/mp4", headers=headers)

#     except Exception as e:
#         shutil.rmtree(tmp_dir, ignore_errors=True)
#         raise HTTPException(status_code=500, detail=str(e))
