"""Automated test suite for the CSRA HAM & DMR Radio Automation Suite."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from csra_radio.cli import _record_pre_flash_backup_manifest, decode_morse, encode_morse
from csra_radio.detector import (
    inspect_btech_image_header,
    inspect_uv5r_image_metadata,
)
from csra_radio.scrapers import parse_ics217_and_build_catalog


REPO_ROOT = Path(__file__).resolve().parents[1]
BTECH_EXPECTED_IMAGE_SIZE = 1606528
UV5R_EXPECTED_IMAGE_SIZE = 6645


def test_btech_stable_baseline_integrity() -> None:
    """Verify the stabilized BTECH DMR-6X2 PRO image header and manifest."""
    img_path = REPO_ROOT / "data" / "stable_firmware" / "dmr6x2_pro" / "dmr6x2pro_stable_baseline.img"
    manifest_path = REPO_ROOT / "data" / "stable_firmware" / "dmr6x2_pro" / "stable_manifest.json"
    assert img_path.exists()
    assert manifest_path.exists()
    assert img_path.stat().st_size == BTECH_EXPECTED_IMAGE_SIZE

    meta = inspect_btech_image_header(img_path)
    assert meta["hardware_ident"] == "D6X2UV2"
    assert meta["firmware_version"] == "24040800D0060110"
    assert meta["build_date"] == "2024-4-12"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["callsign"] == "KR4JLC"
    assert manifest["dmr_id"] == 3221824
    assert manifest["image_size_bytes"] == BTECH_EXPECTED_IMAGE_SIZE
    assert len(manifest["image_sha256"]) == 64


def test_uv5r_stable_baseline_integrity() -> None:
    """Verify the stabilized Baofeng UV-5R CHIRP image and metadata."""
    img_path = REPO_ROOT / "data" / "stable_firmware" / "uv5r" / "uv5r_stable_baseline.img"
    manifest_path = REPO_ROOT / "data" / "stable_firmware" / "uv5r" / "stable_manifest.json"
    assert img_path.exists()
    assert manifest_path.exists()
    assert img_path.stat().st_size == UV5R_EXPECTED_IMAGE_SIZE

    meta = inspect_uv5r_image_metadata(img_path)
    assert meta["hardware_ident"] == "Baofeng_UV-5R"
    assert meta["firmware_version"] == "HN5RV011"
    assert meta["build_date"] == "180618N"


def test_catalog_contains_w4dv_and_csra_dmr_systems() -> None:
    """Verify W4DV analog repeaters, CSRA DMR repeaters, and GA TGIF talkgroups."""
    analog_channels, digital_channels, talkgroups = parse_ics217_and_build_catalog(REPO_ROOT)

    analog_freqs = {round(ch.rx_mhz, 4) for ch in analog_channels}
    # All 6 core W4DV repeaters + Fort Gordon + 2m Calling
    for expected_freq in (145.110, 145.290, 145.390, 145.490, 147.180, 444.950, 145.410, 146.520):
        assert expected_freq in analog_freqs, f"Missing expected analog frequency {expected_freq}"

    dmr_freqs_cc = {(round(ch.rx_mhz, 4), ch.color_code) for ch in digital_channels}
    # W4DV DMR (442.550 CC1), KK4CNM (147.195 CC1), K4KNS Belair (444.900 CC15), K4KNS Wrens (444.175 CC1), N2ZZ (443.4625 CC1)
    assert (442.550, 1) in dmr_freqs_cc
    assert (147.195, 1) in dmr_freqs_cc
    assert (444.900, 15) in dmr_freqs_cc
    assert (444.175, 1) in dmr_freqs_cc
    assert (443.4625, 1) in dmr_freqs_cc

    tg_ids = {tg.dmr_id for tg in talkgroups}
    for expected_tg in (358, 985, 3113, 31130, 31665, 43389, 3145, 9990):
        assert expected_tg in tg_ids, f"Missing expected Talkgroup {expected_tg}"


def test_generated_codeplug_binaries_verify_cleanly() -> None:
    """Verify compiled CHIRP and dmrconfig codeplug images pass binary verification."""
    uv5r_img = REPO_ROOT / "data" / "generated" / "chirp" / "CSRA_W4DV_UV5R.img"
    btech_img = REPO_ROOT / "data" / "generated" / "dmrconfig" / "CSRA_W4DV_DMR6X2PRO.img"
    dmrconfig_bin = REPO_ROOT / "bin" / "dmrconfig"

    assert uv5r_img.exists()
    assert uv5r_img.stat().st_size == UV5R_EXPECTED_IMAGE_SIZE

    assert btech_img.exists()
    assert btech_img.stat().st_size == BTECH_EXPECTED_IMAGE_SIZE

    res = subprocess.run(
        [str(dmrconfig_bin), str(btech_img)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert "Radio: BTECH DMR-6X2 PRO" in res.stdout
    assert "3221824" in res.stdout
    assert "KR4JLC" in res.stdout


def test_morse_phreak_codec() -> None:
    """Verify ITU Morse Code encoder/decoder for CW & 90s phreak telemetry."""
    msg = "CQ DE KR4JLC 73"
    cw = encode_morse(msg)
    assert cw == "-.-. --.- / -.. . / -.- .-. ....- .--- .-.. -.-. / --... ...--"
    assert decode_morse(cw) == msg


def test_mandatory_pre_flash_backup_guard_and_windows_suite() -> None:
    """Verify mandatory pre-flash backup verification and Windows PowerShell/CHIRP suite."""
    import tempfile

    # 1. Verify Windows directory artifacts exist and contain mandatory backup & CHIRP Wiki references
    ps1_path = REPO_ROOT / "windows" / "Invoke-CsraChirp.ps1"
    bat_path = REPO_ROOT / "windows" / "Run-CsraChirp.bat"
    win_readme = REPO_ROOT / "windows" / "README.md"
    assert ps1_path.exists()
    assert bat_path.exists()
    assert win_readme.exists()

    ps1_text = ps1_path.read_text(encoding="utf-8")
    assert "Invoke-MandatoryPreFlashBackup" in ps1_text
    assert "--download-mmap" in ps1_text
    assert "https://chirpmyradio.com/projects/chirp/wiki/Home" in ps1_text

    win_readme_text = win_readme.read_text(encoding="utf-8")
    assert "https://chirpmyradio.com/projects/chirp/wiki/Home" in win_readme_text
    assert "Radio -> Download from radio" in win_readme_text

    # 2. Verify _record_pre_flash_backup_manifest rejects missing or 0-byte backups
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        empty_img = tmp_path / "empty.img"
        empty_img.write_bytes(b"")
        try:
            _record_pre_flash_backup_manifest(empty_img, "Baofeng_UV-5R", "COM4")
            raise AssertionError("Expected RuntimeError for 0-byte pre-flash backup!")
        except RuntimeError:
            pass

        valid_img = tmp_path / "valid_pre_flash.img"
        valid_img.write_bytes(b"CHIRP_EEPROM_BACKUP" * 350)
        manifest_path = _record_pre_flash_backup_manifest(valid_img, "Baofeng_UV-5R", "COM4")
        assert manifest_path.exists()
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest_data["size_bytes"] == valid_img.stat().st_size
        assert len(manifest_data["sha256"]) == 64


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(REPO_ROOT / "src"))
    for fn in (
        test_btech_stable_baseline_integrity,
        test_uv5r_stable_baseline_integrity,
        test_catalog_contains_w4dv_and_csra_dmr_systems,
        test_generated_codeplug_binaries_verify_cleanly,
        test_morse_phreak_codec,
        test_mandatory_pre_flash_backup_guard_and_windows_suite,
    ):
        fn()
        print(f"[PASS] {fn.__name__}")
    print("All 6 test suites passed!")
