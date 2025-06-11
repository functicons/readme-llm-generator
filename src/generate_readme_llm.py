# src/generate_readme_llm.py

import os
import time
import argparse
import fnmatch
import google.generativeai as genai # type: ignore
from pathlib import Path
import shutil

import typing # Import the typing module for type hints

# --- Component: Configuration Loader ---
def load_configuration() -> tuple[str, str, bool, int]:
    """
    Loads configuration from environment variables.

    Returns:
        A tuple containing:
            - api_key (str): The Google API key.
            - model_name (str): The Gemini model name.
            - debug_mode (bool): Flag indicating if debug mode is enabled.
            - max_prompt_size (int): Maximum prompt size in characters.
    Raises:
        ValueError: If the GOOGLE_API_KEY environment variable is not set.
    """
    api_key: typing.Optional[str] = os.getenv("GOOGLE_API_KEY")
    model_name: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest")
    debug_mode: bool = os.getenv("DEBUG_MODE", "false").lower() == "true"
    max_prompt_size: int = int(os.getenv("MAX_PROMPT_SIZE", "512000"))
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set.")
    return api_key, model_name, debug_mode, max_prompt_size

# --- Component: Smart Parser & Chunker (GENERATOR) ---
def parse_and_chunk_repository(
    repo_path: str,
    extensions: list[str],
    display_path: str,
    max_chunk_size: int,
    include_patterns: list[str],
    exclude_patterns: list[str]
) -> typing.Generator[str, None, None]:
    """
    Scans a repository, filters files by include/exclude patterns and extensions,
    and yields content chunks. This function is a generator, making it memory-efficient.

    Args:
        repo_path: The absolute path to the repository.
        extensions: A list of file extensions to include (e.g., ['.py', '.js']).
        display_path: The path to display in log messages (can be relative).
        max_chunk_size: The maximum size of each content chunk in bytes.
        include_patterns: List of glob patterns to include files.
        exclude_patterns: List of glob patterns to exclude files.

    Yields:
        str: A chunk of aggregated source code, prefixed with file headers.
    """
    print(f"🔎 Scanning repository at '{display_path}' for files with extensions: {extensions} ...")
    current_chunk: str = ""
    total_files_processed: int = 0
    chunks_yielded: int = 0
    files_in_current_chunk: int = 0

    all_files: list[Path] = []
    # Walk through the repository to find all files
    for root, _, files in os.walk(repo_path):
        for file in files:
            # Filter by specified extensions
            if any(file.endswith(ext) for ext in extensions):
                all_files.append(Path(root) / file)

    if not all_files:
        print("✅ No files with the specified extensions were found.")
        return

    # Process each found file
    for file_path in all_files:
        relative_path: Path = file_path.relative_to(repo_path)

        # Apply include patterns: skip if not matching any include pattern
        if include_patterns:
            if not any(fnmatch.fnmatch(str(relative_path), pattern) for pattern in include_patterns):
                continue

        # Apply exclude patterns: skip if matching any exclude pattern
        if exclude_patterns:
            if any(fnmatch.fnmatch(str(relative_path), pattern) for pattern in exclude_patterns):
                continue
        try:
            content: str = file_path.read_text(encoding='utf-8')
            total_files_processed += 1

            header: str = f"# === File: {relative_path} ===\n"
            separator: str = "\n\n" # Separator between file contents in a chunk

            # Check if the file itself is too large and truncate if necessary
            header_size: int = len(header.encode('utf-8'))
            if header_size + len(content.encode('utf-8')) > max_chunk_size:
                print(f"⚠️  Warning: File '{relative_path}' is too large and will be truncated.")
                max_content_size: int = max_chunk_size - header_size
                content = content.encode('utf-8')[:max_content_size].decode('utf-8', 'ignore')

            file_block: str = header + content
            # Calculate size to be added, including separator if current_chunk is not empty
            size_to_add: int = len((separator + file_block).encode('utf-8')) if current_chunk else len(file_block.encode('utf-8'))

            # If adding the new file block exceeds max_chunk_size, yield the current chunk
            if current_chunk and len(current_chunk.encode('utf-8')) + size_to_add > max_chunk_size:
                print(f"📦 Yielding chunk {chunks_yielded + 1} with {files_in_current_chunk} files...")
                yield current_chunk
                chunks_yielded += 1
                current_chunk = file_block # Start a new chunk with the current file block
                files_in_current_chunk = 1
            else:
                # Add the file block to the current chunk
                current_chunk += (separator + file_block) if current_chunk else file_block
                files_in_current_chunk += 1
        except Exception as e:
            print(f"⚠️  Could not read file {file_path}: {e}")

    # Yield any remaining content in the last chunk
    if current_chunk:
        print(f"📦 Yielding final chunk {chunks_yielded + 1} with {files_in_current_chunk} files...")
        yield current_chunk
        chunks_yielded += 1
    
    print(f"✅ Found and processed {total_files_processed} files into {chunks_yielded} chunks.")

