from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

from scripts.release_claims import load_current_claim_entries, validate_current_claims

ROOT=Path(__file__).resolve().parents[2]

def test_wave20_required_terminal_artifacts_exist():
    required=[
        "release/FINAL_READINESS_REPORT.md",
        "release/FINAL_GAP_REPORT.md",
        "release/CLEAN_ROOM_VERIFICATION.md",
        "release/FINAL_HANDOFF.md",
        "release/WAVE_20_FINAL_RELEASE_MANIFEST.json",
        "research/WAVE_20_FINAL_CONTROL.json",
        "project/WAVE_20_REPORT.md",
        "project/WAVE_20_REQUIREMENT_COVERAGE.md",
        "project/WAVE_20_SOURCE_CONTINUITY.md",
        "docs/WAVE_20_FINAL_INTEGRATION_AND_HANDOFF.md",
    ]
    for rel in required:
        p=ROOT/rel
        assert p.exists() and p.stat().st_size>80, rel

def test_wave20_preserves_current_release_candidate_state():
    control=json.loads((ROOT/"research/WAVE_20_FINAL_CONTROL.json").read_text())
    proof=json.loads((ROOT/"release/WAVE_17_RELEASE_PROOF.json").read_text())
    assert proof["release_exit_gate"]=="PASS"
    assert control["application_release_status"]=="RELEASE_CANDIDATE"
    assert control["sequential_last_completed_wave"]==20
    assert control["active_prerequisite_issue"]=="OGCI-TASK-035"
    assert control["wave18_status"]=="VERIFIED_RELEASE_CANDIDATE"
    assert control["no_wave_21"] is True

def test_current_handoff_claims_match_the_release_candidate():
    assert validate_current_claims(load_current_claim_entries(ROOT)) == []

def test_current_handoff_claims_reject_resolved_environment_blockers():
    entries=load_current_claim_entries(ROOT)
    name="operator/WAVE_20_REQUIREMENT_COVERAGE.md"
    entries[name]+=b"\n| Container build/run proof | **BLOCKED: Docker unavailable** | stale |\n"
    errors=validate_current_claims(entries)
    assert any("stale current claim" in error and "BLOCKED: Docker" in error for error in errors)

def test_wave20_truth_snapshot_is_stable():
    t=json.loads((ROOT/"research/WAVE_20_FINAL_CONTROL.json").read_text())["commercial_truth"]
    assert t["stafford_project_id"]=="1007341663"
    assert t["commercial_fit"]==80.0
    assert t["data_confidence"]==69.25
    assert t["no_value_counterfactual"]==75.0
    assert t["ee_reed_counts"]=={"planning":6,"post_bid":87,"bidding_role":74}
    assert t["rental_authority"]=="UNKNOWN"
    assert t["lead_ready"] is True
    assert t["deal_ready"] is False
    assert t["primary_kpi_demo_value"]=="N/A"

def test_wave20_verifier_passes_for_current_snapshot():
    p=subprocess.run([sys.executable,"scripts/verify_wave20_final.py"],cwd=ROOT,text=True,capture_output=True,check=False)
    assert p.returncode==0, p.stdout+p.stderr

def test_final_handoff_builder_is_privacy_safe(tmp_path):
    out=tmp_path/"handoff.zip"
    p=subprocess.run([sys.executable,"scripts/build_final_handoff_pack.py","--output",str(out)],cwd=ROOT,text=True,capture_output=True,check=False)
    assert p.returncode==0, p.stdout+p.stderr
    assert out.exists()
    with zipfile.ZipFile(out) as z:
        names={n for n in z.namelist() if not n.endswith("/")}
        assert "FINAL_HANDOFF_MANIFEST.json" in names
        assert "FINAL_HANDOFF_CHECKSUMS.sha256" in names
        assert "employer/Kevin_Garrett_Off_Grid_Task.pdf" in names
        assert not any("EE-Reed-Construction-Houston-HQ" in n for n in names)
        assert not any("Stafford-Technology-Campus-Phases-3-4" in n for n in names)
        manifest=json.loads(z.read("FINAL_HANDOFF_MANIFEST.json"))
        assert manifest["application_release_status"]=="RELEASE_CANDIDATE"
        assert manifest["active_prerequisite_issue"]=="OGCI-TASK-035"

def test_wave_pack_builder_supports_blocked_active_wave_override():
    text=(ROOT/"scripts/build_wave_packs.py").read_text()
    assert "--active-wave" in text
    assert "active_wave_override" in text
