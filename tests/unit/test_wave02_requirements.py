from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / 'project' / 'requirements.yaml'


def load_catalog():
    return yaml.safe_load(CATALOG.read_text(encoding='utf-8'))


def test_requirement_catalog_is_unique_and_well_formed():
    data = load_catalog()
    reqs = data['requirements']
    ids = [r['id'] for r in reqs]
    assert len(reqs) >= 120
    assert len(ids) == len(set(ids))
    assert {r['priority'] for r in reqs} == {'P0','P1','P2'}
    assert all(r['verification'] and r['owner_wave'] for r in reqs)


def test_all_six_employer_questions_drive_requirements():
    reqs = load_catalog()['requirements']
    drivers = {d for r in reqs for d in r['drivers']}
    assert {f'EMP-Q{i}' for i in range(1,7)} <= drivers


def test_traceability_matrix_maps_all_six_questions():
    text = (ROOT / 'docs' / 'TRACEABILITY_MATRIX.md').read_text(encoding='utf-8')
    for i in range(1,7):
        assert f'**Q{i}:' in text
    for token in ['Source/data','System features','Employer UI','Requirement IDs','Planned tests','Acceptance','Deliverables']:
        assert token in text


def test_no_legacy_illustrative_stafford_score_is_requirement():
    text = (ROOT / 'docs' / 'REQUIREMENTS.md').read_text(encoding='utf-8')
    # Historical design discussions used illustrative values; acceptance must not require them.
    forbidden = [r'Stafford\s*=\s*91', r'Fit:\s*91', r'Data Confidence\s*64']
    assert not any(re.search(p, text, flags=re.I) for p in forbidden)
    assert 'No fixed Stafford outcome' in text


def test_wave2_required_documents_exist_and_nonempty():
    paths = [
        'docs/REQUIREMENTS.md','docs/TRACEABILITY_MATRIX.md','docs/PRIORITY_MATRIX.md',
        'docs/ACCEPTANCE_CRITERIA.md','docs/SUCCESS_CRITERIA.md','docs/NON_GOALS.md',
        'docs/SECURITY_AND_PRIVACY.md','docs/USABILITY_AND_EMPLOYER_EXPERIENCE.md',
        'docs/EMPLOYER_WOW_NARRATIVE.md','docs/REQUIREMENTS_CHANGE_CONTROL.md',
        'project/requirements.yaml','project/WAVE_02_REPORT.md'
    ]
    for rel in paths:
        p=ROOT/rel
        assert p.exists(), rel
        assert p.stat().st_size > 300, rel


def test_machine_readable_traceability_covers_six_questions():
    data = yaml.safe_load((ROOT / 'project' / 'traceability.yaml').read_text(encoding='utf-8'))
    assert set(data['employer_questions']) == {f'Q{i}' for i in range(1, 7)}
    catalog_ids = {r['id'] for r in load_catalog()['requirements']}
    for item in data['employer_questions'].values():
        assert item['source_inputs']
        assert item['capabilities']
        assert item['ui']
        assert item['acceptance']
        assert item['planned_tests']
        assert item['requirement_refs']
        assert set(item['requirement_refs']) <= catalog_ids