# --- Component: Prompt Construction ---
def construct_prompt(source_code: str) -> str:
    """
    Reads the prompt template from 'system_prompt.md' and appends the provided
    source code to it.

    Args:
        source_code: A string containing the aggregated source code.

    Returns:
        A string representing the complete prompt to be sent to the LLM.

    Raises:
        FileNotFoundError: If 'system_prompt.md' is not found.
    """
    try:
        script_dir: Path = Path(__file__).parent
        prompt_template_path: Path = script_dir / "system_prompt.md"
        prompt_template: str = prompt_template_path.read_text(encoding="utf-8")
        # Combine the template with the source code
        return (
            prompt_template
            + "\n---\n\n## Aggregated Source Code to Analyze\n\n"
            + "Here is the aggregated source code to be analyzed:\n\n"
            + source_code
        )
    except FileNotFoundError:
        print(f"❌ Critical Error: The prompt template file was not found at {prompt_template_path}.")
        raise

# --- Component: Gemini API Interaction ---
def generate_summary_with_gemini(api_key: str, model_name: str, source_code: str, debug_mode: bool) -> str:
    """
    Constructs a prompt, sends it to the Gemini API, and returns the generated summary.

    Args:
        api_key: The Google API key.
        model_name: The name of the Gemini model to use.
        source_code: The source code string to summarize.
        debug_mode: If True, prints debug information about the prompt and response.

    Returns:
        The summary text generated by the Gemini API.

    Raises:
        Exception: If an API error occurs.
    """
    prompt: str = construct_prompt(source_code)
    if debug_mode:
        print("\n" + "="*20 + " DEBUG: PROMPT SENT TO GEMINI " + "="*20)
        # Print only the beginning of the prompt for brevity
        print(prompt[:1000] + "...")
        print("="*69 + "\n")

    print(f"🤖 Calling Gemini API with model: {model_name} ...")
    try:
        genai.configure(api_key=api_key)
        model: genai.GenerativeModel = genai.GenerativeModel(model_name)
        start_call_time: float = time.time()
        response: genai.types.GenerateContentResponse = model.generate_content(prompt)
        end_call_time: float = time.time()
        call_duration: float = end_call_time - start_call_time

        if debug_mode:
            print("\n" + "="*20 + " DEBUG: RESPONSE FROM GEMINI " + "="*20)
            print(response.text)
            print("="*68 + "\n")
        try:
            # Attempt to get usage metadata
            usage = response.usage_metadata
            prompt_tokens_k: str = f"{usage.prompt_token_count / 1000:.1f}K"
            output_tokens_k: str = f"{usage.candidates_token_count / 1000:.1f}K"
            print(f"📊 Gemini API Usage: {prompt_tokens_k} prompt tokens -> {output_tokens_k} output tokens.")
        except (AttributeError, ValueError):
            # Handle cases where usage metadata might not be available
            print("📊 Gemini API Usage: Token count not available.")
        
        print(f"⏱️  Gemini API call took {call_duration:.2f} seconds.")
        print("✅ Summary generated successfully!")
        return response.text
    except Exception as e:
        print(f"❌ An API error occurred: {e}")
        raise

# --- Component: README.llm File Generator ---
def write_output_file(repo_path: str, content: str, display_path: str) -> None:
    """
    Writes the generated summary to the README.llm file in the repository root.

    Args:
        repo_path: The absolute path to the repository.
        content: The content to write to the file.
        display_path: The path to display in log messages.

    Raises:
        IOError: If writing to the file fails.
    """
    output_path_for_os: Path = Path(repo_path) / "README.llm"
    output_path_for_log: Path = Path(display_path) / "README.llm" # For display purposes
    print(f"✍️  Writing output to {output_path_for_log} ...")
    try:
        output_path_for_os.write_text(content, encoding='utf-8')
    except IOError as e:
        print(f"❌ Failed to write output file: {e}")
        raise

# --- Helper: Glob Pattern Cleaner ---
def _clean_glob_patterns(patterns: list[str]) -> list[str]:
    """
    Cleans a list of glob patterns by removing surrounding single or double quotes.

    Args:
        patterns: A list of pattern strings.

    Returns:
        A new list with cleaned patterns.
    """
    if not patterns:
        return []
    cleaned_patterns = []
    for pattern in patterns:
        if len(pattern) >= 2 and pattern.startswith("'") and pattern.endswith("'"):
            cleaned_patterns.append(pattern[1:-1])
        elif len(pattern) >= 2 and pattern.startswith('"') and pattern.endswith('"'):
            cleaned_patterns.append(pattern[1:-1])
        else:
            cleaned_patterns.append(pattern)
    return cleaned_patterns

