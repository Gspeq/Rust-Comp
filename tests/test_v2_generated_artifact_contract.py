from __future__ import annotations

import subprocess
import unittest
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "v2"


def git_source_candidates() -> list[PurePosixPath]:
    """Return every tracked or untracked non-ignored path under v2/."""
    completed = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "v2",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        PurePosixPath(line.strip())
        for line in completed.stdout.splitlines()
        if line.strip()
    ]


class V2GeneratedArtifactContractTests(unittest.TestCase):
    def test_v2_gitignore_blocks_generated_trees(self) -> None:
        source = (V2 / ".gitignore").read_text(encoding="utf-8")
        for required in (
            "/target/",
            "/apps/desktop/node_modules/",
            "/apps/desktop/dist/",
            "/apps/desktop/.vite/",
            "__pycache__/",
            "*.py[cod]",
        ):
            self.assertIn(required, source)

    def test_protected_dotfiles_are_source_files(self) -> None:
        candidates = set(git_source_candidates())
        for relative in (".env.example", ".gitignore"):
            path = V2 / relative
            self.assertTrue(path.is_file(), path)
            self.assertGreater(path.stat().st_size, 0, path)
            self.assertIn(PurePosixPath("v2") / relative, candidates)

    def test_source_candidates_contain_no_generated_trees(self) -> None:
        forbidden = {"target", "node_modules", "dist", ".vite", "__pycache__"}
        offenders = [
            path.as_posix()
            for path in git_source_candidates()
            if any(part in forbidden for part in path.parts)
        ]
        self.assertEqual([], offenders)

    def test_source_candidates_contain_no_compiled_artifacts(self) -> None:
        forbidden_suffixes = {
            ".exe",
            ".dll",
            ".pdb",
            ".obj",
            ".o",
            ".rlib",
            ".rmeta",
            ".lib",
            ".a",
            ".pyc",
            ".pyo",
        }
        offenders = [
            path.as_posix()
            for path in git_source_candidates()
            if path.suffix.casefold() in forbidden_suffixes
        ]
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
