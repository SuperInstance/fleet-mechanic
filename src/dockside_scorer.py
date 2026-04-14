"""Automated dockside exam scorer — check any repo's seaworthiness."""
import json, os, urllib.request, ssl
from pathlib import Path

class DocksideScorer:
    CHECKS = ['README.md', 'LICENSE', '.gitignore', 'tests/', '.github/workflows', 'CHANGELOG.md',
              'CHARTER.md', 'ABSTRACTION.md', 'STATE.md', 'DIARY/', 'Dockerfile']

    def score_local(self, path='.'):
        p = Path(path)
        results = {}
        for check in self.CHECKS:
            if check.endswith('/'):
                results[check] = (p / check.rstrip('/')).is_dir()
            elif check == 'LICENSE':
                results[check] = bool(list(p.glob('LICENSE*')))
            elif check == 'Dockerfile':
                results[check] = (p / 'Dockerfile').exists() or (p / '.devcontainer').exists()
            else:
                results[check] = (p / check).exists()
        total = sum(results.values())
        pct = round(total / len(results) * 100)
        grade = '🟢' if pct >= 80 else '🟡' if pct >= 60 else '⚠️'
        return total, len(results), pct, grade, results

    def score_github(self, repo, token=None):
        ctx = ssl.create_default_context()
        url = f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1"
        headers = {}
        if token: headers['Authorization'] = f'Bearer {token}'
        req = urllib.request.Request(url, headers=headers)
        try:
            data = json.loads(urllib.request.urlopen(req, timeout=10, context=ctx).read())
            files = [t['path'] for t in data.get('tree', []) if t['type'] == 'blob']
        except:
            return 0, len(self.CHECKS), 0, '❌', {}

        results = {}
        for check in self.CHECKS:
            name = check.rstrip('/')
            if check == 'LICENSE':
                results[check] = any(f.startswith('LICENSE') for f in files)
            elif check == 'Dockerfile':
                results[check] = 'Dockerfile' in files or '.devcontainer' in str(files)
            else:
                results[check] = name in files or any(f.startswith(name) for f in files)

        total = sum(results.values())
        pct = round(total / len(results) * 100)
        grade = '🟢' if pct >= 80 else '🟡' if pct >= 60 else '⚠️'
        return total, len(results), pct, grade, results

if __name__ == '__main__':
    import sys
    scorer = DocksideScorer()
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    total, mx, pct, grade, results = scorer.score_local(path)
    print(f'Dockside: {total}/{mx} ({pct}%) {grade}')
    for k, v in results.items():
        print(f'  [{"✅" if v else "❌"}] {k}')