# --- Helper: Code Fence Stripper ---
def strip_markdown_code_block(text: str) -> str:
    """
    Removes markdown code block fences (```) if they surround the text.
    It also removes the language specifier if present after the opening fence.

    Args:
        text: The input string.

    Returns:
        The string with markdown code fences removed, or the original string if not fenced.
    """
    stripped_text: str = text.strip()
    # Check if the text starts and ends with triple backticks
    if stripped_text.startswith("```") and stripped_text.endswith("```"):
        # Find the first newline, which signifies the end of the opening fence line
        first_newline_pos: int = stripped_text.find('\n')
        # Find the last newline, which signifies the start of the closing fence line
        last_newline_pos: int = stripped_text.rfind('\n')

        # Ensure both newlines are found and in correct order
        if first_newline_pos != -1 and last_newline_pos > first_newline_pos:
            # Extract the content between the fences
            return stripped_text[first_newline_pos + 1 : last_newline_pos].strip()
    # If not fenced or malformed, return the original text
    return text

# --- Helper: Merging Logic ---
def get_readme_parts(content: str) -> tuple[str, str]:
    """
    Splits a generated README file (or a part of it) into a header and body.
    The split point is determined by common patterns indicating the start of the main code/module documentation.

    Args:
        content: The content of a README file or chunk.

    Returns:
        A tuple containing:
            - header (str): The part of the content before the main body.
            - body (str): The main body of the content.
    """
    lines: list[str] = content.splitlines(True) # Keep line endings
    # Patterns that usually indicate the start of the main documentation body
    body_start_patterns: list[str] = ["# === Module:", "declare module", "public interface", "namespace", "#pragma once", "package "]
    body_start_index: int = -1

    # Find the first line that matches one of the body start patterns
    for i, line in enumerate(lines):
        if any(p in line for p in body_start_patterns):
            body_start_index = i
            break

    if body_start_index != -1:
        # Split into header and body
        header: str = "".join(lines[:body_start_index])
        body: str = "".join(lines[body_start_index:])
        return header, body
    # If no pattern is found, assume the entire content is the body
    return "", content

def merge_readme_parts(tmp_files: list[Path]) -> str:
    """
    Merges multiple partial README.llm files (chunks) into a single coherent file.
    It handles markdown code fences, extracts headers and bodies, and cleans up redundant module declarations.

    Args:
        tmp_files: A list of Path objects pointing to temporary chunk files.

    Returns:
        A string containing the merged and cleaned-up README content.
    """
    if not tmp_files:
        return "" # Return empty string if there are no files to merge
    
    # Read the first file to determine initial fencing and language
    first_file_content: str = tmp_files[0].read_text(encoding='utf-8')
    was_fenced: bool = first_file_content.strip().startswith("```")
    language: str = ""
    if was_fenced:
        # Extract language from the first line (e.g., ```python)
        language = first_file_content.strip().splitlines()[0][3:].strip()

    # Strip fences and get header/body from the first file
    content_to_split: str = strip_markdown_code_block(first_file_content)
    header, first_body = get_readme_parts(content_to_split)

    all_bodies: list[str] = [first_body.strip()]
    # Process subsequent temporary files
    for tmp_file in tmp_files[1:]:
        content: str = tmp_file.read_text(encoding='utf-8')
        unfenced_content: str = strip_markdown_code_block(content)
        _, body = get_readme_parts(unfenced_content) # We only need the body from subsequent files
        all_bodies.append(body.strip())
        
    print("🤝 Merging content from all chunks...")
    
    # Combine all bodies and then clean up
    full_body: str = "\n\n".join(all_bodies)
    lines: list[str] = full_body.splitlines()
    cleaned_lines: list[str] = []

    # Clean up potentially redundant or empty module headers
    for i, line in enumerate(lines):
        # Check if the line is a module header like "# === Module:"
        if line.strip().startswith("# === Module:"):
            # Check if the next line is also a module header or if the current module content is empty
            # This helps remove empty module declarations that might occur due to chunking
            if (i + 1 < len(lines) and lines[i+1].strip().startswith("# ===")) or \
               (i + 1 < len(lines) and not lines[i+1].strip()): # Next line is empty
                continue # Skip this likely empty/redundant module declaration
        cleaned_lines.append(line)

    final_body: str = "\n".join(cleaned_lines)
    # Combine the initial header with the cleaned and merged bodies
    final_content: str = header.strip() + "\n\n" + final_body

    # Re-apply fencing if it was present initially
    if was_fenced:
        return f"```{language}\n{final_content.strip()}\n```"
    else:
        return final_content.strip()

