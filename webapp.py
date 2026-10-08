"""Web UI for the 3GPP specification downloader (Flask)."""

import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, url_for

from core.config import COMMON_SPECS, DEFAULT_DOWNLOAD_DIR
from core.downloader import SpecDownloader
from core.specs import validate_number, validate_version

app = Flask(__name__)

# Download directory (override via env var for CLI 'web' command)
DOWNLOAD_DIR = Path(os.environ.get("ATF_DOWNLOAD_DIR", str(DEFAULT_DOWNLOAD_DIR)))

# Cache of available versions per spec (in-memory, refreshed on demand)
_versions_cache: dict[str, list[str]] = {}


def _downloader() -> SpecDownloader:
    return SpecDownloader(download_dir=DOWNLOAD_DIR)


@app.route("/")
def index():
    return render_template(
        "index.html",
        common_specs=COMMON_SPECS,
        download_dir=str(DOWNLOAD_DIR),
    )


@app.route("/api/versions")
def api_versions():
    """Return available versions for a spec number."""
    number = request.args.get("spec", "").strip()
    source = request.args.get("source", "3gpp").strip()
    if not validate_number(number):
        return jsonify({"error": "invalid spec number", "versions": []})
    if source not in ("3gpp", "etsi"):
        source = "3gpp"
    cache_key = f"{source}:{number}"
    versions = _versions_cache.get(cache_key)
    if versions is None:
        if source == "etsi":
            versions = _downloader().list_etsi_versions(number)
        else:
            versions = _downloader().list_versions(number)
        _versions_cache[cache_key] = versions
    return jsonify({"spec": number, "source": source, "versions": versions})


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json(silent=True) or {}
    number = str(data.get("spec", "")).strip()
    version = str(data.get("version", "")).strip()
    source = str(data.get("source", "both")).strip()
    extract = bool(data.get("extract", True))

    if not validate_number(number):
        return jsonify({"ok": False, "error": f"Invalid spec number: {number}"})
    if not validate_version(version):
        return jsonify({"ok": False, "error": f"Invalid version: {version}"})
    if source not in ("3gpp", "etsi", "both"):
        source = "both"

    dl = _downloader()
    result = dl.download(
        number, version,
        prefer=source,
        extract=extract,
        progress=None,
        overwrite=False,
    )
    if result.ok:
        # Relative path from the download dir (may include a subfolder
        # for extracted 3GPP zip contents). Normalize to forward slashes.
        try:
            rel = str(result.local_path.resolve().relative_to(DOWNLOAD_DIR.resolve()))
        except ValueError:
            rel = result.local_path.name
        rel = rel.replace("\\", "/")
        return jsonify({
            "ok": True,
            "source": result.source,
            "file": result.local_path.name,
            "path": str(result.local_path),
            "url": result.url,
            "download_url": url_for("api_get_file", filename=rel),
        })
    return jsonify({"ok": False, "error": result.error, "url": result.url})


@app.route("/api/download-many", methods=["POST"])
def api_download_many():
    """Download several specifications at once.

    Body JSON: {"specs": [{"spec": "29.274", "version": "15.3.0"}, ...],
                "source": "both", "extract": true}
    """
    data = request.get_json(silent=True) or {}
    specs = data.get("specs", [])
    source = str(data.get("source", "both")).strip()
    extract = bool(data.get("extract", True))

    if source not in ("3gpp", "etsi", "both"):
        source = "both"

    clean = []
    for item in specs:
        if isinstance(item, dict):
            number = str(item.get("spec", "")).strip()
            version = str(item.get("version", "")).strip()
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            number = str(item[0]).strip()
            version = str(item[1]).strip()
        else:
            continue
        if not validate_number(number) or not validate_version(version):
            return jsonify({"ok": False,
                            "error": f"Invalid spec/version: {number} / {version}"})
        clean.append((number, version))

    if not clean:
        return jsonify({"ok": False, "error": "No valid specifications provided"})

    dl = _downloader()
    results = dl.download_many(
        clean,
        prefer=source,
        extract=extract,
        overwrite=False,
    )

    items = []
    for key, res in results.items():
        entry = {
            "key": key,
            "ok": res.ok,
            "source": res.source,
            "error": res.error if not res.ok else "",
        }
        if res.ok:
            try:
                rel = str(res.local_path.resolve()
                          .relative_to(DOWNLOAD_DIR.resolve()))
            except ValueError:
                rel = res.local_path.name
            rel = rel.replace("\\", "/")
            entry["file"] = res.local_path.name
            entry["path"] = str(res.local_path)
            entry["download_url"] = url_for("api_get_file", filename=rel)
        items.append(entry)

    ok_count = sum(1 for r in results.values() if r.ok)
    return jsonify({"ok": True, "total": len(results),
                    "succeeded": ok_count, "items": items})


@app.route("/api/refresh/<spec>")
def api_refresh(spec: str):
    """Force refresh the versions cache for a spec."""
    source = request.args.get("source", "3gpp").strip()
    if source not in ("3gpp", "etsi"):
        source = "3gpp"
    if not validate_number(spec):
        return jsonify({"error": "invalid spec", "versions": []})
    if source == "etsi":
        versions = _downloader().list_etsi_versions(spec)
    else:
        versions = _downloader().list_versions(spec)
    _versions_cache[f"{source}:{spec}"] = versions
    return jsonify({"spec": spec, "source": source, "versions": versions})


@app.route("/files/<path:filename>")
def api_get_file(filename: str):
    """Serve a downloaded file from the download directory.

    `filename` may be a path relative to the download dir (e.g.
    '29274-16.4.0/29274-g40.docx'). If not found directly, fall back to
    searching the whole download dir by the file name (handles files that
    live in a version subfolder).
    """
    base = DOWNLOAD_DIR.resolve()
    safe = (base / filename).resolve()
    if str(safe).startswith(str(base)) and safe.exists() and safe.is_file():
        return send_file(safe, as_attachment=True)

    # Fallback: search by the base file name anywhere under the download dir
    name = Path(filename).name
    hits = [p for p in base.rglob(name) if p.is_file()]
    if hits:
        return send_file(hits[0], as_attachment=True)
    return "Not found", 404


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8090, debug=False)
