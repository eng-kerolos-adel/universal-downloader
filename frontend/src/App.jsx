/* eslint-disable no-useless-escape */
/* eslint-disable no-unused-vars */
import { useState } from "react";
import { motion } from "framer-motion";

export default function App() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [formats, setFormats] = useState([]);
  const [title, setTitle] = useState("");
  const [thumbnail, setThumbnail] = useState("");
  const [progress, setProgress] = useState(0);

  const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

  const fetchFormats = async () => {
    if (!url) return;
    setLoading(true);
    setFormats([]);
    setTitle("");
    setThumbnail("");
    try {
      const res = await fetch(`${API}/formats?url=${encodeURIComponent(url)}`);
      if (!res.ok) throw new Error("Failed to fetch formats");
      const data = await res.json();
      setFormats(data.formats || []);
      setTitle(data.title || "");
      setThumbnail(data.thumbnail || "");
    } catch (err) {
      console.error(err);
      alert("Error fetching formats: " + err.message);
    }
    setLoading(false);
  };

  // helper: extract filename from Content-Disposition header
  function extractFilenameFromCD(header) {
    if (!header) return null;
    // try filename* first (RFC5987)
    let m = header.match(/filename\*\=UTF-8''([^;\n]+)/);
    if (m && m[1]) {
      try {
        return decodeURIComponent(m[1].replace(/\+/g, " "));
      } catch {
        return m[1];
      }
    }
    m = header.match(/filename="([^"]+)"/);
    if (m && m[1]) {
      try {
        return decodeURIComponent(m[1].replace(/\+/g, " "));
      } catch {
        return m[1];
      }
    }
    m = header.match(/filename=([^;\n]+)/);
    if (m && m[1]) {
      try {
        return decodeURIComponent(m[1].replace(/\+/g, " "));
      } catch {
        return m[1];
      }
    }
    return null;
  }

  const downloadFile = async (formatId) => {
    if (!url) return;
    setLoading(true);
    setProgress(0);

    const apiUrl = `${API}/download?url=${encodeURIComponent(
      url
    )}&format_id=${encodeURIComponent(formatId)}`;

    try {
      // Try to fetch and stream (best: progress + read headers)
      const res = await fetch(apiUrl, { method: "GET" });

      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || "Download failed");
      }

      // attempt to read Content-Disposition and Content-Length
      const cdHeader =
        res.headers.get("Content-Disposition") ||
        res.headers.get("content-disposition") ||
        "";
      const contentLength =
        res.headers.get("Content-Length") || res.headers.get("content-length");

      const filenameFromHeader = extractFilenameFromCD(cdHeader);

      // If filename available and we can stream: use reader to show progress
      if (filenameFromHeader && res.body && contentLength) {
        const total = parseInt(contentLength, 10);
        const reader = res.body.getReader();
        const chunks = [];
        let received = 0;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          chunks.push(value);
          received += value.length;
          setProgress(Math.round((received / total) * 100));
        }

        setProgress(100);

        const blob = new Blob(chunks, {
          type: res.headers.get("Content-Type") || "application/octet-stream",
        });
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = blobUrl;
        a.download = filenameFromHeader;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(blobUrl);
      } else {
        // fallback: if headers not exposed or content-length missing, open direct link so browser handles headers
        // this will trigger the browser native download and correctly use Content-Disposition
        const a = document.createElement("a");
        a.href = apiUrl;
        a.target = "_self";
        document.body.appendChild(a);
        a.click();
        a.remove();
      }
    } catch (err) {
      console.error(err);
      alert("Error downloading file: " + (err.message || err));
    } finally {
      setTimeout(() => setProgress(0), 600);
      setLoading(false);
    }
  };

  // helper to show size nicely
  function niceSize(bytes) {
    if (!bytes) return "Unknown";
    const mb = bytes / (1024 * 1024);
    if (mb < 1) return (bytes / 1024).toFixed(1) + " KB";
    return mb.toFixed(2) + " MB";
  }

  return (
    <div className="min-h-screen bg-linear-to-br from-slate-900 to-slate-800 flex items-center justify-center p-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-4xl bg-white/6 backdrop-blur-xl p-8 rounded-2xl shadow-2xl border border-white/6"
      >
        <h1 className="text-4xl font-bold text-white mb-6 text-center">
          Universal Media Downloader
        </h1>

        <div className="flex gap-3 mb-4">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Paste media URL here..."
            className="flex-1 px-4 py-3 rounded-xl bg-white/10 text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <button
            onClick={fetchFormats}
            className="px-6 py-3 rounded-xl bg-blue-500 hover:bg-blue-600 text-white font-semibold transition cursor-pointer"
          >
            Fetch
          </button>
        </div>

        {loading && progress > 0 && (
          <div className="mb-4">
            <div className="w-full bg-white/20 rounded-full h-3">
              <div
                className="h-3 rounded-full bg-green-400"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-white text-sm mt-2">Downloading: {progress}%</p>
          </div>
        )}

        {title && (
          <div className="mb-6 text-center">
            {thumbnail && (
              <img
                src={thumbnail}
                alt="thumb"
                className="w-56 mx-auto rounded-xl shadow-lg mb-4"
              />
            )}
            <h2 className="text-2xl text-white font-semibold font-rubik">
              {title}
            </h2>
          </div>
        )}

        {formats.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {formats.map((f) => (
              <motion.div
                key={f.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="p-4 bg-white/8 rounded-xl border border-white/8 text-white"
              >
                <div className="flex items-start gap-4">
                  <div className="flex-1">
                    <h3 className="font-bold">Format: {f.id}</h3>
                    <p className="text-sm">
                      Type: {f.ext} • Resolution: {f.resolution || "N/A"}
                    </p>
                    <p className="text-sm">Size: {niceSize(f.size)}</p>
                  </div>
                  <div className="w-28 text-right">
                    <button
                      onClick={() => downloadFile(f.id)}
                      className="px-3 py-2 bg-green-500 hover:bg-green-600 rounded-lg font-semibold cursor-pointer"
                    >
                      Download
                    </button>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </motion.div>
    </div>
  );
}