# --- Main Orchestration Logic ---
def main() -> None:
    """
    Main function to orchestrate the README.llm generation process.
    Parses arguments, loads configuration, processes files in chunks,
    generates summaries using Gemini, merges them, and writes the final README.llm.
    """
    start_time: float = time.time()
    
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="Generate a README.llm file for a code repository.")
    parser.add_argument("repo_path", type=str, help="The path to the repository to analyze (e.g., /app/repo).")
    parser.add_argument("--ext", nargs="+", default=[".py", ".ts", ".js", ".java", ".hpp", ".h", ".go"],
                        help="A list of file extensions to include in the analysis.")
    parser.add_argument("--include", nargs="+", default=[],
                        help="List of glob patterns (e.g., '*.py', 'src/**') to include files/paths. Applied after extension filtering.")
    parser.add_argument("--exclude", nargs="+", default=[],
                        help="List of glob patterns (e.g., 'test_*', '**/temp/') to exclude files/paths. Applied after include filtering and take precedence.")
    args: argparse.Namespace = parser.parse_args()

    # Clean up glob patterns using the utility function
    args.include = _clean_glob_patterns(args.include)
    args.exclude = _clean_glob_patterns(args.exclude)

    # Determine the display path for logs (can be different from actual repo_path in containers)
    display_path: str = os.getenv("HOST_REPO_PATH", args.repo_path)
    # Define a temporary directory for storing chunk summaries
    temp_dir: Path = Path(args.repo_path) / ".readme_llm_tmp"
    
    try:
        # --- Configuration & Initialization ---
        api_key, model_name, debug_mode, max_prompt_size = load_configuration()
        # Construct a base prompt to calculate available size for code
        base_prompt: str = construct_prompt("")
        max_code_size: int = max_prompt_size - len(base_prompt.encode('utf-8'))
        
        # --- File Parsing and Chunking ---
        chunk_generator: typing.Generator[str, None, None] = parse_and_chunk_repository(
            args.repo_path, args.ext, display_path, max_code_size, args.include, args.exclude
        )
        tmp_files: list[Path] = [] # To store paths of temporary summary files
        
        # --- Process Each Chunk ---
        for i, chunk in enumerate(chunk_generator):
            print(f"--- Processing chunk {i+1} ---")
            # Generate summary for the current chunk
            summary_chunk: str = generate_summary_with_gemini(api_key, model_name, chunk, debug_mode)

            # Create temporary directory if it doesn't exist
            if not temp_dir.exists():
                temp_dir.mkdir(exist_ok=True)
            # Write chunk summary to a temporary file
            tmp_file_path: Path = temp_dir / f"chunk_{i}.tmp"
            tmp_file_path.write_text(summary_chunk, encoding='utf-8')
            tmp_files.append(tmp_file_path)

        if not tmp_files:
            print("✅ No content was generated because no relevant files were found or all were excluded.")
            return # Exit if no temporary files were created
        
        # --- Merging and Final Output ---
        final_summary: str = ""
        if len(tmp_files) == 1:
            # If only one chunk, no complex merging is needed, just potential fence stripping/re-adding
            raw_content: str = tmp_files[0].read_text(encoding='utf-8')
            was_fenced_single: bool = raw_content.strip().startswith("```")
            final_summary = strip_markdown_code_block(raw_content)
            if was_fenced_single:
                 # Re-add fence with original language if present
                 language_single: str = raw_content.strip().splitlines()[0][3:].strip()
                 final_summary = f"```{language_single}\n{final_summary}\n```"
        else:
            # Merge summaries from multiple chunks
            final_summary = merge_readme_parts(tmp_files)
        
        # Write the final merged summary to README.llm
        write_output_file(args.repo_path, final_summary, display_path)

        # --- Reporting ---
        end_time: float = time.time()
        total_time: float = end_time - start_time
        print(f"📞 Total Gemini API calls: {len(tmp_files)}")
        print(f"🎉 Success! README.llm has been created at {Path(display_path) / 'README.llm'}.")
        print(f"⏰ Total time: {total_time:.2f} seconds.")

    except Exception as e:
        # Catch-all for any unexpected errors during the process
        print(f"❌ An unexpected error occurred: {e}")
    finally:
        # --- Cleanup ---
        # Remove the temporary directory if it exists
        if temp_dir.exists():
            print("🧹 Cleaning up temporary files...")
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    main()
