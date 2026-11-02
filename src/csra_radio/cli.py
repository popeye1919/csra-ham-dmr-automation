"""
Command-line interface for CSRA HAM & DMR Radio Automation.
.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.
  [ 2600 Hz TONE LOCKED ] // [ THE KNIGHTS WHO SAY '73' (--... ...--) ]
  CQ CQ CQ DE KR4JLC (-.- .-. ....- .--- .-.. -.-.) // DMR ID: 3221824
.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.=~=.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict

from .detector import (
    extract_and_stabilize_btech,
    extract_and_stabilize_uv5r,
    scan_connected_radios,
)
from .generators import (
    generate_btech_dmr6x2pro_artifacts,
    generate_uv5r_chirp_artifacts,
)
from .scrapers import parse_ics217_and_build_catalog, sync_remote_sources


# ITU-R M.1677-1 International Morse Code Table (Because real phreaks speak CW at 30 WPM)
ITU_MORSE_TABLE: Dict[str, str] = {
    "A": ".-",    "B": "-...",  "C": "-.-.",  "D": "-..",   "E": ".",
    "F": "..-.",  "G": "--.",   "H": "....",  "I": "..",    "J": ".---",
    "K": "-.-",   "L": ".-..",  "M": "--",    "N": "-.",    "O": "---",
    "P": ".--.",  "Q": "--.-",  "R": ".-.",   "S": "...",   "T": "-",
    "U": "..-",   "V": "...-",  "W": ".--",   "X": "-..-",  "Y": "-.--",
    "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    "/": "-..-.", "?": "..--..", "=": "-...-", "+": ".-.-.", "-": "-....-",
    ".": ".-.-.-", ",": "--..--", "@": ".--.-.",
}
REVERSE_MORSE_TABLE: Dict[str, str] = {v: k for k, v in ITU_MORSE_TABLE.items()}

PHREAK_BANNER = r"""
 ._________________________________________________________________________.
 |  ____ ____ ____    _      ____  _   _ ____  _____    _    _  __         |
 | / ___/ ___|  _ \  / \    |  _ \| | | |  _ \| ____|  / \  | |/ /         |
 || |   \___ \ |_) |/ _ \   | |_) | |_| | |_) |  _|   / _ \ | ' /   [2600] |
 || |___ ___) |  _ < ___ \  |  __/|  _  |  _ <| |___ / ___ \| . \   [ Hz ] |
 | \____|____/|_| \_\_/ \_\ |_|   |_| |_|_| \_\_____/_/   \_\_|\_\         |
 |-------------------------------------------------------------------------|
 |  * HACK THE PLANET (AND THE REPEATER INPUT OFFSET) *                    |
 |  * THE KNIGHTS WHO SAY "--... ...--" (73) // DE KR4JLC [ID: 3221824] *  |
 |  * CW: -.-. --.-  -.. .  -.- .-. ....- .--- .-.. -.-.  -...-  -.-      |
 |  * "What... is the airspeed velocity of an unladen RF carrier?"         |
 |    "What do you mean? An African or an ITU Region 2 carrier?"           |
 `-------------------------------------------------------------------------'
"""


def encode_morse(text: str) -> str:
    """Encode ASCII text into ITU Morse Code (`/` separates words)."""
    words = []
    for word in text.upper().split():
        letters = [ITU_MORSE_TABLE.get(ch, "?") for ch in word]
        words.append(" ".join(letters))
    return " / ".join(words)


def decode_morse(cw: str) -> str:
    """Decode ITU Morse Code (`/` separates words) back into ASCII text."""
    words = []
    for raw_word in cw.strip().split("/"):
        chars = [REVERSE_MORSE_TABLE.get(tok, "?") for tok in raw_word.strip().split() if tok]
        words.append("".join(chars))
    return " ".join(words)


def get_repo_root() -> Path:
    """Resolve repository root directory."""
    return Path(__file__).resolve().parents[2]


def print_banner(quiet: bool = False) -> None:
    """Print the 90s Phreak / Morse / Monty Python BBS header."""
    if not quiet:
        print(PHREAK_BANNER.strip("\n"))


def cmd_detect(args: argparse.Namespace) -> int:
    """Detect connected USB/serial radios and print status."""
    print("[*] Blowing 2600 Hz Cap'n Crunch whistle down /sys/bus/usb/devices ...")
    print(f"    CW BEACON: {encode_morse('QRL? DE KR4JLC')}")
    devices = scan_connected_radios()
    if not devices:
        print("[*] 'Tis but a flesh wound! No live USB/Serial Beige-Box cables currently on the bus.")
        print("    (Your radios are not dead yet! They're just pining for the fjords of /dev/ttyACM0.)")
        print("    - BTECH DMR-6X2 PRO expected VID:PID -> 28e9:018a (GD32 Virtual COM Blue-Box)")
        print("    - Baofeng UV-5R expected VID:PID     -> 1a86:7523 (CH340) / 0403:6001 (FTDI) / 10c4:ea60 (CP210x)")
        return 0

    print(f"[+] NI! Detected {len(devices)} live phreaking interface(s) on the trunk:")
    for d in devices:
        print(f"    - {d.model} [{d.vid}:{d.pid}] tty={d.tty_port or 'N/A'} bus={d.usb_bus_dev}")
    return 0


def cmd_extract_stable(args: argparse.Namespace) -> int:
    """Extract and lock both BTECH DMR-6X2 PRO and Baofeng UV-5R into a stable verified baseline."""
    root = get_repo_root()
    dmrconfig_bin = root / "bin" / "dmrconfig"

    print("[*] Consulting the Book of Armaments, Chapter 2, Verses 9-21...")
    print("    'First shalt thou send the ASCII string PROGRAM, then shalt thou wait for QX\\x06...'")
    print("[*] Extracting & stabilizing BTECH DMR-6X2 PRO (D6X2UV2) firmware/codeplug baseline...")
    btech_manifest = extract_and_stabilize_btech(root, dmrconfig_bin)
    print(json.dumps(asdict(btech_manifest), indent=2))

    print("\n[*] Dumping & stabilizing Baofeng UV-5R (HN5RV011) EEPROM baseline (no shrubbery required)...")
    uv5r_manifest = extract_and_stabilize_uv5r(root)
    print(json.dumps(asdict(uv5r_manifest), indent=2))
    print(f"[+] Baseline locked! CW Checksum ACK: {encode_morse('R R TU 73')}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    """Sync latest repeaters and talkgroups from Augusta Ham Radio (W4DV), ICS-217, and TGIF Georgia API."""
    root = get_repo_root()
    print("[*] Dialing Ma Bell's CSRA Toll Trunk (W4DV + Google Drive ICS-217 + TGIF Georgia API)...")
    print("    'Nobody expects the FCC Part 97 Band Plan Inquisition!'")
    status = sync_remote_sources(root, tgif_api_token=args.tgif_token, dmr_id=args.dmr_id)
    print(json.dumps(status, indent=2))
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    """Compile CHIRP (.csv + .img) for Baofeng UV-5R and dmrconfig (.conf + .img) for BTECH DMR-6X2 PRO."""
    root = get_repo_root()
    dmrconfig_bin = root / "bin" / "dmrconfig"

    print("[*] Synthesizing Red-Box / Blue-Box Codeplug Matrices for Augusta & CSRA...")
    analog_ch, digital_ch, talkgroups = parse_ics217_and_build_catalog(root)
    print(
        f"[*] Parsed CSRA Catalog: {len(analog_ch)} Analog Repeaters/Simplex, "
        f"{len(digital_ch)} Digital DMR Channels, {len(talkgroups)} Talkgroups."
    )

    chirp_res = generate_uv5r_chirp_artifacts(root, analog_ch, compile_img=True)
    print("[+] Generated Baofeng UV-5R CHIRP Artifacts (She weighs the same as a duck!):")
    print(json.dumps(chirp_res, indent=2))

    btech_res = generate_btech_dmr6x2pro_artifacts(
        root,
        dmrconfig_bin,
        analog_ch,
        digital_ch,
        talkgroups,
        dmr_id=args.dmr_id,
        callsign=args.callsign,
        intro_line1=args.intro1,
        intro_line2=args.intro2,
    )
    print("\n[+] Generated BTECH DMR-6X2 PRO Codeplug Artifacts (Holy Hand Grenade of Antioch Edition):")
    print(json.dumps(btech_res, indent=2))
    print(f"\n[*] QSL? {encode_morse(f'DE {args.callsign} 73 SK')}")
    return 0


def _record_pre_flash_backup_manifest(backup_img: Path, radio_type: str, source_port: str) -> Path:
    """Verify non-empty pre-flash backup image and write a SHA-256 rollback manifest."""
    if not backup_img.exists() or backup_img.stat().st_size == 0:
        raise RuntimeError(
            f"[ABORT] Pre-flash backup failed or produced a 0-byte file: {backup_img}. "
            "Refusing to flash without a verified rollback image!"
        )
    digest = hashlib.sha256(backup_img.read_bytes()).hexdigest()
    manifest_path = backup_img.with_suffix(".manifest.json")
    manifest = {
        "radio_type": radio_type,
        "source_port": source_port,
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "backup_file": str(backup_img),
        "size_bytes": backup_img.stat().st_size,
        "sha256": digest,
        "cw_ack": encode_morse("QSL BACKUP OK 73"),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def cmd_flash(args: argparse.Namespace) -> int:
    """
    Flash compiled codeplugs to connected BTECH DMR-6X2 PRO and/or Baofeng UV-5R.
    ALWAYS downloads and verifies a timestamped pre-flash backup image first!
    """
    root = get_repo_root()
    dmrconfig_bin = root / "bin" / "dmrconfig"
    backup_dir = root / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    devices = scan_connected_radios()

    if args.radio in ("btech", "all"):
        btech_devs = [d for d in devices if d.family == "anytone_btech_dmr"]
        img_path = root / "data" / "generated" / "dmrconfig" / "CSRA_W4DV_DMR6X2PRO.img"
        if not btech_devs:
            print(f"[!] BTECH DMR-6X2 PRO not detected on USB. Ready-to-flash image awaits at: {img_path}")
            print("    [MANDATORY SAFETY RULE] Always pull a backup FIRST before writing when plugged in:")
            print(f"      1. {dmrconfig_bin} -r && mv device.img {backup_dir}/btech_pre_flash_{ts}.img")
            print(f"      2. {dmrconfig_bin} -w {img_path}")
        else:
            pre_backup = backup_dir / f"btech_pre_flash_{ts}.img"
            print(f"[*] [STEP 1/2: MANDATORY PRE-FLASH BACKUP] Pulling current image from {btech_devs[0].model}...")
            subprocess.run([str(dmrconfig_bin), "-r"], cwd=str(backup_dir), check=True)
            pulled_img = backup_dir / "device.img"
            if pulled_img.exists():
                shutil.move(str(pulled_img), str(pre_backup))
            manifest_path = _record_pre_flash_backup_manifest(
                pre_backup, "BTECH_DMR-6X2_PRO", btech_devs[0].tty_port or "usb:28e9:018a"
            )
            print(f"[+] Pre-flash backup locked & SHA-256 verified: {pre_backup} ({manifest_path.name})")

            print("[*] Waiting for BTECH DMR-6X2 PRO to complete post-read reboot cycle...")
            for _ in range(25):
                time.sleep(1.0)
                if any(d.family == "anytone_btech_dmr" for d in scan_connected_radios()):
                    time.sleep(2.0)
                    break

            print(f"[*] [STEP 2/2: FLASH] Counting to Three (not Four, nor Two) and flashing {img_path}...")
            subprocess.run([str(dmrconfig_bin), "-w", str(img_path)], check=True)
            print("[+] BTECH DMR-6X2 PRO flash complete! Rejoice!")

    if args.radio in ("uv5r", "all"):
        uv5r_devs = [d for d in devices if d.family == "kplug_serial"]
        img_path = root / "data" / "generated" / "chirp" / "CSRA_W4DV_UV5R.img"
        if not uv5r_devs or not uv5r_devs[0].tty_port:
            print(f"[!] Baofeng UV-5R K-plug cable not detected on USB. Ready-to-flash image awaits at: {img_path}")
            print("    [MANDATORY SAFETY RULE] Always download a backup FIRST before uploading when plugged in:")
            print(f"      1. chirpc -r Baofeng_UV-5R -s {args.port} --mmap {backup_dir}/uv5r_pre_flash_{ts}.img --download-mmap")
            print(f"      2. chirpc -r Baofeng_UV-5R -s {args.port} --mmap {img_path} --upload-mmap")
        else:
            port = uv5r_devs[0].tty_port
            pre_backup = backup_dir / f"uv5r_pre_flash_{ts}.img"
            env = os.environ.copy()
            env["HOME"] = "/tmp"
            print(f"[*] [STEP 1/2: MANDATORY PRE-FLASH BACKUP] Downloading current EEPROM from UV-5R on {port}...")
            # Note: chirpc upstream has an unconditional sys.exit(1) on --download-mmap and --upload-mmap
            # even when successful, so we verify actual file creation / output instead of returncode.
            proc_down = subprocess.run(
                ["chirpc", "-r", "Baofeng_UV-5R", "-s", port, "--mmap", str(pre_backup), "--download-mmap"],
                env=env,
                capture_output=True,
                text=True,
            )
            if not pre_backup.exists() or pre_backup.stat().st_size == 0:
                print(proc_down.stdout)
                print(proc_down.stderr)
                raise RuntimeError(f"Failed to download pre-flash backup from UV-5R on {port}")
            manifest_path = _record_pre_flash_backup_manifest(pre_backup, "Baofeng_UV-5R", port)
            print(f"[+] Pre-flash backup locked & SHA-256 verified: {pre_backup} ({manifest_path.name})")

            # Allow UV-5R microcontroller to complete post-read EEPROM reboot cycle before sending ident magic again
            print("[*] Waiting 3 seconds for UV-5R MCU post-read reboot cycle to settle...")
            time.sleep(3.0)

            print(f"[*] [STEP 2/2: FLASH] Injecting 6,645 bytes of pure 90s phreak magic ({img_path}) into UV-5R on {port}...")
            proc_up = subprocess.run(
                ["chirpc", "-r", "Baofeng_UV-5R", "-s", port, "--mmap", str(img_path), "--upload-mmap"],
                env=env,
                capture_output=True,
                text=True,
            )
            combined_out = (proc_up.stdout or "") + (proc_up.stderr or "")
            if "Upload successful" not in combined_out and "100.0%" not in combined_out and proc_up.returncode != 0:
                print(proc_up.stdout)
                print(proc_up.stderr)
                raise RuntimeError(f"Failed to flash CSRA image to UV-5R on {port}")
            print("[+] Baofeng UV-5R flash complete! Bring out your HTs!")

    return 0


def cmd_morse(args: argparse.Namespace) -> int:
    """Encode or decode ITU Morse Code (`-.-. --.-`) for phreaks & CW operators."""
    if args.decode:
        decoded = decode_morse(args.message)
        print(f"[CW -> ASCII] {decoded}")
    else:
        encoded = encode_morse(args.message)
        print(f"[ASCII -> CW] {encoded}")
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    """Run full pipeline: detect -> extract-stable -> sync -> build."""
    cmd_detect(args)
    print("-" * 73)
    cmd_extract_stable(args)
    print("-" * 73)
    cmd_sync(args)
    print("-" * 73)
    cmd_build(args)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="csra-radio",
        description=(
            "CSRA Phreak & Packet Underground: Automated CHIRP & DMR Codeplug Pipeline "
            "for Augusta (W4DV), CSRA DMR (TGIF/BM), BTECH DMR-6X2 PRO & Baofeng UV-5R."
        ),
        epilog=(
            "CW: -.-. --.-  -.. .  -.- .-. ....- .--- .-.. -.-.  --... ...--  |  "
            "'We are the Knights Who Say 73! Bring us a shrubbery (or a 2600 Hz CTCSS tone)!'"
        ),
    )
    parser.add_argument("--dmr-id", type=int, default=3221824, help="Operator DMR Radio ID (default: 3221824)")
    parser.add_argument("--callsign", type=str, default="KR4JLC", help="Operator Callsign (default: KR4JLC)")
    parser.add_argument("--intro1", type=str, default="D4rkSp2rk", help="Power-on Intro Line 1")
    parser.add_argument("--intro2", type=str, default="-", help="Power-on Intro Line 2")
    parser.add_argument("--tgif-token", type=str, default=None, help="Optional TGIF Static Talkgroup API Bearer Token")
    parser.add_argument("--no-banner", action="store_true", help="Suppress the 90s Phreak / Monty Python BBS banner")

    sub = parser.add_subparsers(dest="subcommand", required=True)
    sub.add_parser("detect", help="Blue-box probe USB bus for BTECH DMR-6X2 PRO & Baofeng UV-5R interfaces")
    sub.add_parser("extract-stable", help="Extract & cryptographically lock firmware/codeplugs into a stable baseline")
    sub.add_parser("sync", help="Scrape Augusta W4DV repeaters, ICS-217, and CSRA/Georgia TGIF talkgroups")
    sub.add_parser("build", help="Compile CHIRP (.csv/.img) and DMR (.conf/.img) codeplugs for both radios")

    p_flash = sub.add_parser("flash", help="Flash compiled images to connected BTECH DMR-6X2 PRO or Baofeng UV-5R")
    p_flash.add_argument("--radio", choices=["btech", "uv5r", "all"], default="all")
    p_flash.add_argument("--port", type=str, default="/dev/ttyUSB0", help="Serial port override for UV-5R")
    p_flash.add_argument("--yes", action="store_true", help="Confirm flashing without interactive prompt")

    p_morse = sub.add_parser("morse", help="Encode ASCII to ITU Morse Code (-.-. --.-) or decode with --decode")
    p_morse.add_argument("message", type=str, help="Message to encode or decode")
    p_morse.add_argument("--decode", action="store_true", help="Decode Morse string ('/' between words) to ASCII")

    sub.add_parser("all", help="Execute full pipeline: detect -> extract-stable -> sync -> build")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.subcommand != "morse":
        print_banner(quiet=args.no_banner)
    dispatch = {
        "detect": cmd_detect,
        "extract-stable": cmd_extract_stable,
        "sync": cmd_sync,
        "build": cmd_build,
        "flash": cmd_flash,
        "morse": cmd_morse,
        "all": cmd_all,
    }
    return dispatch[args.subcommand](args)


if __name__ == "__main__":
    sys.exit(main())
