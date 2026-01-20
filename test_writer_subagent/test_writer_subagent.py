from pathlib import Path
from langchain_core.tools import tool
from shared_utils.prompt_utils import get_inherited_prompt
from shared_utils.schema_utils import TestWriterAgentOutput
import json

TEST_WRITER_ROLE = "You are a Java/JUnit test generation agent. Your goal is to generate robust JUnit 5 tests to improve coverage."

# Updated Protocol: Focus strictly on generation. Quality review is now external.
TEST_WRITER_PROTOCOL = """
1. **CONTEXT:** Use `inspect_java_class` to get the production code and existing tests.
2. **ANALYSIS:** Analyze the logic and required test cases based on the **PROJECT TESTING STANDARDS**.
3. **ONE-SHOT GENERATION:** Generate the ENTIRE test class in a single response. Do not review your own work; the Reviewer Agent will handle that.
"""

TEST_WRITER_RULES = """
- **NO PRODUCTION MODS:** Only write files under src/test/java.
- **EXISTING TESTS:** If `inspect_java_class` returns an existing test, preserve its useful parts. Do not duplicate test methods.
- **STANDARDS:** You must strictly follow the PROJECT TESTING STANDARDS section.
- **STRICT TAGGING:** Every single test method AND the test class itself MUST be annotated with `@Tag("ai-generated")`. This is mandatory.

**OUTPUT FORMAT:**
To finish your task, you **MUST** call the `submit_test_writer_output` tool. This is the only way to return your result. Refer to the tool's definition for the required arguments.
"""

def _read_standards(project_root: str) -> str:
    """
    Finds and reads the 'TESTING_STANDARDS.md' file.
    """
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

@tool
def inspect_java_class(class_name: str, project_root: str) -> str:
    """
    Efficiently locates and reads a Java class and its corresponding test class.
    
    Args:
        class_name: The simple name (e.g. 'UserService') or fully qualified name (e.g. 'com.example.UserService') of the class.
        project_root: The root directory of the project.
        
    Returns:
        A formatted string containing:
        - Class File Path
        - Class Content
        - Test File Path (if found)
        - Test Content (if found)
    """
    try:
        root = Path(project_root)
        
        # 1. Determine search pattern
        if "." in class_name:
            # Fully qualified - turn com.example.Foo into **/com/example/Foo.java
            path_part = class_name.replace(".", "/") + ".java"
            pattern = f"**/{path_part}"
        else:
            # Simple name - **/Foo.java
            pattern = f"**/{class_name}.java"
            
        # 2. Find Production Class
        # Exclude src/test/java to ensure we find the source code, not the test itself if names overlap weirdly
        candidates = list(root.glob(pattern))
        
        # Filter for src/main/java if multiple found, or just pick the first that isn't in build/
        source_file = None
        for c in candidates:
            if "src/main/java" in str(c):
                source_file = c
                break
        if not source_file and candidates:
            source_file = candidates[0]
            
        if not source_file:
            return f"❌ Could not find Java class '{class_name}' in project."

        source_content = source_file.read_text(encoding="utf-8")
        
        # 3. Find/Predict Test Class
        # Assumption: Test class is ClassNameTest.java in src/test/java with same package structure
        test_file = None
        test_content = "No existing test file found."
        
        # Try to deduce test path from source path
        # src/main/java/.../Foo.java -> src/test/java/.../FooTest.java
        src_path_str = str(source_file)
        if "src/main/java" in src_path_str:
            test_path_str = src_path_str.replace("src/main/java", "src/test/java").replace(".java", "Test.java")
            test_candidate = Path(test_path_str)
            if test_candidate.exists():
                test_file = test_candidate
        
        # If deduction failed, try searching
        if not test_file:
            test_name = source_file.stem + "Test.java"
            test_candidates = list(root.glob(f"**/{test_name}"))
            if test_candidates:
                test_file = test_candidates[0]

        if test_file:
            test_content = test_file.read_text(encoding="utf-8")
        
        # 4. Construct Output
        output = []
        output.append(f"MODULE: {source_file.parent}") # Rough module indication
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
    return kwargs

def get_test_writer_subagent(project_root: str):
    """
    Factory function to create the Test Writer Subagent.
    Injects the TESTING_STANDARDS.md content directly into the system prompt.
    """
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