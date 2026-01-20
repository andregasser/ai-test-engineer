from pathlib import Path
from langchain_core.tools import tool
from shared_utils.prompt_utils import get_inherited_prompt
from shared_utils.schema_utils import ReviewerAgentOutput

REVIEWER_ROLE = "You are a strict QA Compliance Officer for a Java project. You DO NOT write code. You only audit it."

REVIEWER_PROTOCOL = """
1. **INPUT:** You will receive the file path of a newly generated test class.
2. **INSPECT:** Use the `read_file` tool to examine the code.
3. **AUDIT:** Compare the code strictly against the **PROJECT TESTING STANDARDS** provided below.
4. **DECIDE:** Approve or Reject based on compliance.
"""

REVIEWER_RULES = """
- **STRICT ENFORCEMENT:** You must REJECT the file if:
  - The mandatory `@Tag(\"ai-generated\")` annotation is missing from the class OR any test method.
  - Test methods use `System.out.println` (forbidden).
  - Naming conventions from standards are violated.
  - Assertions are weak or missing.
- **NO EDITS:** You cannot change the code. You can only provide feedback.
- **FEEDBACK:** Your feedback must be actionable for the Test Writer (e.g., "Add @Tag('ai-generated') to method testX").

**OUTPUT FORMAT:**
To finish your task, you **MUST** call the `submit_review_result` tool. This is the only way to return your result. Refer to the tool's definition for the required arguments.
"""

def _read_standards(project_root: str) -> str:
    """Reads the TESTING_STANDARDS.md file."""
    try:
        root = Path(project_root)
        std_content = "No TESTING_STANDARDS.md found in project."
        std_file = root / "TESTING_STANDARDS.md"
        if not std_file.exists():
            std_candidates = list(root.glob("**/TESTING_STANDARDS.md"))
            if std_candidates:
                std_file = std_candidates[0]
        
        if std_file.exists():
            std_content = std_file.read_text(encoding="utf-8")
        return f"### PROJECT TESTING STANDARDS (Source: {std_file}) ###\n{std_content}"
    except Exception as e:
        return f"Error reading standards: {str(e)}"

from shared_utils.logger import get_logger

logger = get_logger("reviewer-subagent")

@tool(args_schema=ReviewerAgentOutput)
def submit_review_result(**kwargs):
    """Finalizes the Reviewer's work and returns the structured result."""
    status = kwargs.get('status')
    violations = kwargs.get('critical_violations', [])
    logger.info(f"🧐 Review finished. Status: {status}. Violations: {len(violations)}")
    if violations:
        logger.info(f"    ⚠️  Violations: {violations}")
    return kwargs

def get_reviewer_subagent(project_root: str):
    """Factory function to create the Reviewer Subagent with injected standards."""
    logger.info("⚖️  Initializing Reviewer Subagent...")
    standards_content = _read_standards(project_root)
    
    base_prompt = get_inherited_prompt(REVIEWER_ROLE, REVIEWER_PROTOCOL, REVIEWER_RULES)
    final_prompt = f"{base_prompt}\n\n{standards_content}"
    
    return {
        "name": "reviewer-subagent",
        "description": "Reviews generated test files for compliance with testing standards.",
        "system_prompt": final_prompt,
        "tools": [submit_review_result],
    }
