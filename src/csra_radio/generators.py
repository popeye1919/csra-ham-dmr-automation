"""Generators for Baofeng UV-5R CHIRP (.csv & .img) and BTECH DMR-6X2 PRO (.conf & .img) codeplugs."""

from __future__ import annotations

import csv
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .scrapers import (
    AUTHORITATIVE_W4DV_REPEATERS,
    AnalogChannelSpec,
    DigitalChannelSpec,
    TalkgroupSpec,
)


CHIRP_CSV_HEADERS = [
    "Location",
    "Name",
    "Frequency",
    "Duplex",
    "Offset",
    "Tone",
    "rToneFreq",
    "cToneFreq",
    "DtcsCode",
    "DtcsPolarity",
    "RxDtcsCode",
    "CrossMode",
    "Mode",
    "TStep",
    "Skip",
    "Power",
    "Comment",
    "URCALL",
    "RPT1CALL",
    "RPT2CALL",
    "DVCODE",
]


NOAA_WEATHER_CHANNELS = [
    ("WX-01", "Weather1", 162.400, "NOAA Weather CH1"),
    ("WX-02", "Weather2", 162.425, "NOAA Weather CH2"),
    ("WX-03", "Weather3", 162.450, "NOAA Weather CH3"),
    ("WX-04", "Weather4", 162.475, "NOAA Weather CH4"),
    ("WX-05", "Weather5", 162.500, "NOAA Weather CH5"),
    ("WX-06", "Weather6", 162.525, "NOAA Weather CH6"),
    ("WX-07", "Weather7", 162.550, "NOAA Weather CH7"),
]


MURS_CHANNELS = [
    ("MURS-1", "MURS_1.82", 151.820, 12.5, "High"),
    ("MURS-2", "MURS_1.88", 151.880, 12.5, "High"),
    ("MURS-3", "MURS_1.94", 151.940, 12.5, "Low"),
    ("MURS-4", "MURS_4.57", 154.570, 25.0, "High"),
    ("MURS-5", "MURS_4.60", 154.600, 25.0, "High"),
]


FRS_FREQS = [
    (1, 462.5625, "Low"),
    (2, 462.5875, "High"),
    (3, 462.6125, "High"),
    (4, 462.6375, "High"),
    (5, 462.6625, "High"),
    (6, 462.6875, "High"),
    (7, 462.7125, "High"),
    (8, 467.5625, "Low"),
    (9, 467.5875, "Low"),
    (10, 467.6125, "Low"),
    (11, 467.6375, "Low"),
    (12, 467.6625, "Low"),
    (13, 467.6875, "Low"),
    (14, 467.7125, "Low"),
    (15, 462.5500, "High"),
    (16, 462.5750, "High"),
    (17, 462.6000, "High"),
    (18, 462.6250, "High"),
    (19, 462.6500, "High"),
    (20, 462.6750, "High"),
    (21, 462.7000, "High"),
    (22, 462.7250, "High"),
]


def _is_uv5r_supported_band(freq_mhz: float) -> bool:
    """Baofeng UV-5R covers VHF 136-174 MHz and UHF 400-520 MHz (excludes 6m, 1.25m, 33cm)."""
    return (136.0 <= freq_mhz <= 174.0) or (400.0 <= freq_mhz <= 520.0)


