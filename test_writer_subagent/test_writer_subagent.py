import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from langchain_core.tools import tool
from shared_utils.prompt_utils import get_inherited_prompt
from shared_utils.schema_utils import TestWriterAgentOutput
from shared_utils.logger import get_logger

logger = get_logger("test-writer-subagent")

TEST_WRITER_ROLE = "You are a Java test generation agent. Your goal is to generate robust tests to improve coverage."

TEST_WRITER_PROTOCOL = """
1. **INSPECTION:** For EVERY class listed in your instructions, call `inspect_java_class` to retrieve the production code and any existing tests.
2. **PLANNING:** Analyze the logic for ALL target classes and define the required test cases based on the `TESTING_STANDARDS.md` file.
3. **GENERATION:** Create comprehensive test suites for ALL requested classes. You must output a separate `write_file` call for EACH test class.
4. **SUBMISSION:** Provide the final report listing all files created and classes covered.
"""

TEST_WRITER_RULES = """
- **TECHNICAL IMPLEMENTATION:** You MUST use the `inspect_java_class` tool to gather context for each class.
- **BATCH PROCESSING:** You are encouraged to handle multiple classes in a single turn. Ensure you call `write_file` once for each class.
- **TESTS ONLY:** You are strictly forbidden from modifying any files in `src/main/java`. Only write to `src/test/java`.
- **STANDARDS:** Adhere to the provided `TESTING_STANDARDS.md` file for every single file you generate.
- **MANDATORY TAGGING:** Every test class and every test method in EVERY file MUST be annotated with `@Tag("ai-generated")`.
- **ONE-SHOT STRATEGY:** Generate the entire class at once. Do not sequentialize method creation.
- **EXISTING TESTS:** Preserve useful parts of existing tests; do not duplicate logic.
- **SANDBOX:** You operate within a sandboxed directory. All paths are relative to your root (/).
- **FINALIZE:** To finish your task, you **MUST** call the `submit_test_writer_output` tool.
"""

def _read_standards() -> str:
    """Finds and reads the 'TESTING_STANDARDS.md' file."""
    try:
        std_content = "No TESTING_STANDARDS.md found in project."
        std_file = Path("TESTING_STANDARDS.md")
        if not std_file.exists():
            std_candidates = list(Path(".").glob("**/TESTING_STANDARDS.md"))
            if std_candidates:
                std_file = std_candidates[0]
        if std_file.exists():
            std_content = std_file.read_text(encoding="utf-8")
        return f"### CONTENT OF TESTING_STANDARDS.md (Source: {std_file}) ###\n{std_content}"
    except Exception as e:
        return f"Error reading standards: {str(e)}"

def _fast_find_file(root: Path, target_name: str) -> Path | None:
    """Fast file search using ripgrep (rg) if available."""
    try:
        cmd = ["rg", "--files", "--glob", f"**/{target_name}", str(root)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and result.stdout:
            paths = result.stdout.strip().split('\n')
            if paths:
                best_match = paths[0]
                for p in paths:
                    if "src/main/java" in p:
                        best_match = p
                        break
                return Path(best_match)
    except Exception:
        pass
    ignored_dirs = {'build', '.git', '.gradle', 'node_modules', 'target', 'dist', 'out'}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignored_dirs]
        for f in filenames:
            if f == target_name:
                return Path(dirpath) / f
    return None

@tool
def inspect_java_class(class_name: str) -> str:
    """Locates and reads a Java class and its test class."""
    start_time = time.time()
    logger.info(f"🔍 Inspecting class: {class_name}")
    try:
        root = Path(".")
        rel_path = class_name.replace(".", "/") + ".java"
        candidates = [root / "src/main/java" / rel_path, root / "src/test/java" / rel_path]
        source_file = None
        for c in candidates:
            if c.exists():
                source_file = c
                break
        test_file = None
        if not source_file:
            simple_name = class_name.split(".")[-1]
            target_file_name = f"{simple_name}.java"
            test_name = simple_name + "Test.java"
            with ThreadPoolExecutor(max_workers=2) as executor:
                f_src = executor.submit(_fast_find_file, root, target_file_name)
                f_test = executor.submit(_fast_find_file, root, test_name)
                source_file = f_src.result()
                test_file = f_test.result()
        if not source_file:
            return f"❌ Could not find Java class '{class_name}' in project."
        source_content = source_file.read_text(encoding="utf-8")
        test_content = "No existing test file found."
        if not test_file:
            src_path_str = str(source_file)
            if "src/main/java" in src_path_str:
                test_path_str = src_path_str.replace("src/main/java", "src/test/java").replace(".java", "Test.java")
                test_candidate = Path(test_path_str)
                if test_candidate.exists():
                    test_file = test_candidate
        if not test_file:
            simple_name = class_name.split(".")[-1]
            test_name = simple_name + "Test.java"
            test_file = _fast_find_file(root, test_name)
        if test_file:
            test_content = test_file.read_text(encoding="utf-8")
        
        def to_logical(p: Path) -> str:
            try:
                return "/" + str(p.relative_to(root))
            except ValueError:
                return str(p)

        output = [
            f"MODULE: {to_logical(source_file.parent)}",
            f"TARGET CLASS PATH: {to_logical(source_file)}",
            "-" * 40,
            source_content,
            "-" * 40,
            f"EXISTING TEST PATH: {to_logical(test_file) if test_file else 'N/A'}",
            "-" * 40,
            test_content
        ]
        return "\n".join(output)
    except Exception as e:
        return f"Error inspecting class: {str(e)}"

@tool(args_schema=TestWriterAgentOutput)
def submit_test_writer_output(**kwargs):
    """Finalizes the Test Writer agent's work and returns the structured result."""
    files = kwargs.get('files_created', [])
    status = kwargs.get('status')
    logger.info(f"✍️  Test generation finished. Status: {status}. Files: {files}")
    return kwargs

def get_test_writer_subagent():
    """Factory function to create the Test Writer Subagent."""
    logger.info("📝 Initializing Test Writer Subagent...")
    standards_content = _read_standards()
    base_prompt = get_inherited_prompt(TEST_WRITER_ROLE, TEST_WRITER_PROTOCOL, TEST_WRITER_RULES)
    final_prompt = f"{base_prompt}\n\n{standards_content}"
    return {
        "name": "test-writer-subagent",
        "description": "Writes and repairs tests for Java classes based on `TESTING_STANDARDS.md`.",
        "system_prompt": final_prompt,
        "tools": [inspect_java_class, submit_test_writer_output],
    }