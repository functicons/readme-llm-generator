# src/generate_readme_llm.py

import os
import time
import argparse
import fnmatch
import google.generativeai as genai
from pathlib import Path
import shutil

# --- Component: Configuration Loader ---
def load_configuration():
    """Loads configuration from environment variables."""
    api_key = os.getenv("GOOGLE_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest")
    debug_mode = os.getenv("DEBUG_MODE", "false").lower() == "true"
    max_prompt_size = int(os.getenv("MAX_PROMPT_SIZE", "512000"))
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set.")
    return api_key, model_name, debug_mode, max_prompt_size

# --- Component: Smart Parser & Chunker (GENERATOR) ---
def parse_and_chunk_repository(repo_path, extensions, display_path, max_chunk_size, include_patterns, exclude_patterns):
    """
    Scans a repository and yields content chunks, creating them one by one.
    This function is a generator, making it memory-efficient.
    """
    print(f"🔎 Scanning repository at '{display_path}' for files with extensions: {extensions} ...")
    current_chunk = ""
    total_files_processed = 0
    chunks_yielded = 0
    files_in_current_chunk = 0

    all_files = []
    for root, _, files in os.walk(repo_path):
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                all_files.append(Path(root) / file)

    if not all_files:
        print("✅ No files with the specified extensions were found.")
        return

    for file_path in all_files:
        relative_path = file_path.relative_to(repo_path)

        # Apply include patterns
        if include_patterns:
            if not any(fnmatch.fnmatch(str(relative_path), pattern) for pattern in include_patterns):
                continue  # Skip if not matching any include pattern

        # Apply exclude patterns
        if exclude_patterns:
            if any(fnmatch.fnmatch(str(relative_path), pattern) for pattern in exclude_patterns):
                continue  # Skip if matching any exclude pattern
        try:
            content = file_path.read_text(encoding='utf-8')
            total_files_processed += 1

            header = f"# === File: {relative_path} ===\n"
            separator = "\n\n"

            header_size = len(header.encode('utf-8'))
            if header_size + len(content.encode('utf-8')) > max_chunk_size:
                print(f"⚠️  Warning: File '{relative_path}' is too large and will be truncated.")
                max_content_size = max_chunk_size - header_size
                content = content.encode('utf-8')[:max_content_size].decode('utf-8', 'ignore')

            file_block = header + content
            size_to_add = len((separator + file_block).encode('utf-8')) if current_chunk else len(file_block.encode('utf-8'))

            if current_chunk and len(current_chunk.encode('utf-8')) + size_to_add > max_chunk_size:
                print(f"📦 Yielding chunk {chunks_yielded + 1} with {files_in_current_chunk} files...")
                yield current_chunk
                chunks_yielded += 1
                current_chunk = file_block
                files_in_current_chunk = 1
            else:
                current_chunk += (separator + file_block) if current_chunk else file_block
                files_in_current_chunk += 1
        except Exception as e:
            print(f"⚠️  Could not read file {file_path}: {e}")

    if current_chunk:
        print(f"📦 Yielding final chunk {chunks_yielded + 1} with {files_in_current_chunk} files...")
        yield current_chunk
        chunks_yielded += 1
    
    print(f"✅ Found and processed {total_files_processed} files into {chunks_yielded} chunks.")

# --- Component: Prompt Construction ---
def construct_prompt(source_code: str) -> str:
    """Reads the prompt template and appends the source code to it."""
    try:
        script_dir = Path(__file__).parent
        prompt_template_path = script_dir / "system_prompt.md"
        prompt_template = prompt_template_path.read_text(encoding="utf-8")
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
def generate_summary_with_gemini(api_key, model_name, source_code, debug_mode: bool):
    """Constructs a prompt, sends it to the Gemini API, and returns the response."""
    prompt = construct_prompt(source_code)
    if debug_mode:
        print("\n" + "="*20 + " DEBUG: PROMPT SENT TO GEMINI " + "="*20)
        print(prompt[:1000] + "...")
        print("="*69 + "\n")

    print(f"🤖 Calling Gemini API with model: {model_name} ...")
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        start_call_time = time.time()
        response = model.generate_content(prompt)
        end_call_time = time.time()
        call_duration = end_call_time - start_call_time

        if debug_mode:
            print("\n" + "="*20 + " DEBUG: RESPONSE FROM GEMINI " + "="*20)
            print(response.text)
            print("="*68 + "\n")
        try:
            usage = response.usage_metadata
            prompt_tokens_k = f"{usage.prompt_token_count / 1000:.1f}K"
            output_tokens_k = f"{usage.candidates_token_count / 1000:.1f}K"
            print(f"📊 Gemini API Usage: {prompt_tokens_k} prompt tokens -> {output_tokens_k} output tokens.")
        except (AttributeError, ValueError):
            print("📊 Gemini API Usage: Token count not available.")
        
        print(f"⏱️  Gemini API call took {call_duration:.2f} seconds.")
        print("✅ Summary generated successfully!")
        return response.text
    except Exception as e:
        print(f"❌ An API error occurred: {e}")
        raise

# --- Component: README.llm File Generator ---
def write_output_file(repo_path, content, display_path):
    """Writes the generated summary to the README.llm file in the repository root."""
    output_path_for_os = Path(repo_path) / "README.llm"
    output_path_for_log = Path(display_path) / "README.llm"
    print(f"✍️  Writing output to {output_path_for_log} ...")
    try:
        output_path_for_os.write_text(content, encoding='utf-8')
    except IOError as e:
        print(f"❌ Failed to write output file: {e}")
        raise

