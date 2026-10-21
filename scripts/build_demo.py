"""Build an allowlisted, synthetic-only static demo; no application runtime shipped."""

import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import ImageDraw  # noqa: E402
from mazeproof.core import validate_structure  # noqa: E402
from mazeproof.samples import demo_model, demo_route, render  # noqa: E402


def variant(problem, solution, image):
    result = validate_structure(json.dumps(problem), json.dumps(solution))
    if result['overallStatus'] not in ('PASS', 'FAIL'):
        raise ValueError('Unexpected synthetic validation failure')
    return {
        'problem': problem, 'solution': solution,
        'problemImage': './assets/problem.png', 'solutionImage': image,
        'checks': result['checks'],
    }


def build():
    site = ROOT / '_site'
    if site.is_symlink():
        raise ValueError('Build directory must not be a symlink')
    if site.exists():
        shutil.rmtree(site)
    (site / 'assets').mkdir(parents=True)
    for name in ('index.html', 'style.css', 'app.js', 'icon.svg'):
        source = ROOT / 'demo' / name
        if source.is_symlink():
            raise ValueError('Static source must not be a symlink')
        shutil.copyfile(source, site / name)
    (site / '.nojekyll').touch()
    model = demo_model()
    answer = copy.deepcopy(model)
    answer['route'] = demo_route()
    render(model).save(site / 'assets/problem.png')
    render(model, demo_route()).save(site / 'assets/solution.png')

    # The missing cell models the deliberately erased top-row segment. This is a
    # prescribed explanatory state, never presented as measured image recognition.
    gap = render(model, demo_route())
    ImageDraw.Draw(gap).rectangle((140, 54, 232, 66), fill='white')
    gap.save(site / 'assets/gap.png')
    broken_answer = copy.deepcopy(answer)
    broken_answer['route'].pop(2)
    wall = copy.deepcopy(model)
    wall['verticalWalls'][0][2] = True
    wall_answer = copy.deepcopy(answer)
    wall_answer['verticalWalls'][0][2] = True
    good = variant(model, answer, './assets/solution.png')
    wrong = variant(wall, wall_answer, './assets/solution.png')
    broken = variant(model, broken_answer, './assets/gap.png')
    expected = {
        'good': ['PASS', 'PASS', 'PASS', 'PASS'],
        'wrong': ['FAIL', 'FAIL', 'FAIL', 'PASS'],
        'broken': ['PASS', 'PASS', 'FAIL', 'PASS'],
    }
    names = ('reachability', 'uniqueness', 'routeValidity', 'mazeIdentity')
    for name, value in (('good', good), ('wrong', wrong), ('broken', broken)):
        actual = [value['checks'][check]['status'] for check in names]
        if actual != expected[name]:
            raise ValueError(f'{name}: expected {expected[name]}, got {actual}')
    samples = {
        'normal': {'focus': [60, 24], 'before': good, 'after': good},
        'wall': {'focus': [168, 60], 'before': wrong, 'after': good},
        'gap': {'focus': [186, 60], 'before': broken, 'after': good},
    }
    (site / 'samples.js').write_text('export const samples = ' + json.dumps(samples, ensure_ascii=False, sort_keys=True) + ';\n', encoding='utf-8')
    provenance = {
        'notice': 'Original MIT synthetic samples. Fixed instructional states, not image-recognition measurements or human approvals.',
        'coreVersion': '0.2.1', 'checks': expected,
        'modelHashes': {key: hashlib.sha256(json.dumps(value['before']['problem'], sort_keys=True).encode()).hexdigest() for key, value in samples.items()},
    }
    (site / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    files = sorted(str(path.relative_to(site)) for path in site.rglob('*') if path.is_file())
    expected_files = ['.nojekyll', 'app.js', 'assets/gap.png', 'assets/problem.png', 'assets/solution.png', 'icon.svg', 'index.html', 'provenance.json', 'samples.js', 'style.css']
    if files != sorted(expected_files):
        raise ValueError('Unexpected publish artifact contents')
    print(json.dumps({'files': files, 'syntheticChecks': expected}, ensure_ascii=False))


if __name__ == '__main__':
    build()
