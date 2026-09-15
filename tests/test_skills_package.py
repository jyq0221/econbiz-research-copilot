import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.sync_skills import check_package, sync_skills


ROOT = Path(__file__).resolve().parents[1]


class SkillPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / '中文 复制目录'
        self.root.mkdir()
        for name in ('.agents', '.claude', 'docs'):
            shutil.copytree(ROOT / name, self.root / name)
        for name in ('AGENTS.md', 'CLAUDE.md'):
            shutil.copyfile(ROOT / name, self.root / name)

    def test_shipped_package_has_all_sources_copies_and_valid_links(self):
        self.assertEqual(check_package(self.root), [])

    def test_check_is_readonly_and_detects_asset_difference(self):
        asset = self.root / '.claude/skills/econbiz-research/assets/task-card.md'
        asset.write_text('changed', encoding='utf-8')
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertTrue(check_package(self.root))
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        sync_skills(self.root)
        self.assertEqual(check_package(self.root), [])

    def test_missing_source_bad_link_and_absolute_path_are_reported(self):
        skill = self.root / '.agents/skills/econbiz-design/SKILL.md'
        original = skill.read_text()
        for text in (original + '\n[bad](missing.md)\n', original + '\n/Users/test/private.txt\n'):
            skill.write_text(text, encoding='utf-8')
            self.assertTrue(check_package(self.root))
        skill.unlink()
        with self.assertRaises(ValueError):
            sync_skills(self.root)

    def test_sync_never_touches_other_skills_or_follows_symlinks(self):
        other = self.root / '.claude/skills/other'
        other.mkdir()
        (other / 'SKILL.md').write_text('user skill')
        old = self.root / '.claude/skills/econbiz-design/old.md'
        old.write_text('stale asset')
        sync_skills(self.root)
        self.assertFalse(old.exists())
        self.assertEqual((other / 'SKILL.md').read_text(), 'user skill')
        managed = self.root / '.claude/skills/econbiz-design'
        shutil.rmtree(managed)
        managed.symlink_to(other, target_is_directory=True)
        with self.assertRaises(ValueError):
            sync_skills(self.root)
        self.assertEqual((other / 'SKILL.md').read_text(), 'user skill')