# --- Helper: Code Fence Stripper ---
def strip_markdown_code_block(text: str) -> str:
    """Removes markdown code block fences ` ``` if they surround the text."""
    stripped_text = text.strip()
    if stripped_text.startswith("```") and stripped_text.endswith("```"):
        first_newline_pos = stripped_text.find('\n')
        last_newline_pos = stripped_text.rfind('\n')
        if first_newline_pos != -1 and last_newline_pos > first_newline_pos:
            return stripped_text[first_newline_pos + 1 : last_newline_pos].strip()
    return text

# --- Helper: Merging Logic ---
def get_readme_parts(content: str) -> tuple[str, str]:
    """Splits a generated README file into header and body."""
    lines = content.splitlines(True)
    body_start_patterns = ["# === Module:", "declare module", "public interface", "namespace", "#pragma once", "package "]
    body_start_index = -1
    for i, line in enumerate(lines):
        if any(p in line for p in body_start_patterns):
            body_start_index = i
            break
    if body_start_index != -1:
        header = "".join(lines[:body_start_index])
        body = "".join(lines[body_start_index:])
        return header, body
    return "", content

def merge_readme_parts(tmp_files: list[Path]) -> str:
    """Merges multiple partial README.llm files into a single file, handling markdown fences and cleaning up."""
    if not tmp_files: return ""
    
    first_file_content = tmp_files[0].read_text(encoding='utf-8')
    was_fenced = first_file_content.strip().startswith("```")
    language = ""
    if was_fenced:
        language = first_file_content.strip().splitlines()[0][3:].strip()

    content_to_split = strip_markdown_code_block(first_file_content)
    header, first_body = get_readme_parts(content_to_split)

    all_bodies = [first_body.strip()]
    for tmp_file in tmp_files[1:]:
        content = tmp_file.read_text(encoding='utf-8')
        unfenced_content = strip_markdown_code_block(content)
        _, body = get_readme_parts(unfenced_content)
        all_bodies.append(body.strip())
        
    print("🤝 Merging content from all chunks...")
    
    # Combine and then clean up the result
    full_body = "\n\n".join(all_bodies)
    lines = full_body.splitlines()
    cleaned_lines = []
    for i, line in enumerate(lines):
        # Check if the line is a module header
        if line.strip().startswith("# === Module:"):
            # Check if the next line is also a module header or if the line is empty
            if (i + 1 < len(lines) and lines[i+1].strip().startswith("# ===")) or not lines[i+1].strip():
                # This is likely an empty module declaration, so we skip it
                continue
        cleaned_lines.append(line)

    final_body = "\n".join(cleaned_lines)
    final_content = header.strip() + "\n\n" + final_body

    if was_fenced:
        return f"```{language}\n{final_content.strip()}\n```"
    else:
        return final_content.strip()

# --- Main Orchestration Logic ---
def main():
    """Main function to orchestrate the README.llm generation process."""
    start_time = time.time()
    
    parser = argparse.ArgumentParser(description="Generate a README.llm file for a code repository.")
    parser.add_argument("repo_path", help="The path to the repository to analyze (e.g., /app/repo).")
    parser.add_argument("--ext", nargs="+", default=[".py", ".ts", ".js", ".java", ".hpp", ".h", ".go"], help="A list of file extensions to include in the analysis.")
    parser.add_argument("--include", nargs="+", default=[], help="List of glob patterns (e.g., '*.py', 'src/**') to include files/paths. These are not regular expressions. Applied after extension filtering.")
    parser.add_argument("--exclude", nargs="+", default=[], help="List of glob patterns (e.g., 'test_*', '**/temp/') to exclude files/paths. These are not regular expressions. Applied after include filtering and take precedence.")
    args = parser.parse_args()

    display_path = os.getenv("HOST_REPO_PATH", args.repo_path)
    temp_dir = Path(args.repo_path) / ".readme_llm_tmp"
    
    try:
        api_key, model_name, debug_mode, max_prompt_size = load_configuration()
        base_prompt = construct_prompt("")
        max_code_size = max_prompt_size - len(base_prompt.encode('utf-8'))
        
        chunk_generator = parse_and_chunk_repository(args.repo_path, args.ext, display_path, max_code_size, args.include, args.exclude)
        tmp_files = []
        
        for i, chunk in enumerate(chunk_generator):
            print(f"--- Processing chunk {i+1} ---")
            summary_chunk = generate_summary_with_gemini(api_key, model_name, chunk, debug_mode)
            if not temp_dir.exists():
                temp_dir.mkdir(exist_ok=True)
            tmp_file_path = temp_dir / f"chunk_{i}.tmp"
            tmp_file_path.write_text(summary_chunk, encoding='utf-8')
            tmp_files.append(tmp_file_path)

        if not tmp_files:
            print("✅ No content was generated because no relevant files were found.")
            return
        
        final_summary = ""
        if len(tmp_files) == 1:
            # For a single chunk, just strip the fences, no complex merging needed.
            raw_content = tmp_files[0].read_text(encoding='utf-8')
            was_fenced = raw_content.strip().startswith("```")
            final_summary = strip_markdown_code_block(raw_content)
            if was_fenced:
                 language = raw_content.strip().splitlines()[0][3:].strip()
                 final_summary = f"```{language}\n{final_summary}\n```"
        else:
            final_summary = merge_readme_parts(tmp_files)
        
        write_output_file(args.repo_path, final_summary, display_path)

        end_time = time.time()
        total_time = end_time - start_time
        print(f"📞 Total Gemini API calls: {len(tmp_files)}")
        print(f"🎉 Success! README.llm has been created.")
        print(f"⏰ Total time: {total_time:.2f} seconds.")

    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
    finally:
        if temp_dir.exists():
            print("🧹 Cleaning up temporary files...")
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    main()
