# # backend/main.py
# import os
# import re
# import shutil
# import tempfile
# from urllib.parse import quote

# from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import FileResponse
# import yt_dlp

# app = FastAPI(title="Universal Downloader API")

# # Important: expose Content-Disposition and Content-Length so frontend can read them via fetch()
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # tighten in production
#     allow_methods=["*"],
#     allow_headers=["*"],
#     expose_headers=["Content-Disposition", "Content-Type", "Content-Length"],
# )


# def sanitize_filename(name: str) -> str:
#     """Remove characters not allowed in filenames on most platforms."""
#     return re.sub(r'[\\/*?:"<>|]', "", name)


# @app.get("/formats")
# def get_formats(url: str = Query(...)):
#     """
#     Return title, thumbnail, and a filtered set of formats (mp4, mp3, webp)
#     Each format includes id, ext, resolution, size (bytes)
#     """
#     try:
#         with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
#             info = ydl.extract_info(url, download=False)

#         thumbnail = info.get("thumbnail")
#         allowed_exts = {"mp4", "mp3", "webp"}
#         formats = []

#         for f in info.get("formats", []):
#             ext = (f.get("ext") or "").lower()
#             if ext not in allowed_exts:
#                 continue
#             size = f.get("filesize") or f.get("filesize_approx") or 0
#             formats.append({
#                 "id": f.get("format_id"),
#                 "ext": ext,
#                 "resolution": f.get("resolution") or f.get("height") or "N/A",
#                 "size": size
#             })

#         return {
#             "title": info.get("title"),
#             "thumbnail": thumbnail,
#             "formats": formats
#         }

#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))


# @app.get("/download")
# def download(
#     url: str = Query(...),
#     format_id: str = Query(...),
#     background_tasks: BackgroundTasks = None
# ):
#     """
#     Download the requested format to a temporary directory, then return a FileResponse.
#     Important: we set Content-Disposition header with filename* (RFC5987) and we DO NOT pass `filename=` param
#     to FileResponse (some frameworks may override). FileResponse will still set content-length.
#     """
#     tmp_dir = tempfile.mkdtemp(prefix="udl_")
#     outtmpl = os.path.join(tmp_dir, "%(title)s.%(ext)s")

#     try:
#         ydl_opts = {
#             "quiet": True,
#             "format": format_id,
#             "outtmpl": outtmpl,
#             "no_warnings": True,
#         }

#         with yt_dlp.YoutubeDL(ydl_opts) as ydl:
#             info = ydl.extract_info(url, download=True)

#         req = info.get("requested_downloads")
#         if not req or not req[0].get("filepath"):
#             raise Exception("Could not find downloaded file!")

#         file_path = req[0]["filepath"]

#         original_name = sanitize_filename(os.path.basename(file_path))
#         encoded_name = quote(original_name)

#         ext = os.path.splitext(original_name)[1].lower()
#         mime = {
#             ".mp4": "video/mp4",
#             ".webm": "video/webm",
#             ".mp3": "audio/mpeg",
#             ".m4a": "audio/mp4",
#             ".wav": "audio/wav",
#             ".webp": "image/webp",
#         }.get(ext, "application/octet-stream")

#         # schedule cleanup after response
#         if background_tasks:
#             background_tasks.add_task(shutil.rmtree, tmp_dir, True)

#         headers = {
#             # RFC 5987 format:
#             "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"
#         }

#         # Return FileResponse without passing filename= param (we rely on our custom header)
#         return FileResponse(path=file_path, media_type=mime, headers=headers)

#     except Exception as e:
#         shutil.rmtree(tmp_dir, ignore_errors=True)
#         raise HTTPException(status_code=500, detail=str(e))



import os
import re
import shutil
import tempfile
from urllib.parse import quote
import requests

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

app = FastAPI(title="Universal Downloader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Type", "Content-Length"],
)

# Piped instance (fast + stable)
PIPED_API = "https://pipedapi.kavin.rocks"


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name)


@app.get("/formats")
def get_formats(url: str = Query(...)):
    """Return title, thumbnail, and available formats using Piped API."""
    try:
        video_id = url.split("v=")[-1].split("&")[0]

        api_url = f"{PIPED_API}/streams/{video_id}"
        data = requests.get(api_url).json()

        if "title" not in data:
            raise Exception("Could not fetch video data")

        title = data["title"]
        thumbnail = data.get("thumbnailUrl")

        formats = []

        # Add video formats
        for f in data.get("videoStreams", []):
            formats.append({
                "id": f["itag"],
                "ext": "mp4" if "video" in f["mimeType"] else "webm",
                "resolution": f"{f['quality']} ({f['fps']}fps)",
                "size": f.get("contentLength", 0)
            })

        # Add audio formats
        for f in data.get("audioStreams", []):
            formats.append({
                "id": f["itag"],
                "ext": "mp3" if "audio/mp3" in f["mimeType"] else "m4a",
                "resolution": "Audio",
                "size": f.get("contentLength", 0)
            })

        return {
            "title": title,
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
    """Download selected stream using Piped links."""
    tmp_dir = tempfile.mkdtemp(prefix="udl_")

    try:
        video_id = url.split("v=")[-1].split("&")[0]
        api_url = f"{PIPED_API}/streams/{video_id}"
        data = requests.get(api_url).json()

        # find the stream with same itag
        stream = None
        for f in data.get("videoStreams", []) + data.get("audioStreams", []):
            if str(f["itag"]) == str(format_id):
                stream = f
                break

        if not stream:
            raise Exception("Format not found")

        file_url = stream["url"]
        file_ext = "mp4" if "video" in stream["mimeType"] else "mp3"
        file_name = sanitize_filename(f"{data['title']}.{file_ext}")
        file_path = os.path.join(tmp_dir, file_name)

        # Download the file
        with requests.get(file_url, stream=True) as r:
            with open(file_path, "wb") as f:
                shutil.copyfileobj(r.raw, f)

        encoded_name = quote(file_name)

        mime = "video/mp4" if file_ext == "mp4" else "audio/mpeg"

        if background_tasks:
            background_tasks.add_task(shutil.rmtree, tmp_dir, True)

        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"
        }

        return FileResponse(file_path, media_type=mime, headers=headers)

    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))
