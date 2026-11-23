"""Preview skill copying; --apply installs without overwriting different files."""
import argparse
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def plan(destination):
    destination = Path(destination).expanduser().resolve()
    if destination == ROOT or ROOT in destination.parents:
        raise ValueError('Choose an installation directory outside this repository')
    actions = []
    for source in sorted((ROOT / 'skills').iterdir()):
        if not source.is_dir() or not (source / 'SKILL.md').is_file():
            continue
        if source.is_symlink() or (ROOT / 'skills') not in source.resolve().parents:
            raise ValueError('Unexpected linked skill')
        name = source.name
        for path in sorted(source.rglob('*')):
            if not path.is_file() or path.suffix not in ('.md', '.py', '.yaml', '.json', '.csv'):
                continue
            if path.is_symlink() or source not in path.resolve().parents:
                raise ValueError('Unexpected linked source')
            target = destination / name / path.relative_to(source)
            if destination not in target.resolve().parents:
                raise ValueError('Destination escapes installation root')
            if target.exists():
                if not target.is_file() or target.read_bytes() != path.read_bytes():
                    raise FileExistsError(f'Existing different file will not be overwritten: {target}')
                continue
            actions.append((path, target))
    return actions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    home = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
    parser.add_argument('--destination', type=Path, default=home / 'skills')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    actions = plan(args.destination)
    for source, target in actions:
        print(('COPY ' if args.apply else 'WOULD COPY ') + str(target))
        if args.apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    print(f'{len(actions)} files; no credentials configured or messages accessed.')


if __name__ == '__main__':
    main()
