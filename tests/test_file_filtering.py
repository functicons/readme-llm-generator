import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys
import os
import typing # For type hints

# Add src directory to Python path to import generate_readme_llm
# This allows the test file to find the module being tested.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from generate_readme_llm import parse_and_chunk_repository, _clean_glob_patterns

class TestCleanGlobPatterns(unittest.TestCase):
    """
    Test suite for the `_clean_glob_patterns` utility function.
    """
    def test_strip_single_quotes(self) -> None:
        self.assertEqual(_clean_glob_patterns(["'pattern1'", "'p2/*'"]), ["pattern1", "p2/*"])

    def test_strip_double_quotes(self) -> None:
        self.assertEqual(_clean_glob_patterns(['"pattern1"', '"p2/*"']), ["pattern1", "p2/*"])

    def test_no_quotes(self) -> None:
        self.assertEqual(_clean_glob_patterns(["pattern1", "p2/*"]), ["pattern1", "p2/*"])

    def test_mixed_quotes_and_no_quotes(self) -> None:
        self.assertEqual(_clean_glob_patterns(["'p1'", '"p2"', "p3"]), ["p1", "p2", "p3"])

    def test_mismatched_quotes(self) -> None:
        # Mismatched quotes should not be stripped
        self.assertEqual(_clean_glob_patterns(["'pattern1\"", "\"p2'"]), ["'pattern1\"", "\"p2'"])

    def test_empty_list(self) -> None:
        self.assertEqual(_clean_glob_patterns([]), [])

    def test_empty_strings_and_quotes_only(self) -> None:
        # '' -> '' (empty string from single quotes)
        # "" -> "" (empty string from double quotes)
        # "'" -> "'" (single quote char, no change)
        # '"' -> '"' (double quote char, no change)
        self.assertEqual(_clean_glob_patterns(["''", '""', "'", '"', "notempty"]), ["", "", "'", '"', "notempty"])

    def test_patterns_with_internal_quotes(self) -> None:
        # Quotes are only stripped if they are at the very beginning AND end.
        self.assertEqual(_clean_glob_patterns(["'pat\"ern1'", "\"pat'ern2\""]), ["pat\"ern1", "pat'ern2"])

    def test_single_quote_inside_double_quotes(self) -> None:
        self.assertEqual(_clean_glob_patterns(["\"'\""]), ["'"])

    def test_double_quote_inside_single_quotes(self) -> None:
        self.assertEqual(_clean_glob_patterns(["'\"'"]), ["\""])

    def test_incomplete_quoting(self) -> None:
        self.assertEqual(_clean_glob_patterns(["'pat", "pat'", "\"pat", "pat\""]), ["'pat", "pat'", "\"pat", "pat\""])


