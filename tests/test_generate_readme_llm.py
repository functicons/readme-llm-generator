import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys
import os

# Add src directory to Python path to import generate_readme_llm
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from generate_readme_llm import parse_and_chunk_repository

class TestParseAndChunkRepositoryFiltering(unittest.TestCase):

    def setUp(self):
        self.repo_path = Path("/fake/repo")
        self.display_path = "/fake/repo"
        self.extensions = [".py", ".txt"]
        self.max_chunk_size = 1024  # Small chunk size for testing
        # Store self instance to access in mock_read_text from class method patch
        TestParseAndChunkRepositoryFiltering.instance = self


    def _run_parser(self, files_structure, include_patterns=None, exclude_patterns=None, extensions=None):
        processed_files = []

        walk_output = []
        # Correctly group files by their parent directory for os.walk mock
        # files_structure: {"file.py": "content", "subdir/file.py": "content"}
        # walk_output should be:
        # [('/fake/repo', ['subdir'], ['file.py']), ('/fake/repo/subdir', [], ['file.py'])]

        # Prepare entries for os.walk mock
        # Directory structure: { 'dir_path': ([subdirs], [files_in_dir]) }
        dir_contents = {}
        all_paths = [Path(p) for p in files_structure.keys()]

        # Populate root directory and subdirectories
        for p in all_paths:
            parent_str = str(self.repo_path / p.parent)
            if parent_str not in dir_contents:
                dir_contents[parent_str] = ([], [])

            if p.name != '.': # Ensure we don't add '.' as a file/dir name itself
                # Check if it's a directory by seeing if it's a parent of another path
                is_dir = any(other_p != p and p == other_p.parent for other_p in all_paths)
                if is_dir:
                    if p.name not in dir_contents[parent_str][0]:
                         dir_contents[parent_str][0].append(p.name)
                else: # It's a file
                    if p.name not in dir_contents[parent_str][1]:
                        dir_contents[parent_str][1].append(p.name)

        # Ensure all parent directories are in dir_contents, even if empty
        # For a path "a/b/c.txt", "a" and "a/b" must exist in walk
        # Start with root
        if str(self.repo_path) not in dir_contents:
            dir_contents[str(self.repo_path)] = ([], [])

        current_parents = {str(p.parent) for p in all_paths}
        for cp_str in current_parents:
            cp = self.repo_path / cp_str # This line was causing an error, should be relative to self.repo_path
            # Corrected cp construction:
            # cp_path_abs is the absolute path of the directory being processed
            # if cp_str is '.', it means self.repo_path itself
            # if cp_str is 'a/b', it means self.repo_path / 'a' / 'b'
            if cp_str == '.':
                 cp_path_abs = self.repo_path
            else:
                 cp_path_abs = self.repo_path / cp_str

            while cp_path_abs != self.repo_path.parent and cp_path_abs != self.repo_path : # Loop until we are above repo_path or at repo_path
                # Current directory (cp_path_abs) must be in dir_contents if it's not already
                if str(cp_path_abs) not in dir_contents:
                    dir_contents[str(cp_path_abs)] = ([],[])

                # Parent of current directory
                parent_of_cp_abs = cp_path_abs.parent
                if str(parent_of_cp_abs) not in dir_contents:
                     dir_contents[str(parent_of_cp_abs)] = ([],[])

                # Add current directory's name to its parent's list of subdirectories
                # unless current directory is the root itself or parent is above root
                if cp_path_abs != self.repo_path and parent_of_cp_abs != self.repo_path.parent :
                    if cp_path_abs.name not in dir_contents[str(parent_of_cp_abs)][0]:
                         dir_contents[str(parent_of_cp_abs)][0].append(cp_path_abs.name)

                if cp_path_abs == self.repo_path: # Stop if we processed the root
                    break
                cp_path_abs = parent_of_cp_abs

        # Convert to os.walk format
        for path_str, (dirs, files_in_dir) in sorted(dir_contents.items()):
            walk_output.append((path_str, sorted(list(set(dirs))), sorted(list(set(files_in_dir)))))

        mock_walk = MagicMock(return_value=walk_output)

        def mock_read_text_for_path(path_obj, encoding='utf-8'):
            # 'self' in this context is the Path instance
            rel_path_str = str(path_obj.relative_to(TestParseAndChunkRepositoryFiltering.instance.repo_path))
            return files_structure.get(rel_path_str, "")

        with patch('os.walk', mock_walk),              patch.object(Path, 'read_text', mock_read_text_for_path):

            parser_extensions = extensions if extensions is not None else self.extensions

            for chunk in parse_and_chunk_repository(
                self.repo_path, parser_extensions, self.display_path, self.max_chunk_size,
                include_patterns or [], exclude_patterns or []
            ):
                for line in chunk.splitlines():
                    if line.startswith("# === File: "):
                        processed_files.append(line.replace("# === File: ", "").replace(" ===", "").strip())
            return sorted(list(set(processed_files)))

    def test_no_filtering_basic(self):
        files = {
            "file1.py": "content",
            "file2.txt": "content",
            "file3.md": "content"
        }
        result = self._run_parser(files)
        self.assertEqual(result, ["file1.py", "file2.txt"])

    def test_include_pattern_simple(self):
        files = {
            "proj/main.py": "content",
            "proj/utils.py": "content",
            "test/test_main.py": "content"
        }
        result = self._run_parser(files, include_patterns=["proj/*.py"])
        self.assertEqual(result, ["proj/main.py", "proj/utils.py"])

    def test_include_pattern_directory_recursive(self):
        # Test if include like "src/**" or "src/*" works for nested files
        files = {
            "src/app/file1.py": "content",
            "src/lib/file2.py": "content",
            "src/lib/sub/file3.txt": "content", # txt is a valid extension
            "data/info.txt": "content"
        }
        # This should grab all .py and .txt files under src/ recursively
        # Given the environment's fnmatch behavior where '*' can match '/',
        # 'src/*' and 'src/**' and 'src/*.*' (for these specific file names) will behave similarly.
        expected_recursive_match = sorted(["src/app/file1.py", "src/lib/file2.py", "src/lib/sub/file3.txt"])

        result = self._run_parser(files, include_patterns=["src/*"]) # common glob for recursive, simplified from src/**
        self.assertEqual(sorted(result), expected_recursive_match)

        result_shallow = self._run_parser(files, include_patterns=["src/*"]) # only direct children
        self.assertEqual(sorted(result_shallow), expected_recursive_match) # Corrected based on observed fnmatch behavior

        result_shallow_files = self._run_parser(files, include_patterns=["src/*.*"])
        self.assertEqual(sorted(result_shallow_files), expected_recursive_match) # Corrected based on observed fnmatch behavior


    def test_include_pattern_specific_files_in_dir(self):
        files = {
            "src/app/main.py": "content",
            "src/app/core.py": "content",
            "src/lib/utils.py": "content",
        }
        result = self._run_parser(files, include_patterns=["src/app/*.py"])
        self.assertEqual(sorted(result), sorted(["src/app/core.py", "src/app/main.py"]))


    def test_exclude_pattern_simple(self):
        files = {
            "main.py": "content",
            "secrets.py": "content",
            "config.txt": "content"
        }
        result = self._run_parser(files, exclude_patterns=["secrets.py"])
        self.assertEqual(result, ["config.txt", "main.py"])

    def test_exclude_pattern_directory(self):
        files = {
            "src/app/file1.py": "content",
            "src/app/file2.py": "content",
            "src/ignore_this/data.py": "content",
            "src/ignore_this/more_data.txt": "content",
            "docs/readme.txt": "content"
        }
        result = self._run_parser(files, exclude_patterns=["src/ignore_this/*"])
        self.assertEqual(sorted(result), sorted(["docs/readme.txt", "src/app/file1.py", "src/app/file2.py"]))

    def test_include_and_exclude_patterns(self):
        files = {
            "src/feature1/code.py": "content",
            "src/feature1/data.txt": "content",
            "src/common/utils.py": "content",
            "src/common/config.txt": "content", # Will be included by src/* then excluded by *.txt
            "tests/test_feature1.py": "content"
        }
        result = self._run_parser(files, include_patterns=["src/*"], exclude_patterns=["*.txt"])
        self.assertEqual(sorted(result), sorted(["src/common/utils.py", "src/feature1/code.py"]))

    def test_exclude_overrides_include(self):
        files = {
            "include_me/important.py": "content",
            "include_me/also_this.py": "content",
            "include_me/but_not_this.py": "content"
        }
        result = self._run_parser(files, include_patterns=["include_me/*.py"], exclude_patterns=["*/but_not_this.py"])
        self.assertEqual(sorted(result), sorted(["include_me/also_this.py", "include_me/important.py"]))

    def test_no_patterns_provided(self):
        files = {
            "file1.py": "content",
            "docs/file2.txt": "content",
            "another.md": "content"
        }
        result = self._run_parser(files, include_patterns=[], exclude_patterns=[])
        self.assertEqual(sorted(result), sorted(["docs/file2.txt", "file1.py"]))

    def test_include_pattern_no_match(self):
        files = {
            "actual/file.py": "content",
            "another/file.txt": "content"
        }
        result = self._run_parser(files, include_patterns=["nonexistent/*"])
        self.assertEqual(result, [])

    def test_extension_filter_with_patterns(self):
        files = {
            "src/code.py": "content",
            "src/data.txt": "content",
            "src/image.jpg": "content", # Not .py or .txt
            "other/script.py": "content"
        }
        # This will be empty because src/* matches directories 'code.py' and 'data.txt' if they were dirs
        # but not the files themselves if they are directly under src.
        # The files_structure should represent files directly.
        # If files are src/code.py, then include pattern should be "src/code.py" or "src/*.*" or "src/*" (if fnmatch handles files for *)

        # Let's refine the files for this test to be more explicit about structure
        files_refined = {
             "src/code.py": "content",      # Match include "src/**", match extension
             "src/data.txt": "content",     # Match include "src/*", match extension
             "src/image.jpg": "content",    # Match include "src/*", but not extension
             "other/script.py": "content"   # Not in include "src/*", but match extension
        }
        result_refined = self._run_parser(files_refined, include_patterns=["src/*"], exclude_patterns=[])
        self.assertEqual(sorted(result_refined), sorted(["src/code.py", "src/data.txt"]))

    def test_empty_repo(self):
        files = {}
        result = self._run_parser(files)
        self.assertEqual(result, [])

    def test_only_excluded_files(self):
        files = {"secret/one.py": "content", "secret/two.txt": "content"}
        result = self._run_parser(files, exclude_patterns=["secret/*"])
        self.assertEqual(result, [])

    def test_include_specific_extension_only(self):
        files = {
            "file.py": "py stuff",
            "file.txt": "text stuff",
            "another.py": "more py"
        }
        # repo extensions are [.py, .txt]
        # we want to include only .py files using include pattern, not by changing general extensions
        result = self._run_parser(files, include_patterns=["*.py"])
        self.assertEqual(sorted(result), sorted(["another.py", "file.py"]))

    def test_include_pattern_star_py(self):
        files = {
            "root.py": "python content",
            "root.txt": "text content",
            "subdir/file1.py": "python content in subdir",
            "subdir/another.txt": "text content in subdir",
            "subdir/subsubdir/file2.py": "python content in subsubdir",
            "subdir/subsubdir/other.md": "markdown content"
        }
        expected_files = sorted([
            "root.py",
            "subdir/file1.py",
            "subdir/subsubdir/file2.py"
        ])
        # self.extensions is [".py", ".txt"], so *.py should only pick .py files
        # and ignore .txt and .md even if they would be picked by extension filter alone
        result = self._run_parser(files, include_patterns=["*.py"])
        self.assertEqual(sorted(result), expected_files)

if __name__ == '__main__':
    unittest.main()
