"""CLI interface for the 3GPP specification downloader."""

import argparse
import logging
import sys
from pathlib import Path

from core.config import COMMON_SPECS, DEFAULT_DOWNLOAD_DIR
from core.downloader import SpecDownloader
from core.specs import validate_number, validate_version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="3gpp-downloader",
        description="Download 3GPP specifications from 3gpp.org or etsi.org",
    )
    sub = parser.add_subparsers(dest="command")

    # download
    dl = sub.add_parser("download", help="Download a specification")
    dl.add_argument("spec", help="Specification number, e.g. 29.274")
    dl.add_argument("version", help="Version, e.g. 15.3.0")
    dl.add_argument("-s", "--source", choices=["3gpp", "etsi", "both"],
                    default="both", help="Source (default: both, 3gpp first)")
    dl.add_argument("-d", "--dir", type=Path, default=DEFAULT_DOWNLOAD_DIR,
                    help="Download directory")
    dl.add_argument("--no-extract", action="store_true",
                    help="Do not extract .zip (3gpp.org)")
    dl.add_argument("--overwrite", action="store_true",
                    help="Re-download even if file exists")

    # batch
    bt = sub.add_parser("batch", help="Download several specifications at once")
    bt.add_argument("specs", nargs="*",
                    help="Spec(s) as 'number:version', e.g. 29.274:15.3.0 29.244:16.4.0")
    bt.add_argument("-f", "--file", type=Path, default=None,
                    help="Optional file with one 'number:version' per line")
    bt.add_argument("-s", "--source", choices=["3gpp", "etsi", "both"],
                    default="both", help="Source (default: both, 3gpp first)")
    bt.add_argument("-d", "--dir", type=Path, default=DEFAULT_DOWNLOAD_DIR,
                    help="Download directory")
    bt.add_argument("--no-extract", action="store_true",
                    help="Do not extract .zip (3gpp.org)")
    bt.add_argument("--overwrite", action="store_true",
                    help="Re-download even if file exists")

    # list
    ls = sub.add_parser("list", help="List available versions for a spec")
    ls.add_argument("spec", help="Specification number, e.g. 29.274")
    ls.add_argument("-s", "--source", choices=["3gpp", "etsi", "both"],
                    default="3gpp", help="Source to query")

    # common
    com = sub.add_parser("common", help="List common specifications")
    com.add_argument("-s", "--source", choices=["3gpp", "etsi", "both"],
                     default="3gpp", help="Source (unused, for consistency)")

    # web
    web = sub.add_parser("web", help="Start web UI")
    web.add_argument("-p", "--port", type=int, default=8090,
                     help="Port (default 8090)")
    web.add_argument("-d", "--dir", type=Path, default=DEFAULT_DOWNLOAD_DIR,
                     help="Download directory")
    web.add_argument("--host", default="127.0.0.1", help="Bind host")

    return parser


def cmd_download(args) -> int:
    if not validate_number(args.spec):
        print(f"Invalid spec number: {args.spec} (expected e.g. 29.274)")
        return 2
    if not validate_version(args.version):
        print(f"Invalid version: {args.version} (expected e.g. 15.3.0)")
        return 2

    dl = SpecDownloader(download_dir=args.dir)

    def progress(total, done, msg):
        if total and done:
            pct = int(done * 100 / total)
            print(f"\r  {msg}: {pct}%", end="", flush=True)
        else:
            print(f"\r  {msg}...", end="", flush=True)

    print(f"Downloading {args.spec} v{args.version} (source: {args.source})")
    result = dl.download(
        args.spec, args.version,
        prefer=args.source,
        extract=not args.no_extract,
        progress=progress,
        overwrite=args.overwrite,
    )
    print()
    if result.ok:
        print(f"OK  [{result.source}] -> {result.local_path}")
        return 0
    print(f"FAILED [{result.source}]: {result.error}")
    return 1


def cmd_batch(args) -> int:
    """Download multiple specs. Accepts 'number:version' args and/or a file."""
    specs = []
    for s in args.specs:
        if ":" in s:
            specs.append(tuple(s.split(":", 1)))
        else:
            specs.append((s, ""))
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8-sig") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if ":" in line:
                        specs.append(tuple(line.split(":", 1)))
                    else:
                        specs.append((line, ""))
        except OSError as e:
            print(f"Cannot read file {args.file}: {e}")
            return 2

    # Validate and collect
    clean = []
    for num, ver in specs:
        if not validate_number(num):
            print(f"Invalid spec number: {num}")
            return 2
        if not ver:
            print(f"Missing version for {num} (use number:version)")
            return 2
        if not validate_version(ver):
            print(f"Invalid version for {num}: {ver} (expected e.g. 15.3.0)")
            return 2
        clean.append((num, ver))

    if not clean:
        print("No specifications to download.")
        return 2

    dl = SpecDownloader(download_dir=args.dir)
    print(f"Batch download of {len(clean)} spec(s) (source: {args.source})")

    def progress(total, done, msg):
        print(f"\r  [{done}/{total}] {msg}", end="", flush=True)

    results = dl.download_many(
        clean,
        prefer=args.source,
        extract=not args.no_extract,
        overwrite=args.overwrite,
        progress=progress,
    )
    print()
    ok = sum(1 for r in results.values() if r.ok)
    print(f"\nResult: {ok}/{len(results)} succeeded")
    for key, res in results.items():
        status = "OK  " if res.ok else "FAIL"
        detail = str(res.local_path) if res.ok else res.error
        print(f"  [{status}] {key} -> {detail}")
    return 0 if ok == len(results) else 1


def cmd_list(args) -> int:
    if not validate_number(args.spec):
        print(f"Invalid spec number: {args.spec}")
        return 2
    dl = SpecDownloader()
    versions = dl.list_versions(args.spec)
    if not versions:
        print(f"No versions found for {args.spec}")
        return 1
    print(f"Available versions for {args.spec}:")
    for v in versions:
        print(f"  {v}")
    return 0


def cmd_common(args) -> int:
    print("Common 3GPP specifications:")
    for num, title in sorted(COMMON_SPECS.items()):
        print(f"  {num:<8} {title}")
    return 0


def cmd_web(args) -> int:
    try:
        from webapp import app  # noqa: F401
    except ImportError as e:
        print(f"Cannot start web UI: {e}. Is Flask installed?")
        print("  pip install flask")
        return 2
    # Configure download dir for webapp
    import os
    os.environ["ATF_DOWNLOAD_DIR"] = str(args.dir)
    print(f"Starting web UI at http://{args.host}:{args.port}")
    print(f"Download dir: {args.dir}")
    app.run(host=args.host, port=args.port, debug=False)
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    handlers = {
        "download": cmd_download,
        "batch": cmd_batch,
        "list": cmd_list,
        "common": cmd_common,
        "web": cmd_web,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