class TestParseAndChunkRepositoryFiltering(unittest.TestCase):
    """
    Test suite for the `parse_and_chunk_repository` function, focusing on its
    file filtering capabilities (extensions, include/exclude patterns).
    """
    # Class attribute to hold the current test instance for the mock_read_text method.
    # This is a workaround because Path.read_text is patched globally for the class,
    # but needs access to instance-specific `self.repo_path`.
    instance: 'TestParseAndChunkRepositoryFiltering'

    def setUp(self) -> None:
        """
        Set up common test variables and mock file system structure.
        This method is called before each test function.
        """
        self.repo_path: Path = Path("/fake/repo") # Mock repository root path
        self.display_path: str = "/fake/repo" # Path used for display in logs
        self.extensions: list[str] = [".py", ".txt"] # Default extensions to include
        self.max_chunk_size: int = 1024  # Arbitrary small chunk size for testing
        # Store self instance to allow mock_read_text (patched to Path) to access test instance's repo_path
        TestParseAndChunkRepositoryFiltering.instance = self


    def _run_parser(self,
                    files_structure: dict[str, str],
                    include_patterns: typing.Optional[list[str]] = None,
                    exclude_patterns: typing.Optional[list[str]] = None,
                    extensions: typing.Optional[list[str]] = None
                   ) -> list[str]:
        """
        Helper method to run the `parse_and_chunk_repository` generator with mocked
        file system operations and collect the paths of processed files.

        Args:
            files_structure: A dictionary mapping relative file paths (from repo_path)
                             to their content.
                             e.g., {"file1.py": "print('hello')", "subdir/file2.txt": "text"}
            include_patterns: A list of glob patterns for including files.
            exclude_patterns: A list of glob patterns for excluding files.
            extensions: A list of file extensions to filter by. If None, uses self.extensions.

        Returns:
            A sorted list of unique relative file paths (as strings) that were processed by the parser.
        """
        processed_files: list[str] = []

        # --- Mocking os.walk ---
        # `walk_output` needs to be a list of tuples: (dirpath_str, dirnames_list, filenames_list)
        # e.g., [('/fake/repo', ['subdir'], ['file.py']), ('/fake/repo/subdir', [], ['file.py'])]
        walk_output: list[tuple[str, list[str], list[str]]] = []

        # `dir_contents` will store directory structure: { 'dir_path_str': ([subdirs_list], [files_in_dir_list]) }
        # This helps build the structure needed for os.walk mock.
        dir_contents: dict[str, tuple[list[str], list[str]]] = {}

        # Initialize root directory in dir_contents to ensure it's always present in walk_output
        if str(self.repo_path) not in dir_contents:
            dir_contents[str(self.repo_path)] = ([], [])

        # Populate dir_contents based on the paths in files_structure
        for p_rel_str in files_structure.keys():
            # p_rel is the relative path from repo_path, e.g., Path("subdir/file.py")
            p_rel = Path(p_rel_str)
            # current_abs_path is the full mocked path, e.g., Path("/fake/repo/subdir/file.py")
            current_abs_path = self.repo_path / p_rel

            # Add the file to its immediate parent's file list
            parent_abs_str = str(current_abs_path.parent)
            if parent_abs_str not in dir_contents: # Ensure parent directory entry exists
                dir_contents[parent_abs_str] = ([], [])
            if current_abs_path.name not in dir_contents[parent_abs_str][1]:
                 dir_contents[parent_abs_str][1].append(current_abs_path.name)

            # Ensure all ancestor directories of the file exist in dir_contents
            # and update their respective subdirectory lists.
            ancestor_path = current_abs_path.parent
            while ancestor_path != self.repo_path.parent : # Loop until above repo_path
                # Ensure current ancestor directory itself is in dir_contents
                if str(ancestor_path) not in dir_contents:
                    dir_contents[str(ancestor_path)] = ([], [])

                # Add current ancestor's name to its parent's list of subdirectories
                # (unless ancestor is the root repo_path itself, as root has no parent in this context)
                if ancestor_path != self.repo_path:
                    parent_of_ancestor_str = str(ancestor_path.parent)
                    if parent_of_ancestor_str not in dir_contents:
                         dir_contents[parent_of_ancestor_str] = ([],[])

                    if ancestor_path.name not in dir_contents[parent_of_ancestor_str][0]:
                        dir_contents[parent_of_ancestor_str][0].append(ancestor_path.name)

                if ancestor_path == self.repo_path: # Stop if we've processed the root directory
                    break
                ancestor_path = ancestor_path.parent # Move to the next ancestor up

        # Convert dir_contents to os.walk's expected output format
        # Sorting items for consistent mock_walk output, aiding test predictability.
        for path_str, (dirs, files_in_dir) in sorted(dir_contents.items()):
            walk_output.append((path_str, sorted(list(set(dirs))), sorted(list(set(files_in_dir)))))

        mock_walk = MagicMock(return_value=walk_output)

        # --- Mocking Path.read_text ---
        def mock_read_text_for_path(path_obj: Path, encoding: str ='utf-8') -> str:
            """
            Mocks Path.read_text to return content from the files_structure dict.
            'path_obj' is the Path instance on which read_text is called (e.g., an absolute Path).
            """
            # We need its path relative to the test's repo_path to look up in files_structure.
            # TestParseAndChunkRepositoryFiltering.instance provides access to the correct self.repo_path.
            rel_path_str = str(path_obj.relative_to(TestParseAndChunkRepositoryFiltering.instance.repo_path))
            return files_structure.get(rel_path_str, "") # Default to empty string if path not in mock data

        # Patch os.walk and Path.read_text for the duration of this method call
        with patch('os.walk', mock_walk), \
             patch.object(Path, 'read_text', mock_read_text_for_path):

            parser_extensions_to_use: list[str] = extensions if extensions is not None else self.extensions

            # Call the function under test
            # Note: parse_and_chunk_repository expects repo_path as a string
            for chunk in parse_and_chunk_repository(
                str(self.repo_path),
                parser_extensions_to_use,
                self.display_path,
                self.max_chunk_size,
                include_patterns or [],
                exclude_patterns or []
            ):
                # Extract file paths from the generated chunk headers
                for line in chunk.splitlines():
                    if line.startswith("# === File: "):
                        # Example line: "# === File: src/main.py ==="
                        file_path_in_chunk: str = line.replace("# === File: ", "").replace(" ===", "").strip()
                        processed_files.append(file_path_in_chunk)

            # Return sorted unique list of processed file paths for consistent assertion
            return sorted(list(set(processed_files)))

    def test_no_filtering_basic(self) -> None:
        """ Test with basic extension filtering, no include/exclude patterns. """
        files: dict[str, str] = {
            "file1.py": "content",      # Should be included (matches .py extension)
            "file2.txt": "content",     # Should be included (matches .txt extension)
            "file3.md": "content"       # Should be filtered out (by extension)
        }
        result: list[str] = self._run_parser(files)
        # Assert that only files with allowed extensions are processed
        self.assertEqual(result, ["file1.py", "file2.txt"])

    def test_include_pattern_simple(self) -> None:
        """ Test a simple include pattern. """
        files: dict[str, str] = {
            "proj/main.py": "content",      # Should be included by "proj/*.py"
            "proj/utils.py": "content",     # Should be included by "proj/*.py"
            "test/test_main.py": "content"  # Should be filtered out (not matching "proj/*.py")
        }
        result: list[str] = self._run_parser(files, include_patterns=["proj/*.py"])
        self.assertEqual(result, ["proj/main.py", "proj/utils.py"])

    def test_include_pattern_directory_recursive(self) -> None:
        """
        Test include pattern for recursive directory matching.
        `fnmatch` (used by the parser) with '*' typically doesn't cross directory separators ('/').
        A pattern like "src/*" matches "src/file.py" but not "src/subdir/file.py".
        For recursive matching, one might use "src/**/*" if the glob library supports it,
        or the calling code handles recursion and pattern application segment by segment.
        This test assumes `src/*` is intended to match anything under `src` due to how `os.walk` interacts
        with the path filtering in `parse_and_chunk_repository`.
        """
        files: dict[str, str] = {
            "src/app/file1.py": "content",      # Matches "src/*" if "*" can match "app/file1.py" or if applied segment-wise
            "src/lib/file2.py": "content",      # Matches "src/*"
            "src/lib/sub/file3.txt": "content", # .txt is a valid extension per self.extensions
            "data/info.txt": "content"          # Should be filtered out (not matching "src/*")
        }
        # The expected result implies that "src/*" effectively matches recursively here.
        expected_recursive_match: list[str] = sorted(["src/app/file1.py", "src/lib/file2.py", "src/lib/sub/file3.txt"])

        result: list[str] = self._run_parser(files, include_patterns=["src/*"])
        self.assertEqual(sorted(result), expected_recursive_match, "Test with 'src/*'")

        # Test with more explicit patterns that would achieve recursion if '*' is not directory-crossing
        # This assumes the glob interpretation allows '*' to match multiple segments or specific file names.
        # This part of the test is to explore the glob behavior more deeply.
        result_multi_glob: list[str] = self._run_parser(files, include_patterns=["src/*.*", "src/*/*.*", "src/*/*/*.*"])
        self.assertEqual(sorted(result_multi_glob), expected_recursive_match, "Test with 'src/*.*', 'src/*/*.*', etc.")


    def test_include_pattern_specific_files_in_dir(self) -> None:
        """ Test include pattern for specific files within a directory. """
        files: dict[str, str] = {
            "src/app/main.py": "content",   # Matches "src/app/*.py"
            "src/app/core.py": "content",   # Matches "src/app/*.py"
            "src/lib/utils.py": "content",  # Filtered out (not in "src/app/")
        }
        result: list[str] = self._run_parser(files, include_patterns=["src/app/*.py"])
        self.assertEqual(sorted(result), sorted(["src/app/core.py", "src/app/main.py"]))


    def test_exclude_pattern_simple(self) -> None:
        """ Test a simple exclude pattern for a specific file. """
        files: dict[str, str] = {
            "main.py": "content",
            "secrets.py": "content", # Should be excluded by "secrets.py"
            "config.txt": "content"
        }
        result: list[str] = self._run_parser(files, exclude_patterns=["secrets.py"])
        self.assertEqual(result, ["config.txt", "main.py"])

    def test_exclude_pattern_directory(self) -> None:
        """ Test excluding an entire directory using a glob pattern. """
        files: dict[str, str] = {
            "src/app/file1.py": "content",
            "src/app/file2.py": "content",
            "src/ignore_this/data.py": "content",      # Should be excluded by "src/ignore_this/*"
            "src/ignore_this/more_data.txt": "content",# Should be excluded by "src/ignore_this/*"
            "docs/readme.txt": "content"
        }
        result: list[str] = self._run_parser(files, exclude_patterns=["src/ignore_this/*"])
        self.assertEqual(sorted(result), sorted(["docs/readme.txt", "src/app/file1.py", "src/app/file2.py"]))

    def test_include_and_exclude_patterns(self) -> None:
        """ Test interaction of include and exclude patterns. Exclude takes precedence. """
        files: dict[str, str] = {
            "src/feature1/code.py": "content",      # Included by "src/*", not excluded
            "src/feature1/data.txt": "content",     # Included by "src/*", but then excluded by "*.txt"
            "src/common/utils.py": "content",       # Included by "src/*", not excluded
            "src/common/config.txt": "content",     # Included by "src/*", but then excluded by "*.txt"
            "tests/test_feature1.py": "content"     # Not included by "src/*"
        }
        result: list[str] = self._run_parser(files, include_patterns=["src/*"], exclude_patterns=["*.txt"])
        self.assertEqual(sorted(result), sorted(["src/common/utils.py", "src/feature1/code.py"]))

    def test_exclude_overrides_include(self) -> None:
        """ Test that exclude patterns take precedence over include patterns explicitly. """
        files: dict[str, str] = {
            "include_me/important.py": "content",
            "include_me/also_this.py": "content",
            "include_me/but_not_this.py": "content" # Matches include "include_me/*.py", but also exclude "*/but_not_this.py"
        }
        result: list[str] = self._run_parser(files, include_patterns=["include_me/*.py"], exclude_patterns=["*/but_not_this.py"])
        self.assertEqual(sorted(result), sorted(["include_me/also_this.py", "include_me/important.py"]))

    def test_no_patterns_provided(self) -> None:
        """ Test behavior when no include/exclude patterns are given (only default extension filtering). """
        files: dict[str, str] = {
            "file1.py": "content",
            "docs/file2.txt": "content",
            "another.md": "content" # Filtered by default extensions [.py, .txt]
        }
        result: list[str] = self._run_parser(files, include_patterns=[], exclude_patterns=[])
        self.assertEqual(sorted(result), sorted(["docs/file2.txt", "file1.py"]))

    def test_include_pattern_no_match(self) -> None:
        """ Test an include pattern that matches no files in the structure. """
        files: dict[str, str] = {
            "actual/file.py": "content",
            "another/file.txt": "content"
        }
        result: list[str] = self._run_parser(files, include_patterns=["nonexistent/*"])
        self.assertEqual(result, []) # Expect empty list as no files match the include pattern

    def test_extension_filter_with_patterns(self) -> None:
        """
        Test interaction of extension filtering (initial pass) and include/exclude patterns.
        Files are first filtered by extension, then include patterns, then exclude patterns.
        """
        files_refined: dict[str, str] = {
             "src/code.py": "content",      # Matches extension .py, matches include "src/*"
             "src/data.txt": "content",     # Matches extension .txt, matches include "src/*"
             "src/image.jpg": "content",    # Filtered out by extension (not .py or .txt)
             "other/script.py": "content"   # Matches extension .py, but filtered out by include "src/*"
        }
        result_refined: list[str] = self._run_parser(files_refined, include_patterns=["src/*"], exclude_patterns=[])
        self.assertEqual(sorted(result_refined), sorted(["src/code.py", "src/data.txt"]))

    def test_empty_repo(self) -> None:
        """ Test with an empty repository (no files defined in files_structure). """
        files: dict[str, str] = {}
        result: list[str] = self._run_parser(files)
        self.assertEqual(result, [])

    def test_only_excluded_files(self) -> None:
        """ Test a scenario where all files that would normally be included are excluded. """
        files: dict[str, str] = {"secret/one.py": "content", "secret/two.txt": "content"}
        # Both files match default extensions, but "secret/*" should exclude them.
        result: list[str] = self._run_parser(files, exclude_patterns=["secret/*"])
        self.assertEqual(result, [])

    def test_include_specific_extension_only(self) -> None:
        """
        Test using an include pattern to effectively select only files of a specific extension,
        even if other extensions are allowed by the main extension filter.
        """
        files: dict[str, str] = {
            "file.py": "py stuff",    # Matches "*.py"
            "file.txt": "text stuff", # Does not match "*.py", so filtered out by include pattern
            "another.py": "more py"   # Matches "*.py"
        }
        # Default extensions are [.py, .txt].
        # The include pattern "*.py" further refines the selection to only .py files.
        result: list[str] = self._run_parser(files, include_patterns=["*.py"])
        self.assertEqual(sorted(result), sorted(["another.py", "file.py"]))

    def test_include_pattern_star_py(self) -> None:
        """
        Test the "*.py" include pattern to ensure it correctly selects Python files
        across various directory levels, while respecting the initial extension filter
        (e.g., .md files should be out regardless of include patterns if not in self.extensions).
        """
        files: dict[str, str] = {
            "root.py": "python content",                        # Include (matches *.py and .py extension)
            "root.txt": "text content",                         # Exclude (matches .txt extension, but not *.py include pattern)
            "subdir/file1.py": "python content in subdir",      # Include (matches *.py and .py extension)
            "subdir/another.txt": "text content in subdir",     # Exclude (matches .txt extension, but not *.py include pattern)
            "subdir/subsubdir/file2.py": "python content in subsubdir", # Include (matches *.py and .py extension)
            "subdir/subsubdir/other.md": "markdown content"     # Exclude (filtered by extension first, as .md is not in self.extensions)
        }
        expected_files: list[str] = sorted([
            "root.py",
            "subdir/file1.py",
            "subdir/subsubdir/file2.py"
        ])
        # self.extensions is [".py", ".txt"]. Files are first filtered by these.
        # Then, include_patterns=["*.py"] is applied.
        result: list[str] = self._run_parser(files, include_patterns=["*.py"])
        self.assertEqual(sorted(result), expected_files)


if __name__ == '__main__':
    unittest.main()
