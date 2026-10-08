"""Download logic for 3GPP specifications from 3gpp.org and etsi.org."""

import logging
import zipfile
from pathlib import Path
from typing import Callable, Optional

import requests

from .config import DEFAULT_DOWNLOAD_DIR, REQUEST_TIMEOUT, USER_AGENT
from .specs import SpecRef

log = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, str], None]


class DownloadResult:
    """Result of a download attempt."""

    def __init__(self, ok: bool, source: str, local_path: Optional[Path],
                 url: str, error: str = ""):
        self.ok = ok
        self.source = source
        self.local_path = local_path
        self.url = url
        self.error = error

    def __repr__(self) -> str:
        status = "OK" if self.ok else f"FAIL ({self.error})"
        return f"<DownloadResult {self.source} {status} {self.url}>"


class SpecDownloader:
    """Downloads 3GPP specs from 3gpp.org and etsi.org."""

    def __init__(self, download_dir: Optional[Path] = None,
                 session: Optional[requests.Session] = None):
        self.download_dir = Path(download_dir or DEFAULT_DOWNLOAD_DIR)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or self._make_session()

    @staticmethod
    def _make_session() -> requests.Session:
        s = requests.Session()
        s.headers["User-Agent"] = USER_AGENT
        return s

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def download(self, number: str, version: str,
                 prefer: str = "both",
                 extract: bool = True,
                 progress: Optional[ProgressCallback] = None,
                 overwrite: bool = False) -> DownloadResult:
        """Download a specification.

        Args:
            number: 3GPP spec number, e.g. "29.274"
            version: version, e.g. "15.3.0"
            prefer: "3gpp", "etsi" or "both" (try 3gpp first, fallback to etsi)
            extract: if True, extract .zip (3gpp.org archives)
            progress: optional callback(step_total, step_done, message)
            overwrite: re-download even if file exists
        """
        ref = SpecRef(number=number, version=version)

        if prefer in ("3gpp", "both"):
            log.info("Trying 3gpp.org for %s v%s", number, version)
            result = self._try_3gpp(ref, extract=extract, progress=progress,
                                    overwrite=overwrite)
            if result.ok:
                return result
            if prefer == "3gpp":
                return result
            log.info("3gpp.org failed (%s); trying etsi.org", result.error)

        if prefer in ("etsi", "both"):
            log.info("Trying etsi.org for %s v%s", number, version)
            result_etsi = self._try_etsi(ref, progress=progress, overwrite=overwrite)
            if result_etsi.ok:
                return result_etsi
            if prefer == "both" and not result.ok:
                # Both sources failed — merge the errors into a single message
                combined = _merge_errors(result, result_etsi)
                return DownloadResult(False, "both", None, result.url or result_etsi.url,
                                      combined)
            return result_etsi

        return DownloadResult(False, "none", None, "", "no source selected")

    def download_many(self, specs: list[tuple[str, str]],
                      prefer: str = "both",
                      extract: bool = True,
                      overwrite: bool = False,
                      progress: Optional[ProgressCallback] = None,
                      on_result=None) -> dict[str, DownloadResult]:
        """Download several specifications (optionally with per-item version).

        Args:
            specs: list of (number, version) tuples, e.g.
                   [("29.274", "15.3.0"), ("29.244", "16.4.0")]
            prefer: source preference passed to each download
            extract: extract .zip archives
            overwrite: re-download existing files
            progress: progress callback(total_steps, done_steps, message)
            on_result: optional callback(spec_key, DownloadResult) after each item

        Returns:
            dict { "number vversion" : DownloadResult }
        """
        results: dict[str, DownloadResult] = {}
        total = len(specs)
        for i, (number, version) in enumerate(specs, start=1):
            key = f"{number} v{version}"
            if progress:
                progress(total, i - 1, f"Downloading {key}")
            try:
                res = self.download(
                    number, version,
                    prefer=prefer,
                    extract=extract,
                    overwrite=overwrite,
                    progress=None,
                )
            except Exception as e:  # defensive: keep batch going
                log.warning("Unexpected error for %s: %s", key, e)
                res = DownloadResult(False, "unknown", None, "", str(e))
            results[key] = res
            if progress:
                progress(total, i, f"Done {key}")
            if on_result:
                on_result(key, res)
        return results

    def list_versions(self, number: str) -> list[str]:
        """Fetch available versions for a spec number from 3gpp.org."""
        ref = SpecRef(number=number, version="0.0.0")
        url = ref.threagpp_dir_url
        try:
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("Could not list versions for %s: %s", number, e)
            return []
        from .specs import parse_versions_from_3gpp_listing
        return parse_versions_from_3gpp_listing(resp.text)

    def list_etsi_versions(self, number: str) -> list[str]:
        """Fetch available (published) versions for a spec from etsi.org.

        ETSI only publishes "frozen"/published versions, so this list is
        usually a subset of the 3gpp.org archive versions.
        """
        ref = SpecRef(number=number, version="0.0.0")
        url = ref.etsi_dir_url
        try:
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("Could not list ETSI versions for %s: %s", number, e)
            return []
        import re
        versions = []
        # ETSI version folders look like '15.04.00_60'
        for m in re.finditer(r"(\d{2}\.\d{2}\.\d{2})_60", resp.text):
            v = m.group(1)
            parts = v.split(".")
            ver = f"{int(parts[0])}.{int(parts[1])}.{int(parts[2])}"
            if ver not in versions:
                versions.append(ver)
        from .specs import _version_key
        return sorted(versions, key=_version_key)

    # ------------------------------------------------------------------
    # 3gpp.org
    # ------------------------------------------------------------------

    def _try_3gpp(self, ref: SpecRef, extract: bool,
                  progress: Optional[ProgressCallback],
                  overwrite: bool) -> DownloadResult:
        url = ref.threagpp_zip_url
        local_zip = self.download_dir / f"{ref.file_stem}-{ref.version}.zip"
        if local_zip.exists() and not overwrite:
            log.info("Already downloaded: %s", local_zip)
            # If extraction was requested, ensure it happens even if the zip
            # was downloaded earlier (e.g. by a previous extract=False call).
            if extract:
                extracted = self._extract_zip(local_zip, ref)
                return DownloadResult(True, "3gpp", extracted, url)
            return DownloadResult(True, "3gpp", local_zip, url)

        try:
            resp = self.session.get(url, stream=True, timeout=REQUEST_TIMEOUT)
            # 3gpp.org returns 404 for truly missing files but 403 for some
            # missing/redirected paths; either way the direct URL did not work.
            if resp.status_code != 200:
                resp.close()
                return self._try_3gpp_via_listing(ref, extract, progress, overwrite,
                                                  direct_status=resp.status_code)
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            with open(local_zip, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(total, done, f"Downloading {local_zip.name}")
            log.info("Downloaded %s (%d bytes)", local_zip, done)
        except requests.RequestException as e:
            log.warning("3gpp.org download failed (%s); trying listing", e)
            return self._try_3gpp_via_listing(ref, extract, progress, overwrite,
                                              direct_status=-1)

        if not extract:
            return DownloadResult(True, "3gpp", local_zip, url)
        extracted = self._extract_zip(local_zip, ref)
        return DownloadResult(True, "3gpp", extracted, url)

    def _try_3gpp_via_listing(self, ref: SpecRef, extract: bool,
                              progress: Optional[ProgressCallback],
                              overwrite: bool,
                              direct_status: int = 404) -> DownloadResult:
        """If direct URL fails, list the dir and find matching file."""
        versions = self.list_versions(ref.number)
        if not versions:
            return DownloadResult(False, "3gpp", None, ref.threagpp_dir_url,
                                  "no versions found in listing")
        # Find the version matching the requested one
        from .specs import _version_key
        target = _version_key(ref.version)
        match = None
        for v in versions:
            if _version_key(v) == target:
                match = v
                break
        if not match:
            return DownloadResult(
                False, "3gpp", None, ref.threagpp_dir_url,
                f"version {ref.version} does not exist on 3gpp.org "
                f"(direct URL returned {direct_status}); "
                f"available versions: {_format_versions(versions)}")
        # Build filename from the actual listing entry
        # We re-derive by iterating listing links
        url, filename = self._find_listing_file(ref, target)
        if not url:
            return DownloadResult(False, "3gpp", None, ref.threagpp_dir_url,
                                  "could not locate file in listing")
        local_zip = self.download_dir / filename
        if local_zip.exists() and not overwrite:
            return DownloadResult(True, "3gpp", local_zip, url)
        try:
            resp = self.session.get(url, stream=True, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            with open(local_zip, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
                    if progress:
                        progress(0, 0, f"Downloading {filename}")
            log.info("Downloaded %s", local_zip)
        except requests.RequestException as e:
            return DownloadResult(False, "3gpp", None, url, str(e))
        if not extract:
            return DownloadResult(True, "3gpp", local_zip, url)
        extracted = self._extract_zip(local_zip, ref)
        return DownloadResult(True, "3gpp", extracted, url)

    def _find_listing_file(self, ref: SpecRef,
                           target: tuple) -> tuple[Optional[str], Optional[str]]:
        """Return (url, filename) for the exact version in the 3gpp listing."""
        try:
            resp = self.session.get(ref.threagpp_dir_url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException:
            return None, None
        import re
        from .specs import _suffix_to_version, _version_key
        for m in re.finditer(r'href="([^"]+\.zip)"', resp.text):
            fname = m.group(1).split("/")[-1]
            # fname like 29274-f30.zip
            mm = re.search(r"[a-zA-Z0-9]+-([a-z0-9]+)\.zip$", fname)
            if not mm:
                continue
            ver = _suffix_to_version(mm.group(1))
            if ver and _version_key(ver) == target:
                url = ref.threagpp_dir_url + fname
                return url, fname
        return None, None

    # ------------------------------------------------------------------
    # ETSI.org
    # ------------------------------------------------------------------

    def _try_etsi(self, ref: SpecRef, progress: Optional[ProgressCallback],
                  overwrite: bool) -> DownloadResult:
        from .specs import version_to_5digit
        candidates = ref.etsi_pdf_candidates()
        local_name = f"ts_{ref.etsi_stem}v{version_to_5digit(ref.version)}p.pdf"
        for url in candidates:
            local = self.download_dir / local_name
            if local.exists() and not overwrite:
                return DownloadResult(True, "etsi", local, url)
            try:
                resp = self.session.get(url, stream=True, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                ctype = resp.headers.get("Content-Type", "")
                if "html" in ctype.lower():
                    continue
                with open(local, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        f.write(chunk)
                        if progress:
                            progress(0, 0, f"Downloading {local.name}")
                log.info("Downloaded ETSI %s", local)
                return DownloadResult(True, "etsi", local, url)
            except requests.RequestException as e:
                log.warning("ETSI attempt failed %s: %s", url, e)
                continue
        # All candidates failed — check the directory listing for available versions
        versions = self.list_etsi_versions(ref.number)
        if not versions:
            return DownloadResult(False, "etsi", None,
                                  ref.etsi_dir_url,
                                  "not found on etsi.org (all candidates 404; "
                                  "no versions listed in ETSI catalogue)")
        from .specs import _version_key
        target = _version_key(ref.version)
        exists = any(_version_key(v) == target for v in versions)
        if not exists:
            return DownloadResult(
                False, "etsi", None, ref.etsi_dir_url,
                f"version {ref.version} does not exist on etsi.org (only published "
                f"versions are available); available: {_format_versions(versions)}")
        return DownloadResult(False, "etsi", None,
                              ref.etsi_dir_url,
                              f"not found on etsi.org (candidates 404, but version "
                              f"{ref.version} is listed — URL format may have changed)")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_zip(self, zip_path: Path, ref: SpecRef) -> Path:
        """Extract the first document from a 3GPP .zip archive."""
        out_dir = self.download_dir / f"{ref.file_stem}-{ref.version}"
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                # Prefer .doc / .pdf / .docx
                target = None
                for cand in names:
                    low = cand.lower()
                    if low.endswith((".pdf", ".doc", ".docx", ".zip")):
                        target = cand
                        break
                if not target and names:
                    target = names[0]
                if target:
                    target_path = out_dir / Path(target).name
                    with zf.open(target) as src, open(target_path, "wb") as dst:
                        dst.write(src.read())
                    log.info("Extracted %s -> %s", target, target_path)
                    return target_path
        except zipfile.BadZipFile as e:
            log.warning("Not a valid zip: %s (%s)", zip_path, e)
            return zip_path
        return zip_path


def _format_versions(versions: list[str], max_show: int = 12) -> str:
    """Compact representation of a version list for error messages."""
    if len(versions) <= max_show:
        return ", ".join(versions)
    head = ", ".join(versions[: max_show // 2])
    tail = ", ".join(versions[-(max_show // 2):])
    return f"{head}, ..., {tail}  (total {len(versions)})"


def _merge_errors(a: DownloadResult, b: DownloadResult) -> str:
    """Merge two failure messages into one readable summary."""
    msg = f"3gpp.org: {a.error}; etsi.org: {b.error}"
    return msg
