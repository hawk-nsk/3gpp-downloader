"""Specification number/version mapping and URL construction."""

import re
from dataclasses import dataclass, field
from urllib.parse import quote

from .config import ETSI_BASE, SERIES_MAP, THREEGPP_BASE


@dataclass
class SpecRef:
    """A 3GPP specification reference (number + version)."""

    number: str          # e.g. "29.274"
    version: str         # e.g. "15.3.0"
    series_dir: str = ""  # e.g. "29_series"
    title: str = ""

    def __post_init__(self) -> None:
        self.number = self.number.strip()
        self.version = self.version.strip()
        series_num = self.number.split(".")[0]
        self.series_dir = SERIES_MAP.get(series_num, f"{series_num}_series")
        if not self.title:
            self.title = f"TS {self.number}"

    @property
    def file_stem(self) -> str:
        """e.g. '29274' from '29.274'."""
        return self.number.replace(".", "")

    @property
    def major(self) -> int:
        return int(self.version.split(".")[0])

    @property
    def release_letter(self) -> str:
        """Archive release letter for 3GPP filenames.

        major 10->'a', 11->'b', ..., 15->'f', 16->'g', 17->'h', 18->'i', 19->'j'.
        For major < 10 the archive uses a numeric suffix, not a letter.
        """
        major = self.major
        if major < 10:
            return ""
        return chr(ord("a") + major - 10)

    # ------------------------------------------------------------------
    # 3GPP.org (FTP archive) URL
    # ------------------------------------------------------------------

    @property
    def threagpp_dir_url(self) -> str:
        """Directory listing URL for the spec on 3gpp.org."""
        return f"{THREEGPP_BASE}/{self.series_dir}/{self.number}/"

    @property
    def threagpp_zip_url(self) -> str:
        """Direct ZIP URL on 3gpp.org (best-effort; may need fallback)."""
        major = self.major
        minor = int(self.version.split(".")[1])
        patch = int(self.version.split(".")[2])
        if major < 10:
            if minor < 10:
                # Pre-Rel-10, minor<10: numeric suffix like 800 (8.0.0), 910 (9.1.0)
                stem = f"{self.file_stem}-{major}{minor}{patch}"
            else:
                # Pre-Rel-10, minor>=10: letter minor like 9a0 (9.10.0), 8b0 (8.11.0)
                stem = f"{self.file_stem}-{major}{_minor_to_letter(minor)}{patch}"
        else:
            letter = self.release_letter
            # minor may need a letter if >= 10 (a=10, b=11, ...)
            if minor < 10:
                minor_str = str(minor)
            else:
                minor_str = _minor_to_letter(minor)
            stem = f"{self.file_stem}-{letter}{minor_str}{patch}"
        return f"{self.threagpp_dir_url}{stem}.zip"

    # ------------------------------------------------------------------
    # ETSI deliver URL (fallback)
    # ------------------------------------------------------------------

    @property
    def etsi_stem(self) -> str:
        """ETSI document stem, e.g. '129274' for TS 129 274.

        ETSI prefixes the series with '1': 3GPP series 29 -> ETSI 129,
        series 23 -> 123, series 36 -> 136, etc. The document number is
        the series prefix + spec number without the dot.
        """
        series_num = self.number.split(".")[0]  # e.g. "29"
        spec_num = self.number.split(".")[1]    # e.g. "274"
        return f"1{series_num}{spec_num}"

    @property
    def etsi_series(self) -> str:
        """ETSI deliver series range directory, e.g. '129200_129299'.

        ETSI groups deliverables by 100-number ranges derived from the
        spec number. For TS 129 274 the range is 129200-129299; for
        TS 123 401 it is 123400-123499.
        """
        series_num = self.number.split(".")[0]  # e.g. "29"
        spec_num = int(self.number.split(".")[1])  # e.g. 274
        base = int(f"1{series_num}000")
        low = base + (spec_num // 100) * 100
        high = low + 99
        return f"{low}_{high}"

    @property
    def etsi_dir_url(self) -> str:
        """ETSI deliver directory URL."""
        return f"{ETSI_BASE}/etsi_ts/{self.etsi_series}/{self.etsi_stem}/"

    def etsi_pdf_candidates(self) -> list[str]:
        """Possible ETSI PDF URLs (try in order).

        ETSI stores published versions as folders named '15.04.00_60'
        (two-digit components). The PDF is 'ts_129274v150400p.pdf'.
        We try several folder/name variants for robustness.
        """
        v = version_to_5digit(self.version)          # 150300
        vdots = self.version                        # 15.3.0
        vdots2 = _version_to_2digit(self.version)    # 15.03.00
        major_minor = ".".join(self.version.split(".")[:2])  # 15.3
        stem = f"ts_{self.etsi_stem}v{v}p"
        candidates = []
        for dirname in (
            f"{vdots2}_60",       # 15.03.00_60 (2-digit, ETSI native)
            f"{vdots}_60",        # 15.3.0_60
            f"{major_minor}.0_60",# 15.3.0_60
            f"{v}_60",            # 150300_60
            f"{vdots2}",          # 15.03.00
            f"{vdots}",
        ):
            candidates.append(
                f"{ETSI_BASE}/etsi_ts/{self.etsi_series}/{self.etsi_stem}/{dirname}/{stem}.pdf")
        candidates.append(f"{self.etsi_dir_url}{stem}.pdf")
        return candidates


def validate_version(version: str) -> bool:
    """Check that version looks like 'X.Y.Z'."""
    return bool(re.fullmatch(r"\d+\.\d+\.\d+", version.strip()))


def version_to_5digit(version: str) -> str:
    """Convert '15.3.0' to '150300' (major.minor.patch each 2 digits)."""
    parts = version.strip().split(".")
    while len(parts) < 3:
        parts.append("0")
    return f"{int(parts[0]):02d}{int(parts[1]):02d}{int(parts[2]):02d}"


def _version_to_2digit(version: str) -> str:
    """Convert '15.3.0' to '15.03.00' (two-digit components, ETSI style)."""
    parts = version.strip().split(".")
    while len(parts) < 3:
        parts.append("0")
    return f"{int(parts[0]):02d}.{int(parts[1]):02d}.{int(parts[2]):02d}"


def validate_number(number: str) -> bool:
    """Check that spec number looks like 'XX.YYY'."""
    return bool(re.fullmatch(r"\d{2,3}\.\d{2,4}", number.strip()))


def parse_versions_from_3gpp_listing(html: str) -> list[str]:
    """Parse version list from a 3gpp.org directory listing.

    The listing contains links like '29274-f30.zip'. We extract the
    version part 'f30' and convert to '15.3.0'.
    """
    versions = []
    # Pattern: 29274-f30.zip  or  29274-300.zip
    for m in re.finditer(r"({0}-([a-z0-9]+)\.zip)".format(re.escape("")), html):
        pass
    # Better: match any filename like 29274-XXXX.zip and extract suffix
    for m in re.finditer(r"([a-zA-Z0-9]+)-([a-z0-9]+)\.zip", html):
        stem, suffix = m.group(1), m.group(2)
        if not stem.startswith("29") and not stem[:2].isdigit():
            continue
        ver = _suffix_to_version(suffix)
        if ver and ver not in versions:
            versions.append(ver)
    return sorted(versions, key=_version_key)


def _suffix_to_version(suffix: str) -> str | None:
    """Convert 3GPP archive suffix to version string.

    Numeric (pre-Rel-10, minor<10):   '130' -> 1.3.0, '010' -> 0.1.0, '960' -> 9.6.0
    Mixed (pre-Rel-10, minor>=10):    '9a0' -> 9.10.0, '8b0' -> 8.11.0, '9e0' -> 9.14.0
    Letter (Rel-10+):                 'a10' -> 10.1.0, 'f30' -> 15.3.0, 'ga0' -> 16.10.0
    """
    if not suffix:
        return None
    try:
        if suffix[0].isdigit():
            # major is the leading digit(s); minor is next char (digit or letter)
            major = int(suffix[0])
            rest = suffix[1:]
            if not rest:
                return None
            minor_ch = rest[0]
            if minor_ch.isdigit():
                minor = int(minor_ch)
            else:
                minor = _letter_to_minor(minor_ch)
            if minor is None:
                return None
            patch = int(rest[1:]) if rest[1:] else 0
            return f"{major}.{minor}.{patch}"
        # Letter-based: first char is release letter (a=Rel-10 ... j=Rel-19)
        letter = suffix[0]
        major = _letter_to_major(letter)
        if major is None:
            return None
        rest = suffix[1:]
        # minor is one char (digit or letter), patch is remaining digits
        # e.g. 'f30' -> minor='3', patch='0'; 'ga0' -> minor='a'(=10), patch='0'
        if not rest:
            return None
        minor_ch = rest[0]
        if minor_ch.isdigit():
            minor = int(minor_ch)
        else:
            minor = _letter_to_minor(minor_ch)
        if minor is None:
            return None
        patch = int(rest[1:]) if rest[1:] else 0
        return f"{major}.{minor}.{patch}"
    except (ValueError, IndexError):
        return None


def _letter_to_minor(letter: str) -> int | None:
    """Map a minor-component letter to a number (a=10, b=11, ...)."""
    if not letter or not letter.isalpha():
        return None
    return 10 + (ord(letter) - ord("a"))


def _minor_to_letter(minor: int) -> str:
    """Map a minor number >= 10 to a letter (10->'a', 11->'b', ...)."""
    return chr(ord("a") + (minor - 10))


def _letter_to_major(letter: str) -> int | None:
    """Map archive release letter to major version.

    3GPP archive filenames use a single letter for the major release:
    a=Rel-10, b=Rel-11, c=Rel-12, d=Rel-13, e=Rel-14, f=Rel-15,
    g=Rel-16, h=Rel-17, i=Rel-18, j=Rel-19.
    (Releases before Rel-10 use a numeric suffix, e.g. '960' = 9.6.0.)
    """
    mapping = {"a": 10, "b": 11, "c": 12, "d": 13, "e": 14, "f": 15,
               "g": 16, "h": 17, "i": 18, "j": 19}
    return mapping.get(letter)


def _version_key(v: str) -> tuple[int, int, int]:
    parts = v.split(".")
    while len(parts) < 3:
        parts.append("0")
    return tuple(int(x) for x in parts[:3])  # type: ignore[return-value]
