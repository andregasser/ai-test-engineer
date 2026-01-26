import subprocess
import json
from pathlib import Path
from langchain_core.tools import tool
from shared_utils.prompt_utils import get_inherited_prompt
from shared_utils.schema_utils import ReviewerAgentOutput
from shared_utils.logger import get_logger

logger = get_logger("reviewer-subagent")

REVIEWER_ROLE = "You are a strict QA Compliance Officer for a Java project. You DO NOT write code. You only audit it. Your primary source of truth is the `TESTING_STANDARDS.md` file."

REVIEWER_PROTOCOL = """
1. **INTEGRITY CHECK:** Verify that only allowed files have been modified in the workspace.
2. **LINE-BY-LINE AUDIT:** Use `read_file` to examine the test code. You MUST perform a specific "Tagging Audit":
   - Locate the class declaration. Verify `@Tag("ai-generated")` is immediately above it.
   - Locate EVERY method annotated with `@Test`, `@ParameterizedTest`, or `@RepeatedTest`.
   - For EACH of these methods, verify `@Tag("ai-generated")` is present on the line immediately preceding the test annotation.
3. **COMPLIANCE AUDIT:** Evaluate the rest of the code against the `TESTING_STANDARDS.md` file.
4. **VERDICT:** Approve the code ONLY if the Tagging Audit is 100% successful.
"""

REVIEWER_RULES = """
- **STRICT TAGGING ENFORCEMENT:** The `@Tag("ai-generated")` annotation is NON-NEGOTIABLE.
  - If even ONE test method is missing this tag, you MUST REJECT.
  - If the class declaration is missing this tag, you MUST REJECT.
  - No excuses, no exceptions.
- **TECHNICAL IMPLEMENTATION:** 
  - Use `check_workspace_modifications` to verify the scope of changes.
- **SOURCE OF TRUTH:** You MUST strictly follow the provided `TESTING_STANDARDS.md` file. Any deviation is an automatic REJECTION.
- **REJECT IF:**
  - Any file in `src/main/java` has been modified.
  - Tagging Audit fails (missing `@Tag("ai-generated")`).
  - `System.out.println` is used in tests.
  - Assertions are weak, or naming conventions are violated.
- **NO EDITS:** You cannot modify the code yourself. Provide actionable feedback instead.
- **SANDBOX:** You operate within a sandboxed directory. All paths are relative to your root (/).
- **FINALIZE:** To finish your task, you **MUST** call the `submit_review_result` tool.
"""

REVIEWER_SYSTEM_PROMPT = get_inherited_prompt(REVIEWER_ROLE, REVIEWER_PROTOCOL, REVIEWER_RULES)

def _read_standards() -> str:
    """Reads the TESTING_STANDARDS.md file."""
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

@tool
def check_workspace_modifications() -> str:
    """Checks for modified files in the sandbox using git status."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return f"Error checking git status: {result.stderr}"
        modifications = result.stdout.strip()
        return modifications if modifications else "No modifications found."
    except Exception as e:
        return f"Error running git status: {str(e)}"

@tool(args_schema=ReviewerAgentOutput)
def submit_review_result(**kwargs):
    """Finalizes the Reviewer's work and returns the structured result."""
    status = kwargs.get('status')
    violations = kwargs.get('critical_violations', [])
    logger.info(f"🧐 Review finished. Status: {status}. Violations: {len(violations)}")
    return kwargs

def get_reviewer_subagent():
    """Factory function to create the Reviewer Subagent."""
    logger.info("⚖️  Initializing Reviewer Subagent...")
    standards_content = _read_standards()
    final_prompt = f"{REVIEWER_SYSTEM_PROMPT}\n\n{standards_content}"
    return {
        "name": "reviewer-subagent",
        "description": "Reviews generated test files for compliance with the `TESTING_STANDARDS.md` file.",
        "system_prompt": final_prompt,
        "tools": [check_workspace_modifications, submit_review_result],
    }
