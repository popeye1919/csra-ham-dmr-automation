"""Generators for Baofeng UV-5R CHIRP (.csv & .img) and BTECH DMR-6X2 PRO (.conf & .img) codeplugs."""

from __future__ import annotations

import csv
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .scrapers import AnalogChannelSpec, DigitalChannelSpec, TalkgroupSpec


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
    intro_line1: str = "WELCOME",
    intro_line2: str = "D4RKSP2RK",
) -> Dict[str, str]:
    """
    Generate a complete, validated dmrconfig .conf file and compiled 1,606,528-byte .img codeplug
    for the BTECH DMR-6X2 PRO (`D6X2UV2`), combining:
      - Augusta W4DV & CSRA TGIF / Vidalia Supergroup / BrandMeister / SCHEART DMR repeaters
      - W4DV & CSRA Analog VHF/UHF repeaters & simplex nets
      - NOAA Weather (RX-Only), FRS, GMRS, and MURS banks
      - Organized tactical Zones and Receive Group Lists
    """
    out_dir = repo_root / "data" / "generated" / "dmrconfig"
    out_dir.mkdir(parents=True, exist_ok=True)
    conf_path = out_dir / "CSRA_W4DV_DMR6X2PRO.conf"
    img_path = out_dir / "CSRA_W4DV_DMR6X2PRO.img"

    baseline_img = repo_root / "data" / "stable_firmware" / "dmr6x2_pro" / "dmr6x2pro_stable_baseline.img"
    baseline_conf = repo_root / "data" / "stable_firmware" / "dmr6x2_pro" / "dmr6x2pro_stable_baseline.conf"
    private_contacts = _extract_private_contacts_from_baseline(baseline_conf)

    # Map Talkgroups to Contact Table indices:
    # Slots 1..8: Primary CSRA TGIF Talkgroups
    # Slots 9..1000: Preserved Private Contacts from operator's radio
    # Slots 1001+: Extended Georgia TGIF, Vidalia Supergroup, SCHEART PRN, BrandMeister Talkgroups
    contact_entries: List[Tuple[int, str, str, int, str]] = []
    tg_id_to_contact_idx: Dict[int, int] = {}

    primary_tgs = [t for t in talkgroups if t.dmr_id in (31665, 358, 43389, 9050, 985, 8014, 8044, 31000)]
    extended_tgs = [t for t in talkgroups if t.dmr_id not in (31665, 358, 43389, 9050, 985, 8014, 8044, 31000)]

    for i, tg in enumerate(primary_tgs, start=1):
        contact_entries.append((i, tg.name_16[:16], tg.call_type, tg.dmr_id, tg.rx_tone))
        tg_id_to_contact_idx[tg.dmr_id] = i

    for idx, name, ctype, cid, rxtone in private_contacts:
        contact_entries.append((idx, name[:16], ctype, cid, rxtone))
        tg_id_to_contact_idx[cid] = idx

    for i, tg in enumerate(extended_tgs, start=1001):
        contact_entries.append((i, tg.name_16[:16], tg.call_type, tg.dmr_id, tg.rx_tone))
        tg_id_to_contact_idx[tg.dmr_id] = i

    lines: List[str] = [
        "#",
        "# Automated CSRA & Augusta W4DV Codeplug for BTECH DMR-6X2 PRO",
        "# Generated by csra-ham-dmr-automation",
        "#",
        "Radio: BTECH DMR-6X2 PRO",
        "",
        "# Table of digital channels.",
        "Digital Name             Receive   Transmit Power Scan TOT RO Admit  Color Slot RxGL TxContact",
    ]

    # Allocate Digital Channels and track Zone memberships
    zone_csra_dmr: List[int] = []
    zone_vidalia_bm: List[int] = []
    zone_scheart_prn: List[int] = []
    all_digital_chans: List[int] = []

    ch_idx = 1
    for dch in digital_channels:
        tx_contact_idx = tg_id_to_contact_idx.get(dch.tx_contact_id, 1)
        ro_flag = "+" if dch.rx_only else "-"
        rxgl_str = str(dch.rx_grouplist_idx) if dch.rx_grouplist_idx > 0 else "-"
        rx_freq_str = f"{dch.rx_mhz:.4f}".rstrip("0").rstrip(".")
        if "." not in rx_freq_str:
            rx_freq_str += ".0"
        lines.append(
            f"{ch_idx:5d}   {dch.name[:16]:<16s} {rx_freq_str:<9s} {dch.tx_offset_str:<8s} "
            f"{dch.power:<5s} {dch.scanlist:<4s} -   {ro_flag}  {dch.admit:<6s} "
            f"{dch.color_code:<5d} {dch.timeslot:<3d}  {rxgl_str:<4s} {tx_contact_idx:<4d} "
            f"# {dch.tx_contact_name} ({dch.location})"
        )
        all_digital_chans.append(ch_idx)
        if dch.network in ("TGIF", "Simplex"):
            zone_csra_dmr.append(ch_idx)
        elif dch.network in ("Vidalia_SG", "BrandMeister"):
            zone_vidalia_bm.append(ch_idx)
        elif dch.network == "SCHEART_PRN":
            zone_scheart_prn.append(ch_idx)
        ch_idx += 1

    # Analog Channels Table
    lines.extend(
        [
            "",
            "# Table of analog channels.",
            "Analog  Name             Receive   Transmit Power Scan TOT RO Admit  Squelch RxTone TxTone Width",
        ]
    )

    zone_w4dv_analog: List[int] = []
    zone_csra_repeaters: List[int] = []
    zone_simplex: List[int] = []
    zone_out_of_town: List[int] = []
    zone_weather: List[int] = []
    zone_frs_gmrs_murs: List[int] = []

    ch_idx = 60  # Start Analog repeaters cleanly at channel 60
    vhf_uhf_analog = [
        ch for ch in analog_channels if _is_uv5r_supported_band(ch.rx_mhz) and _is_uv5r_supported_band(ch.tx_mhz)
    ]

    for ach in vhf_uhf_analog:
        if ach.duplex == "+":
            tx_str = f"+{ach.offset_mhz:g}"
        elif ach.duplex == "-":
            tx_str = f"-{ach.offset_mhz:g}"
        else:
            tx_str = "+0"

        ro_flag = "+" if ach.rx_only else "-"
        rx_t = f"{ach.rx_tone:.1f}" if ach.rx_tone else "-"
        tx_t = f"{ach.tx_tone:.1f}" if ach.tx_tone else "-"
        bw_str = "12.5" if ach.bandwidth_khz < 20.0 else "25"
        clean_name = ach.name.replace(" ", "_")[:16]

        rx_freq_str = f"{ach.rx_mhz:.4f}".rstrip("0").rstrip(".")
        if "." not in rx_freq_str:
            rx_freq_str += ".0"
        lines.append(
            f"{ch_idx:5d}   {clean_name:<16s} {rx_freq_str:<9s} {tx_str:<8s} "
            f"{ach.power:<5s} 1    -   {ro_flag}  -      Normal  {rx_t:<6s} {tx_t:<6s} {bw_str}"
        )

        if ach.category == "W4DV":
            zone_w4dv_analog.append(ch_idx)
            zone_csra_repeaters.append(ch_idx)
        elif ach.category == "CSRA_RPT":
            zone_csra_repeaters.append(ch_idx)
        elif ach.category == "SIMPLEX":
            zone_simplex.append(ch_idx)
        elif ach.category == "OUT_OF_TOWN":
            zone_out_of_town.append(ch_idx)
        ch_idx += 1

    # Add NOAA Weather Channels (RX-Only '+' flag)
    for _, full_n, freq, _ in NOAA_WEATHER_CHANNELS:
        lines.append(
            f"{ch_idx:5d}   {full_n:<16s} {freq:<9g} +0       High  -    -   +  -      Normal  -      -      25"
        )
        zone_weather.append(ch_idx)
        ch_idx += 1

    # Add MURS Channels
    for _, full_n, freq, bw, pwr in MURS_CHANNELS:
        bw_str = "12.5" if bw < 20.0 else "25"
        lines.append(
            f"{ch_idx:5d}   {full_n:<16s} {freq:<9g} +0       {pwr:<5s} 1    -   -  -      Normal  -      -      {bw_str}"
        )
        zone_frs_gmrs_murs.append(ch_idx)
        ch_idx += 1

    # Add FRS Channels
    for f_num, freq, pwr in FRS_FREQS:
        freq_s = f"{freq:.4f}".rstrip("0").rstrip(".")
        lines.append(
            f"{ch_idx:5d}   FRS_{f_num:02d}           {freq_s:<9s} +0       {pwr:<5s} 1    -   -  -      Normal  -      -      12.5"
        )
        zone_frs_gmrs_murs.append(ch_idx)
        ch_idx += 1

    def _fmt_list(nums: List[int]) -> str:
        return ",".join(str(n) for n in nums) if nums else "-"

    # Zones Table
    lines.extend(
        [
            "",
            "# Table of channel zones.",
            "Zone    Name             Channels",
            f"    1   CSRA_TGIF_DMR    {_fmt_list(zone_csra_dmr)}",
            f"    2   W4DV_Augusta     {_fmt_list(zone_csra_dmr[:12] + zone_w4dv_analog)}",
            f"    3   GA_Vidalia_BM    {_fmt_list(zone_vidalia_bm)}",
            f"    4   SCHEART_PRN_DMR  {_fmt_list(zone_scheart_prn)}",
            f"    5   CSRA_Repeaters   {_fmt_list(zone_csra_repeaters)}",
            f"    6   CSRA_Simplex     {_fmt_list(zone_simplex)}",
            f"    7   Out_Of_Town      {_fmt_list(zone_out_of_town)}",
            f"    8   NOAA_Weather     {_fmt_list(zone_weather)}",
            f"    9   FRS_MURS         {_fmt_list(zone_frs_gmrs_murs)}",
        ]
    )

    # Scanlist Table (Scanlist 1 covering active CSRA DMR & W4DV repeaters, max 50 channels per Anytone scanlist)
    scan_members = (zone_csra_dmr + zone_w4dv_analog + zone_csra_repeaters)[:50]
    lines.extend(
        [
            "",
            "# Table of scan lists.",
            "Scanlist Name            PCh1 PCh2 TxCh Channels",
            f"    1   CSRA_Active_Scan -    -    Sel  {_fmt_list(scan_members)}",
        ]
    )

    # Contacts Table
    lines.extend(
        [
            "",
            "# Table of contacts.",
            "Contact Name             Type    ID       RxTone",
        ]
    )
    for c_idx, c_name, c_type, c_id, c_tone in contact_entries:
        lines.append(f"{c_idx:5d}   {c_name:<16s} {c_type:<7s} {c_id:<8d} {c_tone}")

    # Group Lists Table
    ext_end = 1000 + len(extended_tgs)
    lines.extend(
        [
            "",
            "# Table of group lists.",
            "Grouplist Name                              Contacts",
            "    1   CSRA_TGIF_Cluster                   1-8,1003-1008",
            "    2   Vidalia_GA_Supergroup               1001-1009",
            f"    3   SCHEART_PRN_Cluster                 1009-{min(ext_end, 1016)}",
            f"    4   BrandMeister_Cluster                1001,1003,1006,1017-{ext_end}",
            "",
            "# Table of text messages.",
            "Message Text",
            "    1   Greetings from CSRA / W4DV!",
            "    2   Monitoring TG 358 CSRA Talk.",
            "    3   73 de KR4JLC!",
            "    4   QSY to 146.520 Simplex.",
            "    5   Better than I deserve!",
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

    # Compile into binary .img starting from the stable DMR-6X2 PRO baseline image
    # Note: dmrconfig -c <in.img> <in.conf> writes its output to 'device.img' in cwd
    subprocess.run(
        [str(dmrconfig_bin), "-c", str(baseline_img), str(conf_path)],
        cwd=str(out_dir),
        capture_output=True,
        text=True,
        check=True,
    )
    compiled_device_img = out_dir / "device.img"
    if compiled_device_img.exists():
        shutil.move(str(compiled_device_img), str(img_path))

    # Verify the compiled binary image
    verify_proc = subprocess.run(
        [str(dmrconfig_bin), str(img_path)],
        capture_output=True,
        text=True,
        check=True,
    )

    return {
        "dmr_conf_path": str(conf_path.relative_to(repo_root)),
        "dmr_img_path": str(img_path.relative_to(repo_root)),
        "digital_channels": str(len(digital_channels)),
        "analog_channels": str(len(vhf_uhf_analog) + len(NOAA_WEATHER_CHANNELS) + len(MURS_CHANNELS) + len(FRS_FREQS)),
        "zones": "9",
        "verified_lines": str(len(verify_proc.stdout.splitlines())),
    }
