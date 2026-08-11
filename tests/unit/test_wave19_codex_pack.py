from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def backlog(): return json.loads((ROOT/'codex/CODEX_BACKLOG.json').read_text())

def test_required_codex_documents_exist():
    required=['CODEX_MASTER_PROMPT.md','CODEX_DAY1_PROMPT.md','CODEX_DAY2_PROMPT.md','CODEX_AUTONOMY_RULES.md','CODEX_GIT_POLICY.md','CODEX_GITHUB_POLICY.md','CODEX_AWS_POLICY.md','CODEX_CHECKPOINTS.md','CODEX_RECOVERY.md','CODEX_DEFINITION_OF_DONE.md','CODEX_BACKLOG.json','CODEX_TIME_BUDGET.md','CODEX_TEST_MATRIX.md','CODEX_FEATURE_FREEZE.md','CODEX_LAUNCH_PROMPT.md']
    for name in required:
        p=ROOT/'codex'/name
        assert p.exists() and p.stat().st_size>80, name

def test_backlog_ids_dependencies_and_profiles():
    data=backlog(); tasks=data['tasks']; ids=[t['id'] for t in tasks]
    assert len(ids)==len(set(ids))
    idset=set(ids)
    assert {35,42,48} == {v['hours'] for v in data['profiles'].values()}
    assert data['profiles']['35']['freeze_at_hour']==30
    assert data['profiles']['42']['freeze_at_hour']==36
    assert data['profiles']['48']['freeze_at_hour']==42
    for t in tasks:
        assert set(t['dependencies']) <= idset
        if t['priority']=='P0': assert t['min_profile_hours'] <= 35

def test_backlog_is_acyclic():
    data=backlog(); tm={t['id']:t for t in data['tasks']}; seen=set(); visiting=set()
    def dfs(n):
        assert n not in visiting, n
        if n in seen: return
        visiting.add(n)
        for d in tm[n]['dependencies']: dfs(d)
        visiting.remove(n); seen.add(n)
    for n in tm: dfs(n)

def test_external_actions_have_authorization_gates():
    data=backlog(); tm={t['id']:t for t in data['tasks']}
    assert tm['P2-305']['authorization_gate']=='live_openai'
    assert tm['P2-306']['authorization_gate']=='github_remote'
    assert tm['P2-307']['authorization_gate']=='aws_deploy'
    text=(ROOT/'codex/CODEX_AUTONOMY_RULES.md').read_text().lower()
    for phrase in ['github','aws','openai','employer','contact','authorization']:
        assert phrase in text

def test_validator_passes():
    p=subprocess.run([sys.executable,'scripts/validate_wave19_codex_pack.py'],cwd=ROOT,text=True,capture_output=True)
    assert p.returncode==0, p.stdout+p.stderr

def test_controller_doctor_and_isolated_init(tmp_path):
    # Copy only control files/script into isolated repo-shaped temp tree to avoid touching working runtime.
    (tmp_path/'scripts').mkdir(); (tmp_path/'codex').mkdir(); (tmp_path/'release').mkdir(); (tmp_path/'apps/web').mkdir(parents=True)
    (tmp_path/'scripts/codex_control.py').write_bytes((ROOT/'scripts/codex_control.py').read_bytes())
    (tmp_path/'codex/CODEX_BACKLOG.json').write_bytes((ROOT/'codex/CODEX_BACKLOG.json').read_bytes())
    (tmp_path/'release/WAVE_17_RELEASE_PROOF.json').write_bytes((ROOT/'release/WAVE_17_RELEASE_PROOF.json').read_bytes())
    p=subprocess.run([sys.executable,'scripts/codex_control.py','doctor'],cwd=tmp_path,text=True,capture_output=True)
    assert p.returncode==0
    p=subprocess.run([sys.executable,'scripts/codex_control.py','init','--hours','35'],cwd=tmp_path,text=True,capture_output=True)
    assert p.returncode==0
    state=json.loads((tmp_path/'.codex-runtime/state.json').read_text())
    assert state['freeze_at_hour']==30
    p=subprocess.run([sys.executable,'scripts/codex_control.py','next'],cwd=tmp_path,text=True,capture_output=True)
    assert p.returncode==0 and 'C0-001' in p.stdout
