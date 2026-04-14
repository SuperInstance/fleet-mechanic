import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from dockside_scorer import DocksideScorer

def test_perfect_repo():
    with tempfile.TemporaryDirectory() as td:
        for f in ['README.md', 'LICENSE', '.gitignore', 'CHANGELOG.md', 'CHARTER.md', 'ABSTRACTION.md', 'STATE.md', 'Dockerfile']:
            open(os.path.join(td, f), 'w').close()
        os.makedirs(os.path.join(td, 'tests'))
        os.makedirs(os.path.join(td, '.github', 'workflows'))
        os.makedirs(os.path.join(td, 'DIARY'))
        s = DocksideScorer()
        total, mx, pct, grade, _ = s.score_local(td)
        assert total == mx, f"Expected {mx}, got {total}"
        assert grade == '🟢'
        print(f"✅ Perfect repo: {total}/{mx} ({pct}%) {grade}")

def test_empty_repo():
    with tempfile.TemporaryDirectory() as td:
        s = DocksideScorer()
        total, mx, pct, grade, _ = s.score_local(td)
        assert total == 0
        assert grade == '⚠️'
        print(f"✅ Empty repo: {total}/{mx} ({pct}%) {grade}")

test_perfect_repo()
test_empty_repo()
print("\n🟢 ALL DOCKSIDE TESTS PASSED")
