"""Run offline suites only. Does not load real profiles or contact providers."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    for path in [*sorted((ROOT / 'skills').glob('*/tests')), ROOT / 'tests']:
        result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover',
                                 '-s', str(path), '-v'], cwd=ROOT)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
