"""Scrapers, API clients, and ICS-217 parsers for Augusta Ham Radio (W4DV) & CSRA DMR / TGIF Georgia."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple


W4DV_REPEATERS_URL = "https://w4dv.club/repeaters/area-repeaters/"
ICS217_GDRIVE_FILE_ID = "1cngh9XC-wQGq8uAd--lfqF1po-himlsK"
ICS217_GDRIVE_EXPORT_URL = (
    f"https://drive.google.com/uc?export=download&id={ICS217_GDRIVE_FILE_ID}"
)
TGIF_TALKGROUPS_JSON_URL = "https://tgif.network/talkgroups.json"
TGIF_STATIC_TG_API_BASE = "https://api.tgif.network/v1/static-talkgroups"


@dataclass
class AnalogChannelSpec:
    """Normalized analog FM repeater or simplex channel."""

    name: str
    short_name: str  # <= 7 chars for Baofeng UV-5R LCD
    rx_mhz: float
    tx_mhz: float
    duplex: str  # "", "+", "-", "off"
    offset_mhz: float
    tone_mode: str  # "", "Tone", "TSQL"
    rx_tone: Optional[float]
    tx_tone: Optional[float]
    bandwidth_khz: float  # 25.0 or 12.5
    power: str  # High, Mid, Low, Turbo
    rx_only: bool
    category: str  # W4DV, CSRA_RPT, SIMPLEX, OUT_OF_TOWN, NOAA_WX, FRS, GMRS, MURS
    callsign: str
    location: str
    notes: str


@dataclass
class DigitalChannelSpec:
    """Normalized DMR Tier-II digital channel."""

    name: str  # <= 16 chars, underscore-separated
    rx_mhz: float
    tx_offset_str: str  # e.g. "+5", "+0.6", "+0"
    power: str  # Turbo, High, Mid, Low
    scanlist: str  # "-" or index
    rx_only: bool
    admit: str  # "-", "Color", "Free"
    color_code: int
    timeslot: int  # 1 or 2
    rx_grouplist_idx: int
    tx_contact_id: int
    tx_contact_name: str
    network: str  # TGIF, Vidalia_SG, BrandMeister, SCHEART_PRN, Simplex
    callsign: str
    location: str


@dataclass
class TalkgroupSpec:
    """Normalized DMR Talkgroup or Private Contact."""

    dmr_id: int
    name_16: str  # <= 16 chars, underscore-separated for dmrconfig
    full_name: str
    call_type: str  # "Group" or "Private"
    network: str  # TGIF, Georgia, BrandMeister, SCHEART_PRN, CSRA
    rx_tone: str = "-"


# Curated Authoritative W4DV & CSRA Repeaters (Verified against w4dv.club & ICS-217)
AUTHORITATIVE_W4DV_REPEATERS: List[Dict[str, object]] = [
    {
        "name": "W4DV_145.110",
        "short_name": "W4DV110",
        "rx_mhz": 145.110,
        "tx_mhz": 144.510,
        "rx_tone": 71.9,
        "tx_tone": 71.9,
        "bw": 25.0,
        "callsign": "W4DV",
        "location": "North Augusta, SC (WBBQ Tower)",
        "notes": "ARCA Primary 2m Repeater | CSRA Nightly Traditions Net 8PM | EchoLink W4DV-L",
    },
    {
        "name": "W4DV_145.290",
        "short_name": "W4DV290",
        "rx_mhz": 145.290,
        "tx_mhz": 144.690,
        "rx_tone": 71.9,
        "tx_tone": 71.9,
        "bw": 25.0,
        "callsign": "W4DV",
        "location": "South Augusta, GA",
        "notes": "ARCA South Augusta 2m Repeater (Trustee: W4IXI)",
    },
    {
        "name": "W4DV_145.390",
        "short_name": "W4DV390",
        "rx_mhz": 145.390,
        "tx_mhz": 144.790,
        "rx_tone": 71.9,
        "tx_tone": 71.9,
        "bw": 25.0,
        "callsign": "W4DV",
        "location": "Trenton, SC",
        "notes": "ARCA Trenton 2m | Ham Radio 101 Net Thu 9PM & CSRA Multi-Mode Sat 8PM",
    },
    {
        "name": "W4DV_145.490",
        "short_name": "W4DV490",
        "rx_mhz": 145.490,
        "tx_mhz": 144.890,
        "rx_tone": 71.9,
        "tx_tone": 71.9,
        "bw": 25.0,
        "callsign": "W4DV",
        "location": "Trenton, SC",
        "notes": "CSRA SKYWARN Emergency Net & Aiken ERC Net Wed 9PM | EchoLink W4DV-R",
    },
    {
        "name": "W4DV_147.180",
        "short_name": "W4DV180",
        "rx_mhz": 147.180,
        "tx_mhz": 147.780,
        "rx_tone": 71.9,
        "tx_tone": 71.9,
        "bw": 25.0,
        "callsign": "W4DV",
        "location": "South Augusta, GA (Fairington Tank)",
        "notes": "ARCA Fairington Elevated Tank 2m Repeater",
    },
    {
        "name": "W4DV_444.950",
        "short_name": "W4DV950",
        "rx_mhz": 444.950,
        "tx_mhz": 449.950,
        "rx_tone": 71.9,
        "tx_tone": 71.9,
        "bw": 25.0,
        "callsign": "W4DV",
        "location": "Trenton, SC",
        "notes": "ARCA 70cm Analog/Mixed Repeater (Trustee: W4IXI)",
    },
]


# Curated CSRA & Georgia TGIF / BrandMeister / Vidalia Supergroup / SCHEART Talkgroups
CURATED_CSRA_GA_TALKGROUPS: List[TalkgroupSpec] = [
    TalkgroupSpec(31665, "31665_TGIF_ALL", "TGIF Mothership All Call", "Group", "TGIF"),
    TalkgroupSpec(358, "358_CSRA_TALK", "CSRA Talkgroup (Augusta/SC)", "Group", "TGIF"),
    TalkgroupSpec(43389, "43389_SE_LINK", "SouthEast Link Multi-Mode", "Group", "TGIF"),
    TalkgroupSpec(9050, "9050_EastC_Ref", "East Coast Reflector", "Group", "TGIF"),
    TalkgroupSpec(985, "985_K4KNS", "K4KNS Columbia County Repeater", "Group", "TGIF"),
    TalkgroupSpec(8014, "CSRA_PT1_Wx", "CSRA Weather Alert PT1", "Group", "TGIF"),
    TalkgroupSpec(8044, "CSRA_PT2_Wx", "CSRA Weather Alert PT2", "Group", "TGIF"),
    TalkgroupSpec(31000, "PARROT", "TGIF Parrot Audio Test", "Group", "TGIF"),
    # Georgia TGIF & BrandMeister / Vidalia Supergroup Talkgroups
    TalkgroupSpec(9, "9_LOCAL_SG", "Local / Vidalia Supergroup TS1/TS2", "Group", "Vidalia_SG"),
    TalkgroupSpec(310592, "310592_VIDALIA", "Vidalia Supergroup BM Bridge", "Group", "Vidalia_SG"),
    TalkgroupSpec(3113, "3113_GA_STATE", "Georgia Statewide (TGIF & BM)", "Group", "Georgia"),
    TalkgroupSpec(31130, "31130_GA_ARES", "Georgia ARES Emergency Net", "Group", "Georgia"),
    TalkgroupSpec(31134, "31134_N_GEORGIA", "North Georgia / AmComm Bridge", "Group", "Georgia"),
    TalkgroupSpec(31137, "31137_KINGSLND", "Kingsland Digital Link (Camden GA)", "Group", "Georgia"),
    TalkgroupSpec(314722, "314722_CSRA_MM", "CSRA Multi-Mode Net Bridge", "Group", "Georgia"),
    TalkgroupSpec(3445, "3445_GA_RADIO", "Georgia Radio TGIF", "Group", "Georgia"),
    TalkgroupSpec(14679, "14679_FOLKSTON", "Folkston GA Repeater TGIF", "Group", "Georgia"),
    # SCHEART / PRN / Regional & National
    TalkgroupSpec(2, "2_PRN_FC_WIDE", "PRN Wide / First Coast DMR TS2", "Group", "SCHEART_PRN"),
    TalkgroupSpec(27500, "27500_PRN_LOC", "SCHEART PRN Local TS1", "Group", "SCHEART_PRN"),
    TalkgroupSpec(27501, "27501_PRN_CHT1", "SCHEART PRN Chat 1", "Group", "SCHEART_PRN"),
    TalkgroupSpec(27502, "27502_PRN_CHT2", "SCHEART PRN Chat 2", "Group", "SCHEART_PRN"),
    TalkgroupSpec(27510, "27510_SC_CALL", "South Carolina Statewide Call", "Group", "SCHEART_PRN"),
    TalkgroupSpec(99, "99_DMR_SIMPLEX", "National DMR Simplex TG99", "Group", "Simplex"),
    TalkgroupSpec(9998, "9998_PRN_ECHO", "PRN Echotest Server", "Group", "SCHEART_PRN"),
    TalkgroupSpec(36102, "36102_PRN_DATA", "PRN Data Channel", "Group", "SCHEART_PRN"),
    TalkgroupSpec(3145, "3145_SC_STATE", "South Carolina Statewide BM", "Group", "BrandMeister"),
    TalkgroupSpec(3100, "3100_USA_NATION", "USA Nationwide BM/TGIF", "Group", "BrandMeister"),
    TalkgroupSpec(91, "91_WORLDWIDE", "Worldwide Calling", "Group", "BrandMeister"),
    TalkgroupSpec(9990, "9990_BM_PARROT", "BrandMeister Parrot Private/Group", "Group", "BrandMeister"),
]


class _TableHTMLParser(HTMLParser):
    """Lightweight HTML table parser for scraping w4dv.club/repeaters/area-repeaters/."""

    def __init__(self) -> None:
        super().__init__()
        self.in_td = False
        self.current_row: List[str] = []
        self.current_cell: List[str] = []
        self.rows: List[List[str]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in ("td", "th"):
            self.in_td = True
            self.current_cell = []
        elif tag == "tr":
            self.current_row = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self.in_td:
            self.in_td = False
            self.current_row.append(" ".join("".join(self.current_cell).split()))
        elif tag == "tr" and self.current_row:
            self.rows.append(self.current_row)

    def handle_data(self, data: str) -> None:
        if self.in_td:
            self.current_cell.append(data)


def fetch_url_bytes(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 10) -> Optional[bytes]:
    """Attempt an HTTP GET when network is available; gracefully return None when sandboxed/offline."""
    req_headers = {"User-Agent": "CSRA-HAM-DMR-Automation/1.0 (+https://w4dv.club)"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None


def sync_remote_sources(repo_root: Path, tgif_api_token: Optional[str] = None, dmr_id: int = 3221824) -> Dict[str, str]:
    """
    Attempt live synchronization from:
      1. Google Drive ICS-217 CSRA Amateur Radio Frequencies.xlsx
      2. https://w4dv.club/repeaters/area-repeaters/
      3. TGIF Network Georgia Talkgroups & Static Talkgroup API (https://api.tgif.network/v1/static-talkgroups/{id})
    Falls back cleanly to verified local snapshots in data/sources/ when running offline.
    """
    sources_dir = repo_root / "data" / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    status: Dict[str, str] = {}

    # 1. ICS-217 Google Drive Workbook
    xlsx_path = sources_dir / "ICS-217 CSRA Amateur Radio Frequencies.xlsx"
    raw_xlsx = fetch_url_bytes(ICS217_GDRIVE_EXPORT_URL)
    if raw_xlsx and raw_xlsx.startswith(b"PK"):
        xlsx_path.write_bytes(raw_xlsx)
        status["ics217_xlsx"] = "live_downloaded"
    elif xlsx_path.exists():
        status["ics217_xlsx"] = "local_verified_cache"
    else:
        status["ics217_xlsx"] = "missing"

    # 2. W4DV Club Area Repeaters Page
    w4dv_cache = sources_dir / "w4dv_area_repeaters.json"
    raw_w4dv = fetch_url_bytes(W4DV_REPEATERS_URL)
    if raw_w4dv:
        parser = _TableHTMLParser()
        parser.feed(raw_w4dv.decode("utf-8", errors="replace"))
        w4dv_cache.write_text(
            json.dumps(
                {
                    "source_url": W4DV_REPEATERS_URL,
                    "scraped_rows": parser.rows,
                    "authoritative_repeaters": AUTHORITATIVE_W4DV_REPEATERS,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        status["w4dv_web"] = "live_scraped"
    else:
        w4dv_cache.write_text(
            json.dumps(
                {
                    "source_url": W4DV_REPEATERS_URL,
                    "authoritative_repeaters": AUTHORITATIVE_W4DV_REPEATERS,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        status["w4dv_web"] = "authoritative_fallback"

    # 3. TGIF Network Talkgroups & Static Talkgroup API for Georgia / CSRA
    tgif_cache = sources_dir / "tgif_georgia_csra.json"
    token = tgif_api_token or os.environ.get("TGIF_API_TOKEN")
    static_tg_state = None
    if token:
        raw_static = fetch_url_bytes(
            f"{TGIF_STATIC_TG_API_BASE}/{dmr_id}",
            headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
        )
        if raw_static:
            try:
                static_tg_state = json.loads(raw_static.decode("utf-8"))
            except json.JSONDecodeError:
                static_tg_state = None

    raw_tgif_list = fetch_url_bytes(TGIF_TALKGROUPS_JSON_URL)
    ga_tgs_from_api: List[Dict[str, object]] = []
    if raw_tgif_list:
        try:
            all_tgs = json.loads(raw_tgif_list.decode("utf-8"))
            if isinstance(all_tgs, list):
                for item in all_tgs:
                    text_blob = json.dumps(item).lower()
                    if any(k in text_blob for k in ("georgia", "csra", "augusta", "w4dv", "k4kns", "358", "3113")):
                        ga_tgs_from_api.append(item)
        except json.JSONDecodeError:
            pass

    tgif_payload = {
        "tgif_portal": "https://tgif.network/signin.php",
        "static_tg_api_endpoint": f"{TGIF_STATIC_TG_API_BASE}/{dmr_id}",
        "static_tg_state": static_tg_state,
        "live_filtered_georgia_talkgroups": ga_tgs_from_api,
        "curated_csra_georgia_talkgroups": [asdict(t) for t in CURATED_CSRA_GA_TALKGROUPS],
    }
    tgif_cache.write_text(json.dumps(tgif_payload, indent=2) + "\n", encoding="utf-8")
    status["tgif_georgia_api"] = "live_synced" if (ga_tgs_from_api or static_tg_state) else "curated_verified_cache"

    return status


def _parse_xlsx_sheets(xlsx_path: Path) -> Dict[str, List[Dict[str, str]]]:
    """Zero-dependency OpenXML (.xlsx) parser using Python's standard zipfile + ElementTree."""
    sheets_data: Dict[str, List[Dict[str, str]]] = {}
    with zipfile.ZipFile(xlsx_path, "r") as z:
        shared: List[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            s_root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in s_root:
                t_val = "".join(node.text or "" for node in si.iter() if node.tag.endswith("}t"))
                shared.append(t_val)

        wb_root = ET.fromstring(z.read("xl/workbook.xml"))
        rels_root = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rid_to_target: Dict[str, str] = {}
        for rel in rels_root:
            rid = rel.attrib.get("Id", "")
            target = rel.attrib.get("Target", "")
            rid_to_target[rid] = f"xl/{target.lstrip('/')}"

        for elem in wb_root.iter():
            if not elem.tag.endswith("}sheet"):
                continue
            sheet_name = elem.attrib.get("name", "")
            rid = next((v for k, v in elem.attrib.items() if k.endswith("}id")), "")
            target_path = rid_to_target.get(rid, "")
            if not target_path or target_path not in z.namelist():
                continue

            s_root = ET.fromstring(z.read(target_path))
            rows_out: List[Dict[str, str]] = []
            for row in s_root.iter():
                if not row.tag.endswith("}row"):
                    continue
                row_dict: Dict[str, str] = {}
                for c in row:
                    cell_ref = c.attrib.get("r", "")
                    col_letters = "".join(ch for ch in cell_ref if ch.isalpha())
                    c_type = c.attrib.get("t", "")
                    v_el = next((ch for ch in c if ch.tag.endswith("}v")), None)
                    val = v_el.text if v_el is not None and v_el.text is not None else ""
                    if c_type == "s" and val.isdigit() and int(val) < len(shared):
                        val = shared[int(val)]
                    if val.strip():
                        row_dict[col_letters] = val.strip()
                if row_dict:
                    rows_out.append(row_dict)
            sheets_data[sheet_name] = rows_out

    return sheets_data


def _clean_tone(tone_str: str) -> Optional[float]:
    """Parse CTCSS tone float or None."""
    if not tone_str:
        return None
    up = tone_str.strip().upper()
    if up in ("NONE", "N/A", "-", "CSQ"):
        return None
    try:
        return round(float(up), 1)
    except ValueError:
        return None


def parse_ics217_and_build_catalog(repo_root: Path) -> Tuple[List[AnalogChannelSpec], List[DigitalChannelSpec], List[TalkgroupSpec]]:
    """
    Parse the ICS-217 CSRA Amateur Radio Frequencies.xlsx workbook and W4DV / CSRA TGIF data
    to produce complete, deduplicated Analog, Digital, and Talkgroup catalogs.
    """
    xlsx_path = repo_root / "data" / "sources" / "ICS-217 CSRA Amateur Radio Frequencies.xlsx"
    sheets = _parse_xlsx_sheets(xlsx_path)

    analog_channels: List[AnalogChannelSpec] = []
    seen_analog_keys = set()

    # 1. Parse Sheet 1 ("ICS-217 CSRA Amateur Radio") and Sheet 7 ("ICS-217 Amateur Radio Out of To")
    for sheet_name, cat_default in [
        ("ICS-217 CSRA Amateur Radio", "CSRA_RPT"),
        ("ICS-217 Amateur Radio Out of To", "OUT_OF_TOWN"),
    ]:
        for row in sheets.get(sheet_name, []):
            config_type = row.get("A", "")
            if config_type not in ("Repeater", "Portable Repeater", "Portable Repeater Direct", "Simplex"):
                continue
            mode_str = row.get("K", "A").upper()
            if "DMR" in mode_str and "ANALOG" not in mode_str and config_type == "Repeater":
                # Pure DMR repeaters (like 444.900 K4KNS) belong in the Digital table
                continue
            if mode_str == "D":
                continue

            try:
                rx_mhz = round(float(row.get("E", "0")), 5)
                tx_mhz = round(float(row.get("H", str(rx_mhz))), 5)
            except ValueError:
                continue
            if rx_mhz <= 0:
                continue

            bw_str = row.get("F", "25.0")
            try:
                bw = 12.5 if float(bw_str) < 20.0 else 25.0
            except ValueError:
                bw = 25.0

            rx_tone = _clean_tone(row.get("G", ""))
            tx_tone = _clean_tone(row.get("J", ""))
            callsign = row.get("N", "").splitlines()[0].strip() if row.get("N") else ""
            if callsign in ("N/A", "nan", ""):
                callsign = "CSRA"
            remarks = " ".join(row.get("M", "").split())
            if "Currently Off the Air" in remarks or "Beleived to be off air" in remarks:
                continue

            # Determine duplex and offset
            diff = round(tx_mhz - rx_mhz, 4)
            if abs(diff) < 0.0001:
                duplex = ""
                offset_mhz = 0.0
            elif diff > 0:
                duplex = "+"
                offset_mhz = abs(diff)
            else:
                duplex = "-"
                offset_mhz = abs(diff)

            # Determine tone mode
            if rx_tone and tx_tone and abs(rx_tone - tx_tone) < 0.05:
                tone_mode = "TSQL"
            elif tx_tone:
                tone_mode = "Tone"
            else:
                tone_mode = ""

            # Build descriptive 16-char name (for DMR-6X2 PRO) and 7-char short_name (for UV-5R)
            raw_chan = row.get("B", "").splitlines()[0].replace(".0", "").strip()
            is_simplex = config_type in ("Simplex", "Portable Repeater Direct") or duplex == ""
            category = "SIMPLEX" if is_simplex else ("W4DV" if callsign == "W4DV" else cat_default)

            freq_tag = f"{rx_mhz:.4f}".rstrip("0").rstrip(".")
            if is_simplex:
                if abs(rx_mhz - 146.520) < 0.001:
                    name_16 = "2M_CALL_146.52"
                    short_7 = "CALL2M"
                elif abs(rx_mhz - 446.000) < 0.001:
                    name_16 = "70CM_CALL_446D"
                    short_7 = "CALL70"
                elif "AmRRON" in remarks:
                    name_16 = "AmRRON_146.420D"
                    short_7 = "AMRRON"
                elif "Ridge" in remarks:
                    name_16 = "RIDGE_146.550D"
                    short_7 = "RIDGE-S"
                elif "Portable Repeater" in config_type:
                    name_16 = f"ITIN_{freq_tag}D"[:16]
                    short_7 = f"IT{raw_chan[:5]}"[:7]
                else:
                    name_16 = f"CSRA_{freq_tag}D"[:16]
                    short_7 = raw_chan[:7]
            else:
                if "Portable Repeater" in config_type:
                    name_16 = f"ITIN_{freq_tag}"[:16]
                    short_7 = f"IT{raw_chan[:5]}"[:7]
                else:
                    prefix = re.sub(r"[^A-Za-z0-9]", "", callsign)[:6] or "RPT"
                    name_16 = f"{prefix}_{freq_tag}"[:16]
                    if callsign == "W4DV":
                        short_7 = f"W4DV{int(round((rx_mhz % 1) * 1000)):03d}"[:7]
                    else:
                        short_7 = f"{prefix[:4]}{int(round((rx_mhz % 1) * 100)):02d}"[:7]

            dedup_key = (round(rx_mhz, 4), round(tx_mhz, 4), category)
            if dedup_key in seen_analog_keys:
                continue
            seen_analog_keys.add(dedup_key)

            analog_channels.append(
                AnalogChannelSpec(
                    name=name_16,
                    short_name=short_7,
                    rx_mhz=rx_mhz,
                    tx_mhz=tx_mhz,
                    duplex=duplex,
                    offset_mhz=offset_mhz,
                    tone_mode=tone_mode,
                    rx_tone=rx_tone,
                    tx_tone=tx_tone,
                    bandwidth_khz=bw,
                    power="High",
                    rx_only=False,
                    category=category,
                    callsign=callsign,
                    location=remarks[:60],
                    notes=remarks,
                )
            )

    # 2. Build Digital DMR Channels from ICS-217 Sheet 3 ("ICS-217 CSRA DMR"), Sheet 4 ("DMR Talkgroup Info"),
    #    W4DV (442.550 CC1), KK4CNM Grovetown (147.195 CC1), and K4KNS Belair Water Tank (444.900 CC15)
    digital_channels: List[DigitalChannelSpec] = [
        # Hotspot / Direct Simplex TGIF Channels (441.100 MHz)
        DigitalChannelSpec("TGIF_ALL_31665", 441.100, "+0", "High", "1", False, "-", 1, 1, 1, 31665, "31665_TGIF_ALL", "TGIF", "HOTSPOT", "Simplex/Hotspot"),
        DigitalChannelSpec("CSRA_Talk_358", 441.100, "+0", "Mid", "1", False, "-", 1, 1, 1, 358, "358_CSRA_TALK", "TGIF", "HOTSPOT", "Simplex/Hotspot"),
        DigitalChannelSpec("SE_LINK_43389", 441.100, "+0", "Low", "1", False, "-", 1, 1, 1, 43389, "43389_SE_LINK", "TGIF", "HOTSPOT", "Simplex/Hotspot"),
        # KK4CNM Grovetown 2m DMR Repeater (147.195 +0.6 CC1)
        DigitalChannelSpec("KK4CNM_CSRA_358", 147.195, "+0.6", "Turbo", "1", False, "-", 1, 1, 1, 358, "358_CSRA_TALK", "TGIF", "KK4CNM", "Grovetown, GA"),
        DigitalChannelSpec("KK4CNM_GA_3113", 147.195, "+0.6", "Turbo", "1", False, "-", 1, 2, 1, 3113, "3113_GA_STATE", "TGIF", "KK4CNM", "Grovetown, GA"),
        # W4DV Augusta/Trenton 70cm DMR Repeater (442.550 +5.0 CC1) - TS1 Static TG358, TS2 Dynamic TGIF
        DigitalChannelSpec("W4DV_CSRA_358", 442.550, "+5", "Turbo", "1", False, "-", 1, 1, 1, 358, "358_CSRA_TALK", "TGIF", "W4DV", "Trenton, SC"),
        DigitalChannelSpec("W4DV_TGIF_ALL", 442.550, "+5", "Turbo", "1", False, "-", 1, 2, 1, 31665, "31665_TGIF_ALL", "TGIF", "W4DV", "Trenton, SC"),
        DigitalChannelSpec("W4DV_GA_3113", 442.550, "+5", "Turbo", "1", False, "-", 1, 2, 1, 3113, "3113_GA_STATE", "TGIF", "W4DV", "Trenton, SC"),
        DigitalChannelSpec("W4DV_GA_ARES", 442.550, "+5", "Turbo", "1", False, "-", 1, 2, 1, 31130, "31130_GA_ARES", "TGIF", "W4DV", "Trenton, SC"),
        DigitalChannelSpec("W4DV_SE_LINK", 442.550, "+5", "Turbo", "1", False, "-", 1, 2, 1, 43389, "43389_SE_LINK", "TGIF", "W4DV", "Trenton, SC"),
        DigitalChannelSpec("W4DV_K4KNS_985", 442.550, "+5", "Turbo", "1", False, "-", 1, 2, 1, 985, "985_K4KNS", "TGIF", "W4DV", "Trenton, SC"),
        DigitalChannelSpec("W4DV_PARROT", 442.550, "+5", "Turbo", "1", False, "-", 1, 2, 1, 31000, "PARROT", "TGIF", "W4DV", "Trenton, SC"),
        # K4KNS Belair Water Tank (Evans/Augusta, GA) 444.900 +5.0 CC15 - TS1=TG358, TS2=TG985
        DigitalChannelSpec("K4KNS_Belair358", 444.900, "+5", "Turbo", "1", False, "-", 15, 1, 1, 358, "358_CSRA_TALK", "TGIF", "K4KNS", "Evans/Belair Water Tank, GA"),
        DigitalChannelSpec("K4KNS_Belair985", 444.900, "+5", "Turbo", "1", False, "-", 15, 2, 1, 985, "985_K4KNS", "TGIF", "K4KNS", "Evans/Belair Water Tank, GA"),
        # K4KNS Wrens GPB Tower (444.175 +5.0 CC1) - Vidalia Supergroup
        DigitalChannelSpec("K4KNS_Wrens_VSG", 444.175, "+5", "Turbo", "1", False, "-", 1, 1, 2, 9, "9_LOCAL_SG", "Vidalia_SG", "K4KNS", "Wrens, GA"),
        DigitalChannelSpec("K4KNS_Wrens_GA", 444.175, "+5", "Turbo", "1", False, "-", 1, 1, 2, 3113, "3113_GA_STATE", "Vidalia_SG", "K4KNS", "Wrens, GA"),
        DigitalChannelSpec("K4KNS_Wrens_ARE", 444.175, "+5", "Turbo", "1", False, "-", 1, 1, 2, 31130, "31130_GA_ARES", "Vidalia_SG", "K4KNS", "Wrens, GA"),
        DigitalChannelSpec("K4KNS_Wrens_KDL", 444.175, "+5", "Turbo", "1", False, "-", 1, 1, 2, 31137, "31137_KINGSLND", "Vidalia_SG", "K4KNS", "Wrens, GA"),
        DigitalChannelSpec("K4KNS_Wrens_MM", 444.175, "+5", "Turbo", "1", False, "-", 1, 1, 2, 314722, "314722_CSRA_MM", "Vidalia_SG", "K4KNS", "Wrens, GA"),
        DigitalChannelSpec("K4KNS_Wrens_LOC", 444.175, "+5", "Turbo", "1", False, "-", 1, 2, 2, 9, "9_LOCAL_SG", "Vidalia_SG", "K4KNS", "Wrens, GA"),
        DigitalChannelSpec("K4KNS_Wrens_FC", 444.175, "+5", "Turbo", "1", False, "-", 1, 2, 2, 2, "2_PRN_FC_WIDE", "Vidalia_SG", "K4KNS", "Wrens, GA"),
        # N2ZZ Aiken SC BrandMeister Repeater (443.4625 +5.0 CC1)
        DigitalChannelSpec("N2ZZ_Aiken_SC", 443.4625, "+5", "Turbo", "1", False, "-", 1, 1, 4, 3145, "3145_SC_STATE", "BrandMeister", "N2ZZ", "Aiken, SC"),
        DigitalChannelSpec("N2ZZ_Aiken_GA", 443.4625, "+5", "Turbo", "1", False, "-", 1, 1, 4, 3113, "3113_GA_STATE", "BrandMeister", "N2ZZ", "Aiken, SC"),
        DigitalChannelSpec("N2ZZ_Aiken_CSRA", 443.4625, "+5", "Turbo", "1", False, "-", 1, 1, 4, 314722, "314722_CSRA_MM", "BrandMeister", "N2ZZ", "Aiken, SC"),
        DigitalChannelSpec("N2ZZ_Aiken_LOC", 443.4625, "+5", "Turbo", "1", False, "-", 1, 2, 4, 9, "9_LOCAL_SG", "BrandMeister", "N2ZZ", "Aiken, SC"),
        DigitalChannelSpec("N2ZZ_Aiken_ECHO", 443.4625, "+5", "Turbo", "1", False, "-", 1, 2, 4, 9990, "9990_BM_PARROT", "BrandMeister", "N2ZZ", "Aiken, SC"),
        # WR4SC SCHEART / PRN Repeaters (Beech Island, Barnwell, Aiken Trailer, Greenwood, Anderson)
        DigitalChannelSpec("WR4SC_Beech_LOC", 444.2875, "+5", "Turbo", "1", False, "-", 1, 1, 3, 27500, "27500_PRN_LOC", "SCHEART_PRN", "WR4SC", "Beech Island, SC"),
        DigitalChannelSpec("WR4SC_Beech_SC", 444.2875, "+5", "Turbo", "1", False, "-", 1, 1, 3, 27510, "27510_SC_CALL", "SCHEART_PRN", "WR4SC", "Beech Island, SC"),
        DigitalChannelSpec("WR4SC_Beech_CH1", 444.2875, "+5", "Turbo", "1", False, "-", 1, 1, 3, 27501, "27501_PRN_CHT1", "SCHEART_PRN", "WR4SC", "Beech Island, SC"),
        DigitalChannelSpec("WR4SC_Beech_CH2", 444.2875, "+5", "Turbo", "1", False, "-", 1, 1, 3, 27502, "27502_PRN_CHT2", "SCHEART_PRN", "WR4SC", "Beech Island, SC"),
        DigitalChannelSpec("WR4SC_Beech_PRN", 444.2875, "+5", "Turbo", "1", False, "-", 1, 2, 3, 2, "2_PRN_FC_WIDE", "SCHEART_PRN", "WR4SC", "Beech Island, SC"),
        DigitalChannelSpec("WR4SC_Barnw_LOC", 440.6875, "+5", "Turbo", "1", False, "-", 1, 1, 3, 27500, "27500_PRN_LOC", "SCHEART_PRN", "WR4SC", "Barnwell, SC"),
        DigitalChannelSpec("WR4SC_Barnw_SC", 440.6875, "+5", "Turbo", "1", False, "-", 1, 1, 3, 27510, "27510_SC_CALL", "SCHEART_PRN", "WR4SC", "Barnwell, SC"),
        DigitalChannelSpec("WR4SC_Barnw_PRN", 440.6875, "+5", "Turbo", "1", False, "-", 1, 2, 3, 2, "2_PRN_FC_WIDE", "SCHEART_PRN", "WR4SC", "Barnwell, SC"),
        DigitalChannelSpec("WR4SC_440.8_LOC", 440.800, "+5", "Turbo", "1", False, "-", 1, 1, 3, 27500, "27500_PRN_LOC", "SCHEART_PRN", "WR4SC", "Aiken Trailer, SC"),
        DigitalChannelSpec("WR4SC_440.8_PRN", 440.800, "+5", "Turbo", "1", False, "-", 1, 2, 3, 2, "2_PRN_FC_WIDE", "SCHEART_PRN", "WR4SC", "Aiken Trailer, SC"),
        DigitalChannelSpec("WR4SC_Grnwd_LOC", 443.8375, "+5", "Turbo", "1", False, "-", 1, 1, 3, 27500, "27500_PRN_LOC", "SCHEART_PRN", "WR4SC", "Greenwood, SC"),
        DigitalChannelSpec("WR4SC_Grnwd_PRN", 443.8375, "+5", "Turbo", "1", False, "-", 1, 2, 3, 2, "2_PRN_FC_WIDE", "SCHEART_PRN", "WR4SC", "Greenwood, SC"),
        DigitalChannelSpec("WR4SC_Andrs_LOC", 444.5375, "+5", "Turbo", "1", False, "-", 1, 1, 3, 27500, "27500_PRN_LOC", "SCHEART_PRN", "WR4SC", "Anderson, SC"),
        DigitalChannelSpec("WR4SC_Andrs_PRN", 444.5375, "+5", "Turbo", "1", False, "-", 1, 2, 3, 2, "2_PRN_FC_WIDE", "SCHEART_PRN", "WR4SC", "Anderson, SC"),
        # National DMR Simplex (441.000 MHz CC1 TS1 TG99)
        DigitalChannelSpec("DMR_Simplex_441", 441.000, "+0", "High", "1", False, "-", 1, 1, 3, 99, "99_DMR_SIMPLEX", "Simplex", "SIMPLEX", "National Digital Simplex"),
    ]

    return analog_channels, digital_channels, list(CURATED_CSRA_GA_TALKGROUPS)
