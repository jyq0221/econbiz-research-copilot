"""Maintain only the five named project skills. --check is strictly read-only."""

import argparse
import re
import shutil
from pathlib import Path
from urllib.parse import unquote


NAMES = tuple('econbiz-' + name for name in ('research', 'design', 'evidence', 'analysis', 'interpret'))


def _tree(root, directory):
    current = root
    for part in directory.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f'受管路径不能为符号链接：{current.relative_to(root)}')
    if not directory.exists():
        return {}
    paths = list(directory.rglob('*'))
    if any(path.is_symlink() for path in paths):
        raise ValueError(f'技能目录包含符号链接：{directory.relative_to(root)}')
    return {path.relative_to(directory).as_posix(): path.read_bytes() for path in paths if path.is_file()}


def _content_errors(root, files):
    errors = []
    for path in files:
        if path.suffix != '.md':
            continue
        content = path.read_text('utf-8')
        if re.search(r'/(?:Users|home)/[^\s/]+/|[A-Z]:\\\\', content):
            errors.append(f'包含本机绝对路径：{path.relative_to(root)}')
        for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)', content):
            link = unquote(link.strip('<>').split('#')[0])
            if not link or re.match(r'^[a-z]+:', link):
                continue
            target = (path.parent / link).resolve()
            if not target.is_relative_to(root) or not target.exists():
                errors.append(f'断链或越界：{path.relative_to(root)} -> {link}')
    return errors


def check_package(root):
    root = Path(root).resolve()
    errors, files = [], []
    for name in NAMES:
        source, target = root / '.agents/skills' / name, root / '.claude/skills' / name
        try:
            a, b = _tree(root, source), _tree(root, target)
            if 'SKILL.md' not in a:
                errors.append(f'缺少维护源：{name}/SKILL.md')
                continue
            text = a['SKILL.md'].decode('utf-8')
            if not text.startswith('---\n') or f'\nname: {name}\n' not in text or '\ndescription: ' not in text:
                errors.append(f'技能发现元数据无效：{name}')
            for key in sorted(a.keys() | b.keys()):
                if a.get(key) != b.get(key):
                    errors.append(f'副本不一致：{name}/{key}')
            files += [source / path for path in a] + [target / path for path in b]
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    for name in ('AGENTS.md', 'CLAUDE.md'):
        path = root / name
        if not path.is_file():
            errors.append(f'缺少入口：{name}')
        else:
            files.append(path)
    files += list((root / 'docs/research-handbook').glob('*.md'))
    errors.extend(_content_errors(root, files))
    return errors


def sync_skills(root):
    root = Path(root).resolve()
    # Validate every managed source/target before the first mutation.
    pairs = []
    for name in NAMES:
        source, target = root / '.agents/skills' / name, root / '.claude/skills' / name
        if 'SKILL.md' not in _tree(root, source):
            raise ValueError(f'缺少维护源：{name}/SKILL.md')
        _tree(root, target)
        pairs.append((source, target))
    for source, target in pairs:
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        if not args.check:
            sync_skills(root)
        errors = check_package(root)
    except (OSError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        print('\n'.join(errors))
        return 1
    print('五个项目 Skills 及两套入口检查通过')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
