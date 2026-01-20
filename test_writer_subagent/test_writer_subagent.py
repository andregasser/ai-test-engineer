from pathlib import Path
import os
import time
import subprocess
from langchain_core.tools import tool
from shared_utils.prompt_utils import get_inherited_prompt
from shared_utils.schema_utils import TestWriterAgentOutput
from shared_utils.logger import get_logger
import json

logger = get_logger("test-writer-subagent")

TEST_WRITER_ROLE = "You are a Java/JUnit test generation agent. Your goal is to generate robust JUnit 5 tests to improve coverage."

# Updated Protocol: Focus strictly on generation. Quality review is now external.
TEST_WRITER_PROTOCOL = """
1. **CONTEXT:** Use `inspect_java_class` to get the production code and existing tests.
2. **ANALYSIS:** Analyze the logic and required test cases based on the **PROJECT TESTING STANDARDS**.
3. **ONE-SHOT GENERATION:** Generate the ENTIRE test class in a single response. Do not review your own work; the Reviewer Agent will handle that.
"""

TEST_WRITER_RULES = """
- **CRITICAL - NO PRODUCTION MODS:** You are STRICTLY FORBIDDEN from creating or modifying ANY file in `src/main/java`. You may ONLY write to `src/test/java`. Violating this rule is a critical failure.
- **EXISTING TESTS:** If `inspect_java_class` returns an existing test, preserve its useful parts. Do not duplicate test methods.
- **STANDARDS:** You must strictly follow the PROJECT TESTING STANDARDS section.
- **STRICT TAGGING:** Every single test method AND the test class itself MUST be annotated with `@Tag("ai-generated")`. This is mandatory.

**OUTPUT FORMAT:**
To finish your task, you **MUST** call the `submit_test_writer_output` tool. This is the only way to return your result. Refer to the tool's definition for the required arguments.
"""

def _read_standards(project_root: str) -> str:
    """Finds and reads the 'TESTING_STANDARDS.md' file."""
    try:
        root = Path(project_root)
        std_content = "No TESTING_STANDARDS.md found in project."
        
        # Try root first
        std_file = root / "TESTING_STANDARDS.md"
        if not std_file.exists():
            # Fallback: try to find it anywhere
            std_candidates = list(root.glob("**/TESTING_STANDARDS.md"))
            if std_candidates:
                std_file = std_candidates[0]
        
        if std_file.exists():
            std_content = std_file.read_text(encoding="utf-8")
            
        return f"### PROJECT TESTING STANDARDS (Source: {std_file}) ###\n{std_content}"
    except Exception as e:
        return f"Error reading standards: {str(e)}"

def _fast_find_file(root: Path, target_name: str) -> Path | None:
    """
    Fast file search using ripgrep (rg) if available, falling back to os.walk.
    """
    # 1. Try ripgrep (fastest)
    try:
        # rg --files --glob '**/target_name' --max-count 1 root
        # optimization: stop after first match
        cmd = ["rg", "--files", "--glob", f"**/{target_name}", str(root)]
        
        # Log the command for debugging performance
        logger.debug(f"Running rg command: {' '.join(cmd)}")
        
        t_start = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True)
        t_end = time.time()
        
        if result.returncode == 0 and result.stdout:
            paths = result.stdout.strip().split('\n')
            if paths:
                best_match = paths[0]
                # If multiple, prefer src/main
                for p in paths:
                    if "src/main/java" in p:
                        best_match = p
                        break
                logger.info(f"✅ rg found {target_name} in {t_end-t_start:.2f}s: {best_match}")
                return Path(best_match)
        else:
            logger.warning(f"⚠️ rg found nothing or failed (code {result.returncode}) for {target_name} in {t_end-t_start:.2f}s")
            
    except Exception as e:
        logger.warning(f"ripgrep failed, falling back to os.walk: {e}")

    # 2. Fallback: os.walk (slower)
    logger.info(f"🐢 Falling back to os.walk for {target_name}...")
    ignored_dirs = {'build', '.git', '.gradle', 'node_modules', 'target', 'dist', 'out'}
    
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories in-place
        dirnames[:] = [d for d in dirnames if d not in ignored_dirs]
        
        for f in filenames:
            if f == target_name:
                return Path(dirpath) / f
    return None