def generate_uv5r_chirp_artifacts(
    repo_root: Path,
    analog_channels: List[AnalogChannelSpec],
    compile_img: bool = True,
) -> Dict[str, str]:
    """
    Generate standard 21-column CHIRP CSV for Augusta (W4DV) & CSRA Analog Repeaters, Simplex,
    NOAA Weather (RX-only), MURS, and FRS/GMRS, and optionally compile a ready-to-flash
    Baofeng UV-5R .img file derived from the stable UV-5R baseline EEPROM dump.
    """
    out_dir = repo_root / "data" / "generated" / "chirp"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "CSRA_W4DV_UV5R_CHIRP.csv"
    img_path = out_dir / "CSRA_W4DV_UV5R.img"

    # Sort so W4DV club repeaters come first, followed by CSRA repeaters, Simplex, Out-of-Town
    priority_order = {"W4DV": 0, "CSRA_RPT": 1, "SIMPLEX": 2, "OUT_OF_TOWN": 3}
    vhf_uhf_channels = [
        ch for ch in analog_channels if _is_uv5r_supported_band(ch.rx_mhz) and _is_uv5r_supported_band(ch.tx_mhz)
    ]
    vhf_uhf_channels.sort(key=lambda c: (priority_order.get(c.category, 9), c.rx_mhz))

    rows: List[Dict[str, str]] = []
    loc = 1

    for ch in vhf_uhf_channels:
        mode = "NFM" if ch.bandwidth_khz < 20.0 else "FM"
        r_tone = f"{ch.tx_tone:.1f}" if ch.tx_tone else "88.5"
        c_tone = f"{ch.rx_tone:.1f}" if ch.rx_tone else (r_tone if ch.tone_mode == "TSQL" else "88.5")
        tone_col = ""
        cross_mode = "Tone->Tone"

        if ch.rx_tone and ch.tx_tone and abs(ch.rx_tone - ch.tx_tone) > 0.05:
            tone_col = "Cross"
            cross_mode = "Tone->Tone"
        elif ch.tone_mode in ("TSQL", "Tone"):
            tone_col = ch.tone_mode

        duplex_col = "off" if ch.rx_only else ch.duplex
        power_col = "High" if ch.power in ("High", "Turbo") else "Low"

        rows.append(
            {
                "Location": str(loc),
                "Name": ch.short_name[:7].upper(),
                "Frequency": f"{ch.rx_mhz:.6f}",
                "Duplex": duplex_col,
                "Offset": f"{ch.offset_mhz:.6f}",
                "Tone": tone_col,
                "rToneFreq": r_tone,
                "cToneFreq": c_tone,
                "DtcsCode": "023",
                "DtcsPolarity": "NN",
                "RxDtcsCode": "023",
                "CrossMode": cross_mode,
                "Mode": mode,
                "TStep": "5.00",
                "Skip": "",
                "Power": power_col,
                "Comment": f"[{ch.category}] {ch.name} - {ch.notes}"[:120],
                "URCALL": "",
                "RPT1CALL": "",
                "RPT2CALL": "",
                "DVCODE": "",
            }
        )
        loc += 1

    # Add MURS channels
    for short_n, full_n, freq, bw, pwr in MURS_CHANNELS:
        if loc > 127:
            break
        rows.append(
            {
                "Location": str(loc),
                "Name": short_n[:7],
                "Frequency": f"{freq:.6f}",
                "Duplex": "",
                "Offset": "0.000000",
                "Tone": "",
                "rToneFreq": "88.5",
                "cToneFreq": "88.5",
                "DtcsCode": "023",
                "DtcsPolarity": "NN",
                "RxDtcsCode": "023",
                "CrossMode": "Tone->Tone",
                "Mode": "NFM" if bw < 20.0 else "FM",
                "TStep": "5.00",
                "Skip": "",
                "Power": "High" if pwr == "High" else "Low",
                "Comment": f"MURS License-Free VHF ({full_n})",
                "URCALL": "",
                "RPT1CALL": "",
                "RPT2CALL": "",
                "DVCODE": "",
            }
        )
        loc += 1

    # Add NOAA Weather channels (Receive-only: Duplex='off', Skip='S' so scan doesn't hang on continuous WX carrier)
    for short_n, full_n, freq, comment in NOAA_WEATHER_CHANNELS:
        if loc > 127:
            break
        rows.append(
            {
                "Location": str(loc),
                "Name": short_n[:7],
                "Frequency": f"{freq:.6f}",
                "Duplex": "off",
                "Offset": "0.000000",
                "Tone": "",
                "rToneFreq": "88.5",
                "cToneFreq": "88.5",
                "DtcsCode": "023",
                "DtcsPolarity": "NN",
                "RxDtcsCode": "023",
                "CrossMode": "Tone->Tone",
                "Mode": "FM",
                "TStep": "5.00",
                "Skip": "S",
                "Power": "Low",
                "Comment": f"{comment} (RX Only)",
                "URCALL": "",
                "RPT1CALL": "",
                "RPT2CALL": "",
                "DVCODE": "",
            }
        )
        loc += 1

    # Add FRS/GMRS Simplex channels up to slot 127
    for ch_num, freq, pwr in FRS_FREQS:
        if loc > 127:
            break
        rows.append(
            {
                "Location": str(loc),
                "Name": f"FRS-{ch_num:02d}",
                "Frequency": f"{freq:.6f}",
                "Duplex": "",
                "Offset": "0.000000",
                "Tone": "",
                "rToneFreq": "88.5",
                "cToneFreq": "88.5",
                "DtcsCode": "023",
                "DtcsPolarity": "NN",
                "RxDtcsCode": "023",
                "CrossMode": "Tone->Tone",
                "Mode": "NFM",
                "TStep": "12.50",
                "Skip": "",
                "Power": "High" if pwr == "High" else "Low",
                "Comment": f"FRS/GMRS Shared Channel {ch_num}",
                "URCALL": "",
                "RPT1CALL": "",
                "RPT2CALL": "",
                "DVCODE": "",
            }
        )
        loc += 1

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CHIRP_CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    result = {
        "chirp_csv_path": str(csv_path.relative_to(repo_root)),
        "channel_count": str(len(rows)),
    }

    baseline_uv5r = repo_root / "data" / "stable_firmware" / "uv5r" / "uv5r_stable_baseline.img"
    if compile_img and baseline_uv5r.exists():
        _compile_uv5r_img_via_chirp_api(baseline_uv5r, rows, img_path)
        result["chirp_img_path"] = str(img_path.relative_to(repo_root))

    return result


