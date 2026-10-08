"""Configuration and constants for the 3GPP downloader."""

from pathlib import Path

# Default download directory
DEFAULT_DOWNLOAD_DIR = Path.home() / "3gpp_downloads"

# 3GPP FTP base URL
THREEGPP_BASE = "https://www.3gpp.org/ftp/Specs/archive"

# ETSI deliver base URL
ETSI_BASE = "https://www.etsi.org/deliver"

# Request timeout (seconds)
REQUEST_TIMEOUT = 60

# User-Agent to avoid bot-blocking
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

# Map: specification number prefix -> 3GPP series directory name
# e.g. "23.401" -> "23_series", "29.274" -> "29_series"
SERIES_MAP = {
    "21": "21_series",
    "22": "22_series",
    "23": "23_series",
    "24": "24_series",
    "25": "25_series",
    "26": "26_series",
    "27": "27_series",
    "28": "28_series",
    "29": "29_series",
    "30": "30_series",
    "31": "31_series",
    "32": "32_series",
    "33": "33_series",
    "34": "34_series",
    "35": "35_series",
    "36": "36_series",
    "37": "37_series",
    "38": "38_series",
    "39": "39_series",
}

# Release letter -> version prefix mapping for 3GPP filenames
# Release number to letter: Rel-4=a, Rel-5=b, ..., Rel-15=f, Rel-16=g, Rel-17=h, Rel-18=i, Rel-19=j
RELEASE_LETTERS = {
    4: "a",
    5: "b",
    6: "c",
    7: "d",
    8: "e",
    9: "f",
    10: "g",
    11: "h",
    12: "i",
    13: "j",
    14: "k",
    15: "f",
    16: "g",
    17: "h",
    18: "i",
    19: "j",
}

# Release number by major version
RELEASE_BY_MAJOR = {
    3: 4,   # 3GPP TS xxx 3.x.y -> Rel-99/4 (approx)
    4: 4,
    5: 5,
    6: 6,
    7: 7,
    8: 8,
    9: 9,
    10: 10,
    11: 11,
    12: 12,
    13: 13,
    14: 14,
    15: 15,
    16: 16,
    17: 17,
    18: 18,
    19: 19,
}

# Common useful specifications for quick reference
COMMON_SPECS = {
    "23.401": "General Packet Radio Service (GPRS) enhancements for E-UTRAN access",
    "23.501": "System architecture for the 5G System (5GS)",
    "23.502": "Procedures for the 5G System (5GS)",
    "24.301": "Non-Access-Stratum (NAS) protocol for EPS",
    "24.501": "Non-Access-Stratum (NAS) protocol for 5G System (5GS)",
    "29.274": "Tunnelling Protocol for Control plane (GTPv2-C)",
    "29.244": "Interface between the Control Plane and the User Plane nodes (PFCP)",
    "29.212": "Policy and Charging Control (PCC); Policy and Charging Enforcement Function",
    "29.214": "Policy and Charging Control over Rx reference point",
    "29.272": "Evolved Packet System; Mobility Management Entity (MME) and Serving GPRS Support Node (SGSN) related interfaces based on Diameter",
    "33.401": "Security architecture for EPS",
    "36.300": "E-UTRAN; Overall description; Stage 2",
    "38.300": "NR; Overall description; Stage 2",
    "38.401": "NG-RAN; Architecture description",
    "32.251": "Telecommunication management; Charging management; Packet Switched (PS) domain charging",
    "32.299": "Telecommunication management; Charging management; Diameter charging applications",
    "23.272": "Circuit Switched (CS) fallback in Evolved Packet System (EPS); Stage 2",
}