@tool
def inspect_java_class(class_name: str, project_root: str) -> str:
    """
    Efficiently locates and reads a Java class and its corresponding test class.
    """
    start_time = time.time()
    logger.info(f"🔍 Inspecting class: {class_name}")
    
    try:
        root = Path(project_root)
        
        # 1. Try Direct Resolution (O(1)) - Fastest
        # Convert com.example.Foo -> com/example/Foo.java
        rel_path = class_name.replace(".", "/") + ".java"
        
        # Standard Gradle/Maven layouts
        candidates = [
            root / "src/main/java" / rel_path,
            root / "src/test/java" / rel_path,
            # Handle multi-module by checking if root has modules? 
            # If project_root is repo root, we might not know the module dir.
            # But checking a few common depths is cheap.
        ]
        
        source_file = None
        for c in candidates:
            if c.exists():
                source_file = c
                logger.info(f"✅ Found class via direct path: {c}")
                break
        
        t1 = time.time()
        
        # 2. If Direct Resolution Failed, Search (O(N))
        if not source_file:
            simple_name = class_name.split(".")[-1]
            target_file_name = f"{simple_name}.java"
            source_file = _fast_find_file(root, target_file_name)
        
        if not source_file:
            return f"❌ Could not find Java class '{class_name}' in project."

        t2 = time.time()
        source_content = source_file.read_text(encoding="utf-8")
        t3 = time.time()
        
        # 3. Find/Predict Test Class
        test_file = None
        test_content = "No existing test file found."
        
        # Try fast deduction: swap src/main/java -> src/test/java
        src_path_str = str(source_file)
        if "src/main/java" in src_path_str:
            test_path_str = src_path_str.replace("src/main/java", "src/test/java").replace(".java", "Test.java")
            test_candidate = Path(test_path_str)
            if test_candidate.exists():
                test_file = test_candidate
        
        # If deduction failed, try fast search for *Test.java
        if not test_file:
            simple_name = class_name.split(".")[-1]
            test_name = simple_name + "Test.java"
            test_file = _fast_find_file(root, test_name)

        t4 = time.time()
        if test_file:
            test_content = test_file.read_text(encoding="utf-8")
        
        t_end = time.time()
        
        logger.info(f"⏱️  Timing: Direct/Search={t2-t1:.2f}s, ReadSrc={t3-t2:.2f}s, FindTest={t4-t3:.2f}s, Total={t_end-start_time:.2f}s")
        
        # 4. Construct Output
        output = []
        output.append(f"MODULE: {source_file.parent}")
        output.append(f"TARGET CLASS PATH: {source_file}")
        output.append("-" * 40)
        output.append(source_content)
        output.append("-" * 40)
        output.append(f"EXISTING TEST PATH: {test_file if test_file else 'N/A'}")
        output.append("-" * 40)
        output.append(test_content)
        
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

def get_test_writer_subagent(project_root: str):
    """
    Factory function to create the Test Writer Subagent.
    Injects the TESTING_STANDARDS.md content directly into the system prompt.
    """
    logger.info("📝 Initializing Test Writer Subagent...")
    standards_content = _read_standards(project_root)
    
    # Combine inherited prompt with injected standards
    base_prompt = get_inherited_prompt(TEST_WRITER_ROLE, TEST_WRITER_PROTOCOL, TEST_WRITER_RULES)
    final_prompt = f"{base_prompt}\n\n{standards_content}"
    
    return {
        "name": "test-writer-subagent",
        "description": "Writes and repairs JUnit 5 tests for Java classes.",
        "system_prompt": final_prompt,
        "tools": [inspect_java_class, submit_test_writer_output],
    }
