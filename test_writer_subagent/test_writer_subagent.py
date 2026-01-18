from pathlib import Path
from shared_utils.prompt_utils import get_inherited_prompt

# Load standards content dynamically to save tool calls
try:
    STANDARDS_CONTENT = Path("TESTING_STANDARDS.md").read_text()
except Exception:
    STANDARDS_CONTENT = "Standards file not found."

TEST_WRITER_ROLE = "You are a Java/JUnit test generation agent. Your goal is to generate robust JUnit 5 tests to improve coverage."

TEST_WRITER_PROTOCOL = """
1. **STANDARDS:** Strict adherence to the # TESTING STANDARDS section below is mandatory.
2. **DISCOVERY:** Use `glob` (e.g., `glob("**/ClassName.java")`) to locate production code if not in context.
3. **ANALYSIS:** Read the code and identify all methods, branches, and edge cases.
4. **ONE-SHOT GENERATION:** Generate the ENTIRE test class in ONE operation for maximum coverage.
"""

TEST_WRITER_RULES = f"""
- **NO PRODUCTION MODS:** Only write files under src/test/java.

# TESTING STANDARDS
{STANDARDS_CONTENT}
"""

TEST_WRITER_SYSTEM_PROMPT = get_inherited_prompt(TEST_WRITER_ROLE, TEST_WRITER_PROTOCOL, TEST_WRITER_RULES)

TEST_WRITER_SUBAGENT = {
    "name": "test-writer-subagent",
    "description": "Writes and repairs JUnit 5 tests for Java classes.",
    "system_prompt": TEST_WRITER_SYSTEM_PROMPT,
    "tools": [],
}
