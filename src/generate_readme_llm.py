# src/generate_readme_llm.py

import os
import time
import argparse
import google.generativeai as genai
from pathlib import Path

# --- Component: Configuration Loader ---
def load_configuration():
    """Loads configuration from environment variables."""
    api_key = os.getenv("GOOGLE_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest")
    # Check for debug mode environment variable
    debug_mode = os.getenv("DEBUG_MODE", "false").lower() == "true"
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set.")
    return api_key, model_name, debug_mode

# --- Component: Repository Parser ---
def parse_repository(repo_path, extensions, display_path):
    """
    Scans a repository, finds relevant files, and aggregates their content.
    Uses 'display_path' for user-facing logs.
    """
    print(f"🔎 Scanning repository at '{display_path}' for files with extensions: {extensions} ...")
    aggregated_content = []
    for root, _, files in os.walk(repo_path):
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                file_path = Path(root) / file
                relative_path = file_path.relative_to(repo_path)
                try:
                    content = file_path.read_text(encoding='utf-8')
                    aggregated_content.append(f"# === File: {relative_path} ===\n{content}")
                except Exception as e:
                    print(f"⚠️  Could not read file {file_path}: {e}")
    if not aggregated_content:
        raise FileNotFoundError("No files with the specified extensions were found.")
    print(f"✅ Found and aggregated {len(aggregated_content)} files.")
    return "\n\n".join(aggregated_content)

# --- [UPDATED HELPER FUNCTION NAME] ---
def construct_prompt(source_code: str) -> str:
    """
    Reads the prompt template and appends the source code to it.
    """
    try:
        script_dir = Path(__file__).parent
        prompt_template_path = script_dir / "system_prompt.md"
        with open(prompt_template_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()

        # Append the user's code after the system prompt and examples.
        return (
            prompt_template
            + "\n---"
            + "\n\n## Aggregated Source Code to Analyze\n\n"
            + "Here is the aggregated source code to be analyzed:\n\n"
            + source_code
        )
    except FileNotFoundError:
        print(f"❌ Critical Error: The prompt template file was not found at {prompt_template_path}.")
        # Re-raise the exception to halt execution, as the app cannot proceed.
        raise

# --- Component: Gemini API Interaction ---
def generate_summary_with_gemini(api_key, model_name, source_code, debug_mode: bool):
    """
    Constructs a prompt, sends it to the Gemini API, and returns the response.
    """
    # 1. Construct the prompt first, outside the API-specific try/except block.
    prompt = construct_prompt(source_code)

    if debug_mode:
        print("\n" + "="*20 + " DEBUG: PROMPT SENT TO GEMINI " + "="*20)
        print(prompt)
        print("="*69 + "\n")

    # 2. Call the API, wrapping only the API-specific code in the try/except block.
    print(f"🤖 Calling Gemini API with model: {model_name} ...")
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)

        if debug_mode:
            print("\n" + "="*20 + " DEBUG: RESPONSE FROM GEMINI " + "="*20)
            print(response.text)
            print("="*68 + "\n")

        try:
            usage = response.usage_metadata
            # Format tokens in K (thousands)
            prompt_tokens_k = f"{usage.prompt_token_count / 1000:.1f}K"
            output_tokens_k = f"{usage.candidates_token_count / 1000:.1f}K"
            print(
                f"📊 Gemini API Usage: "
                f"{prompt_tokens_k} prompt tokens -> "
                f"{output_tokens_k} output tokens."
            )
        except Exception:
            print("📊 Gemini API Usage: Token count not available.")

        print("✅ Summary generated successfully!")
        return response.text
    except Exception as e:
        # This now correctly catches errors related to the API call itself.
        print(f"❌ An API error occurred: {e}")
        raise

# --- Component: README.llm File Generator ---
def write_output_file(repo_path, content, display_path):
    """
    Writes the generated summary to the README.llm file in the repository root.
    Uses 'display_path' for user-facing logs.
    """
    output_path_for_os = Path(repo_path) / "README.llm"
    output_path_for_log = Path(display_path) / "README.llm"
    print(f"✍️  Writing output to {output_path_for_log} ...")
    try:
        output_path_for_os.write_text(content, encoding='utf-8')
    except IOError as e:
        print(f"❌ Failed to write output file: {e}")
        raise

def main():
    """Main function to orchestrate the README.llm generation process."""
    # Capture start time
    start_time = time.time()
    
    parser = argparse.ArgumentParser(description="Generate a README.llm file for a code repository.")
    parser.add_argument("repo_path", help="The path to the repository to analyze (e.g., /app/repo).")
    parser.add_argument(
        "--ext",
        nargs="+",
        default=[".py", ".ts", ".js", ".java", ".hpp", ".h", ".go"],
        help="A list of file extensions to include in the analysis."
    )
    args = parser.parse_args()

    display_path = os.getenv("HOST_REPO_PATH", args.repo_path)
    try:
        api_key, model_name, debug_mode = load_configuration()
        aggregated_code = parse_repository(args.repo_path, args.ext, display_path)
        summary = generate_summary_with_gemini(api_key, model_name, aggregated_code, debug_mode)
        write_output_file(args.repo_path, summary, display_path)

        # Calculate and print total time
        end_time = time.time()
        total_time = end_time - start_time
        print(f"🎉 Success! README.llm has been created.")
        print(f"⏰ Total time: {total_time:.2f} seconds.")

    except (ValueError, FileNotFoundError) as e:
        print(f"❌ A configuration or file error occurred: {e}")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()