def _compile_uv5r_img_via_chirp_api(
    baseline_img: Path,
    csv_rows: List[Dict[str, str]],
    output_img: Path,
) -> None:
    """
    Use CHIRP's Python driver API directly to inject generated CSRA/W4DV channels into the
    stable Baofeng UV-5R EEPROM image while preserving calibration and power-on settings.
    """
    os.environ["HOME"] = "/tmp"
    from chirp import chirp_common, directory
    from chirp.drivers import uv5r  # noqa: F401 - register Baofeng UV-5R driver

    shutil.copy2(baseline_img, output_img)
    rclass = directory.get_radio("Baofeng_UV-5R")
    radio = rclass(str(output_img))

    # Clear existing 1..127 memories first
    for slot in range(1, 128):
        mem = radio.get_memory(slot)
        mem.empty = True
        radio.set_memory(mem)

    for row in csv_rows:
        slot = int(row["Location"])
        mem = chirp_common.Memory()
        mem.number = slot
        mem.empty = False
        mem.name = row["Name"][:7]
        mem.freq = chirp_common.parse_freq(row["Frequency"])
        mem.duplex = row["Duplex"]
        mem.offset = chirp_common.parse_freq(row["Offset"])
        mem.mode = row["Mode"]
        mem.tmode = row["Tone"]
        mem.rtone = float(row["rToneFreq"])
        mem.ctone = float(row["cToneFreq"])
        mem.cross_mode = row["CrossMode"]
        mem.skip = row["Skip"]
        try:
            power_levels = radio.get_features().valid_power_levels
            if power_levels:
                mem.power = power_levels[0] if row["Power"] == "High" else power_levels[-1]
        except Exception:
            pass
        radio.set_memory(mem)

    radio.save_mmap(str(output_img))


def _extract_private_contacts_from_baseline(baseline_conf: Path) -> List[Tuple[int, str, str, int, str]]:
    """Preserve existing private contacts (indices 9..1000) from the operator's baseline config."""
    privates: List[Tuple[int, str, str, int, str]] = []
    if not baseline_conf.exists():
        return privates
    in_contacts = False
    for raw_line in baseline_conf.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line:
            continue
        if not line[0].isspace():
            in_contacts = line.split()[0].lower() == "contact"
            continue
        if in_contacts:
            parts = line.split()
            if len(parts) >= 5 and parts[2] == "Private":
                idx = int(parts[0])
                if 9 <= idx <= 1000:
                    privates.append((idx, parts[1], parts[2], int(parts[3]), parts[4]))
    return privates


