import json
from pathlib import Path
import pytest
from core.performance_lab import prepare, run, sha256


def test_performance_comparison_real_jobs(qapp, tmp_path):
    root = tmp_path/'performance'
    prepare(root)
    source = tmp_path/'existing.bin'
    source.write_bytes(b'READ ONLY SOURCE\n'*65536)
    before = source.stat().st_mtime_ns, sha256(source)
    plan = json.loads((root/'PLAN.json').read_text(encoding='utf-8'))
    plan['source_file'] = str(source)
    (root/'PLAN.json').write_text(json.dumps(plan), encoding='utf-8')
    run(root)
    result = json.loads((root/'RESULT.json').read_text(encoding='utf-8'))
    assert len(result['runs']) == 3
    assert all(row['verified'] for row in result['runs'])
    assert [row['observed_concurrent_jobs'] for row in result['runs']] == [1, 2, 3]
    assert all(row['peak_rss_mib'] >= row['baseline_rss_mib'] > 0 for row in result['runs'])
    assert len(list(Path(result['output_root']).rglob('existing.bin'))) == 9
    assert (source.stat().st_mtime_ns, sha256(source)) == before


def test_performance_setup_and_invalid_limits_do_not_touch_source(tmp_path):
    root = tmp_path/'performance'
    prepare(root)
    with pytest.raises(FileExistsError):
        prepare(root)
    plan = json.loads((root/'PLAN.json').read_text(encoding='utf-8'))
    plan['concurrency_limits'] = [0]
    (root/'PLAN.json').write_text(json.dumps(plan), encoding='utf-8')
    with pytest.raises(ValueError):
        run(root)
    assert not (root/'Source').exists()


def test_recursive_folder_keeps_same_basename_in_different_subfolders(qapp, tmp_path):
    root = tmp_path/'folder-test'
    prepare(root)
    source = tmp_path/'original-tree'
    for name in ('branch A', 'branch B/deep'):
        directory = source/name
        directory.mkdir(parents=True)
        (directory/'same.dmp').write_bytes(name.encode()*1024)
    plan = json.loads((root/'PLAN.json').read_text(encoding='utf-8'))
    plan.update(source_directory=str(source), job_count=2, concurrency_limits=[2])
    (root/'PLAN.json').write_text(json.dumps(plan), encoding='utf-8')
    run(root)
    result = json.loads((root/'RESULT.json').read_text(encoding='utf-8'))
    assert result['runs'][0]['verified']
    assert result['runs'][0]['files_per_job'] == 2
    base = Path(result['output_root'])/'Run-1-Concurrency-2'
    for job in (1, 2):
        for name in ('branch A', 'branch B/deep'):
            assert (base/f'Job-{job}'/name/'same.dmp').read_bytes() == (source/name/'same.dmp').read_bytes()
