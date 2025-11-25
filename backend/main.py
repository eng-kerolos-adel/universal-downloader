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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Type", "Content-Length"],
)


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name)


@app.get("/formats")
def get_formats(url: str = Query(...)):
    """
    Return ONE merged video+audio format per resolution.
    """
    try:
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android"],   # مهم جداً
                }
            },
            "http_headers": {
                "User-Agent": "com.google.android.youtube/18.41.35 (Linux; U; Android 13)"
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        thumbnail = info.get("thumbnail")
        formats_map = {}

        for f in info.get("formats", []):
            if not f.get("height"):
                continue

            height = f.get("height")
            ext = f.get("ext")

            if ext != "mp4":
                continue

            size = f.get("filesize") or f.get("filesize_approx") or 0

            if height not in formats_map or size > formats_map[height]["size"]:
                formats_map[height] = {
                    "id": f["format_id"],
                    "ext": ext,
                    "resolution": f"{f.get('width')}x{height}",
                    "size": size,
                }

        merged_formats_list = list(formats_map.values())
        merged_formats_list.sort(key=lambda x: int(x["resolution"].split("x")[1]))

        return {
            "title": info.get("title"),
            "thumbnail": thumbnail,
            "formats": merged_formats_list
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
    Download selected format_id as: bestvideo[format_id]+bestaudio merged into mp4
    """
    tmp_dir = tempfile.mkdtemp(prefix="udl_")
    outtmpl = os.path.join(tmp_dir, "%(title)s.%(ext)s")

    try:
        ydl_opts = {
            "quiet": True,
            "format": f"{format_id}+bestaudio/best",   # ← هنا السحر الحقيقي
            "merge_output_format": "mp4",
            "outtmpl": outtmpl,
            "no_warnings": True,
						"http_headers": {
        "User-Agent": "com.google.android.youtube/18.41.35 (Linux; U; Android 13)"
    },
    "extractor_args": {
        "youtube": {
            "player_client": ["android"],    # أهم جزء!
        }
    }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        req = info.get("requested_downloads")
        if not req or not req[0].get("filepath"):
            raise Exception("File not found after download.")

        file_path = req[0]["filepath"]
        original_name = sanitize_filename(os.path.basename(file_path))
        encoded_name = quote(original_name)

        ext = os.path.splitext(original_name)[1].lower()
        mime = "video/mp4"

        if background_tasks:
            background_tasks.add_task(shutil.rmtree, tmp_dir, True)

        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"
        }

        return FileResponse(
            path=file_path,
            media_type=mime,
            headers=headers
        )

    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))