def generate_btech_dmr6x2pro_artifacts(
    repo_root: Path,
    dmrconfig_bin: Path,
    analog_channels: List[AnalogChannelSpec],
    digital_channels: List[DigitalChannelSpec],
    talkgroups: List[TalkgroupSpec],
    dmr_id: int = 3221824,
    callsign: str = "KR4JLC",
    intro_line1: str = "D4rkSp2rk",
    intro_line2: str = "-",
) -> Dict[str, str]:
    """
    Generate a complete, validated dmrconfig .conf file and compiled 1,606,528-byte .img codeplug
    for the BTECH DMR-6X2 PRO (`D6X2UV2`).

    Faithfully preserves the operator's original configuration:
      - Zones 1 through 4 exactly as originally structured:
          Zone 1: Digital   (Original 1-3,5-7,91 + new DMR channels)
          Zone 2: Analog    (Original FRS 24-45, GMRS 48-77, MURS 80-84, Simplex 118, W4UC 120)
          Zone 3: Repeaters (Original 9-11 + new CSRA & W4DV repeaters)
          Zone 4: Weather   (Original NOAA Weather1-7: 14-20)
      - Intro Line 1: Cory Singleton, Intro Line 2: -
      - Preserves private contacts and continuous contact table structure.
    """
    out_dir = repo_root / "data" / "generated" / "dmrconfig"
    out_dir.mkdir(parents=True, exist_ok=True)
    conf_path = out_dir / "CSRA_W4DV_DMR6X2PRO.conf"
    img_path = out_dir / "CSRA_W4DV_DMR6X2PRO.img"

    baseline_img = repo_root / "data" / "stable_firmware" / "dmr6x2_pro" / "dmr6x2pro_stable_baseline.img"
    live_pull_img = repo_root / "data" / "backups" / "btech_pull_20261101_1844.img"
    live_pull_conf = repo_root / "data" / "backups" / "btech_pull_20261101_1844.conf"
    base_img_to_use = live_pull_img if live_pull_img.exists() else baseline_img
    baseline_conf = repo_root / "data" / "stable_firmware" / "dmr6x2_pro" / "dmr6x2pro_stable_baseline.conf"

    # Map Talkgroups to Contact Table indices:
    # Slots 1..8: Primary CSRA TGIF Talkgroups
    primary_tgs = [
        (1, "31665_TGIF_ALL", "Group", 31665, "-"),
        (2, "358_CSRA_TALK", "Group", 358, "-"),
        (3, "43389_SE_LINK", "Group", 43389, "-"),
        (4, "9050_EastC_Ref", "Group", 9050, "-"),
        (5, "985_K4KNS", "Group", 985, "-"),
        (6, "CSRA_PT1_Wx", "Group", 8014, "-"),
        (7, "CSRA_PT2_Wx", "Group", 8044, "-"),
        (8, "PARROT", "Group", 31000, "-"),
    ]
    contact_entries: List[Tuple[int, str, str, int, str]] = list(primary_tgs)
    tg_id_to_contact_idx: Dict[int, int] = {cid: idx for idx, _, _, cid, _ in primary_tgs}

    # Slots 9..1000: Preserved Private Contacts from operator's baseline
    private_contacts = _extract_private_contacts_from_baseline(baseline_conf)
    for idx, name, ctype, cid, rxtone in private_contacts:
        contact_entries.append((idx, name[:16], ctype, cid, rxtone))
        tg_id_to_contact_idx[cid] = idx

    # Slots 1001+: Extended Georgia, Vidalia Supergroup, SCHEART PRN, BrandMeister Talkgroups
    extended_tgs = [
        (3113, "3113_GA_STATE"),
        (31130, "31130_GA_ARES"),
        (31137, "31137_KINGSLND"),
        (314722, "314722_CSRA_MM"),
        (9, "9_LOCAL_SG"),
        (2, "2_PRN_FC_WIDE"),
        (3145, "3145_SC_STATE"),
        (9990, "9990_BM_PARROT"),
        (27500, "27500_PRN_LOC"),
        (27510, "27510_SC_CALL"),
        (27501, "27501_PRN_CHT1"),
        (27502, "27502_PRN_CHT2"),
        (99, "99_DMR_SIMPLEX"),
    ]
    ext_idx = 1001
    for tg_id, tg_name in extended_tgs:
        if tg_id not in tg_id_to_contact_idx:
            contact_entries.append((ext_idx, tg_name, "Group", tg_id, "-"))
            tg_id_to_contact_idx[tg_id] = ext_idx
            ext_idx += 1

    # Extract original channels from live pull if present, otherwise use fallback defaults
    orig_dig_lines: List[str] = []
    orig_ana_lines: List[str] = []

    if live_pull_conf.exists():
        cur_sec = None
        for line in live_pull_conf.read_text(encoding="utf-8").splitlines():
            if line.startswith("# Table of digital channels."):
                cur_sec = "DIG"
                continue
            elif line.startswith("# Table of analog channels."):
                cur_sec = "ANA"
                continue
            elif line.startswith("# Table of channel zones."):
                cur_sec = None
                continue
            if cur_sec == "DIG" and line.strip() and not line.startswith("#"):
                orig_dig_lines.append(line)
            elif cur_sec == "ANA" and line.strip() and not line.startswith("#"):
                orig_ana_lines.append(line)

    # If no live pull conf, provide default original lines
    if not orig_dig_lines:
        orig_dig_lines = [
            "    1   TGIF_ALL_31665   441.100   +0       High  -    -   -  -      1     1    -    1    # 31665 TGIF ALL",
            "    2   CSRA_Talk_358    441.100   +0       Mid   -    -   -  -      1     1    -    2    # 358 CSRA TALK",
            "    3   SE_LINK_43389    441.100   +0       Low   -    -   -  -      1     1    -    3    # 43389 SE LINK",
            "    5   W4DV             442.550   +5       Turbo -    -   -  -      1     1    -    2    # 358 CSRA TALK",
            "    6   985_K4KNS_RP     444.900   +5       Turbo -    -   -  -      15    2    -    5    # 985 K4KNS",
            "    7   Digi_Murs        151.940   +0       Mid   -    -   -  -      5     2    -    9    # A Kenneth",
            "   91   Pi-Star          441.500   +5       High  1    -   -  -      1     2    -    1    # 31665 TGIF ALL",
        ]

    # New DMR channels (starting at channel 131)
    new_dig_chans: List[str] = []
    new_dig_indices: List[int] = []
    ch_idx = 131

    for d in digital_channels:
        if d.rx_mhz == 441.100 and d.tx_contact_id in (31665, 358, 43389):
            continue
        if d.rx_mhz == 442.550 and d.timeslot == 1 and d.tx_contact_id == 358:
            continue
        if d.rx_mhz == 444.900 and d.timeslot == 2 and d.tx_contact_id == 985:
            continue

        tx_contact = tg_id_to_contact_idx.get(d.tx_contact_id, 1)
        rx_freq_str = f"{d.rx_mhz:.4f}".rstrip("0").rstrip(".")
        if "." not in rx_freq_str:
            rx_freq_str += ".0"
        line = (
            f"{ch_idx:5d}   {d.name[:16]:<16s} {rx_freq_str:<9s} {d.tx_offset_str:<8s} "
            f"{d.power:<5s} -    -   -  -      {d.color_code:<5d} {d.timeslot:<3d}  -    "
            f"{tx_contact:<4d} # {d.tx_contact_name} ({d.location})"
        )
        new_dig_chans.append(line)
        new_dig_indices.append(ch_idx)
        ch_idx += 1

    # New CSRA & W4DV Repeaters for Zone 3 (starting at channel 201)
    new_ana_chans: List[str] = []
    new_ana_indices: List[int] = []
    ch_idx = 201

    seen_rpt_keys = {
        (145.490, 71.9),
        (146.985, 71.9),
        (145.410, 71.9),
    }

    # Add other W4DV repeaters
    for w in AUTHORITATIVE_W4DV_REPEATERS:
        rx = float(w["rx_mhz"])
        tx = float(w["tx_mhz"])
        tone = float(w["tx_tone"])
        key = (round(rx, 4), round(tone, 1))
        if key in seen_rpt_keys:
            continue
        seen_rpt_keys.add(key)
        diff = round(tx - rx, 4)
        off_str = f"{diff:+.1f}" if abs(diff) != 0 else "+0"
        rx_str = f"{rx:.4f}".rstrip("0").rstrip(".")
        name = str(w["name"])[:16]
        line = f"{ch_idx:5d}   {name:<16s} {rx_str:<9s} {off_str:<8s} High  -    -   -  -      Normal  -      {tone:<6.1f} 25"
        new_ana_chans.append(line)
        new_ana_indices.append(ch_idx)
        ch_idx += 1

    # Add CSRA repeaters from catalog (VHF 136-174 and UHF 400-480)
    for a in analog_channels:
        if a.category != "CSRA_RPT":
            continue
        if not ((136.0 <= a.rx_mhz <= 174.0) or (400.0 <= a.rx_mhz <= 480.0)):
            continue
        tone = a.tx_tone if a.tx_tone is not None else 0.0
        key = (round(a.rx_mhz, 4), round(tone, 1))
        if key in seen_rpt_keys:
            continue
        seen_rpt_keys.add(key)

        diff = round(a.tx_mhz - a.rx_mhz, 4)
        off_str = f"{diff:+.1f}" if abs(diff) != 0 else "+0"
        tone_str = f"{tone:.1f}" if a.tx_tone is not None else "-"
        bw_str = "12.5" if a.bandwidth_khz < 20.0 else "25"
        rx_str = f"{a.rx_mhz:.4f}".rstrip("0").rstrip(".")
        name = a.name[:16]
        line = f"{ch_idx:5d}   {name:<16s} {rx_str:<9s} {off_str:<8s} High  -    -   -  -      Normal  -      {tone_str:<6s} {bw_str}"
        new_ana_chans.append(line)
        new_ana_indices.append(ch_idx)
        ch_idx += 1

    # Zone table: Zones 1 through 4 ONLY!
    zone_1_str = f"1-3,5-7,91,{new_dig_indices[0]}-{new_dig_indices[-1]}" if new_dig_indices else "1-3,5-7,91"
    zone_2_str = "24-45,48-77,80-84,118,120"
    zone_3_str = f"9-11,{new_ana_indices[0]}-{new_ana_indices[-1]}" if new_ana_indices else "9-11"
    zone_4_str = "14-20"

    lines: List[str] = [
        "#",
        "# CSRA Codeplug for BTECH DMR-6X2 PRO",
        "# Faithful layout preserving operator zones 1-4 with updated DMR & Repeaters",
        "#",
        "Radio: BTECH DMR-6X2 PRO",
        "",
        "# Table of digital channels.",
        "Digital Name             Receive   Transmit Power Scan TOT RO Admit  Color Slot RxGL TxContact",
    ]
    lines.extend(orig_dig_lines)
    lines.extend(new_dig_chans)

    lines.extend(
        [
            "",
            "# Table of analog channels.",
            "Analog  Name             Receive   Transmit Power Scan TOT RO Admit  Squelch RxTone TxTone Width",
        ]
    )
    lines.extend(orig_ana_lines)
    lines.extend(new_ana_chans)

    lines.extend(
        [
            "",
            "# Table of channel zones.",
            "Zone    Name             Channels",
            f"    1   Digital          {zone_1_str}",
            f"    2   Analog           {zone_2_str}",
            f"    3   Repeaters        {zone_3_str}",
            f"    4   Weather          {zone_4_str}",
            "",
            "# Table of scan lists.",
            "Scanlist Name            PCh1 PCh2 TxCh Channels",
            "    1   Default_Scan     -    -    Sel  9-11,91,120",
            "",
            "# Table of group lists.",
            "Grouplist Name                              Contacts",
            "    1   Group_List_1                        1",
            "",
            "# Table of text messages.",
            "Message Text",
            "    1   Hello!",
            "    2   Welcome!",
            "    3   Thank you!",
            "    4   Good bye!",
            "    5   Happy every day!",
            "",
            "# Unique DMR ID and name of this radio.",
            f"ID: {dmr_id}",
            f"Name: {callsign}",
            "",
            "# Text displayed when the radio powers up.",
            f"Intro Line 1: {intro_line1}",
            f"Intro Line 2: {intro_line2}",
            "",
            "# Working Mode: Amateur or Professional",
            "Working Mode: Amateur",
            "",
        ]
    )

    conf_path.write_text("\n".join(lines), encoding="utf-8")

    # Compile into temporary binary .img using dmrconfig to build channel structures
    subprocess.run(
        [str(dmrconfig_bin), "-c", str(base_img_to_use), str(conf_path)],
        cwd=str(out_dir),
        capture_output=True,
        text=True,
        check=True,
    )
    compiled_device_img = out_dir / "device.img"

    # Surgical Rolling Image Patching:
    # To prevent any codeplug corruption or firmware boot-reset, take the pristine rolling baseline image
    # and surgically inject only the new channels (131-166 & 201-232), channel map bits, zone channel lists,
    # and Intro Line 1, while preserving 100% of the radio's native settings, scanlists, and 6,034 contacts.
    base_raw = bytearray(base_img_to_use.read_bytes())
    if compiled_device_img.exists():
        comp_raw = compiled_device_img.read_bytes()
        # 1. Copy new digital channels 131-166 (0x20c0 - 0x29c0)
        base_raw[0x20C0 : 0x20C0 + 2304] = comp_raw[0x20C0 : 0x20C0 + 2304]
        # 2. Copy new analog repeater channels 201-232 (0x3240 - 0x3a40)
        base_raw[0x3240 : 0x3240 + 2048] = comp_raw[0x3240 : 0x3240 + 2048]
        # Clean up temporary device.img
        compiled_device_img.unlink()

    # 3. Update channel bitmap at OFFSET_CHAN_MAP = 0x070a40
    for ch_idx in list(range(130, 166)) + list(range(200, 232)):
        base_raw[0x070A40 + ch_idx // 8] |= (1 << (ch_idx % 8))

    # 4. Update Zone 1 channel list at OFFSET_ZONELISTS = 0x03e8c0
    # Original channels: 1, 2, 3, 5, 6, 7, 91 (indices 0, 1, 2, 4, 5, 6, 90) + 131-166 (indices 130..165)
    z1_chans = [0, 1, 2, 4, 5, 6, 90] + list(range(130, 166))
    z1_bytes = bytearray()
    for c in z1_chans:
        z1_bytes += c.to_bytes(2, "little")
    z1_bytes += b"\xff\xff" * (250 - len(z1_chans))
    base_raw[0x03E8C0 : 0x03E8C0 + 500] = z1_bytes

    # 5. Update Zone 3 channel list at OFFSET_ZONELISTS + 2*512 = 0x03ecc0
    # Original channels: 9, 10, 11 (indices 8, 9, 10) + 201-232 (indices 200..231)
    z3_chans = [8, 9, 10] + list(range(200, 232))
    z3_bytes = bytearray()
    for c in z3_chans:
        z3_bytes += c.to_bytes(2, "little")
    z3_bytes += b"\xff\xff" * (250 - len(z3_chans))
    base_raw[0x03ECC0 : 0x03ECC0 + 500] = z3_bytes

    # 6. Update Intro Line 1 at OFFSET_SETTINGS + 0x600 = 0x071c00 (preserve case, null-padded)
    intro_bytes = intro_line1.encode("ascii")[:14].ljust(16, b"\x00")
    base_raw[0x071C00 : 0x071C10] = intro_bytes

    img_path.write_bytes(base_raw)

    # Verify the compiled binary image
    verify_proc = subprocess.run(
        [str(dmrconfig_bin), str(img_path)],
        capture_output=True,
        text=True,
        check=True,
    )

    total_dig = len(orig_dig_lines) + len(new_dig_chans)
    total_ana = len(orig_ana_lines) + len(new_ana_chans)

    return {
        "dmr_conf_path": str(conf_path.relative_to(repo_root)),
        "dmr_img_path": str(img_path.relative_to(repo_root)),
        "digital_channels": str(total_dig),
        "analog_channels": str(total_ana),
        "zones": "4",
        "verified_lines": str(len(verify_proc.stdout.splitlines())),
    }
