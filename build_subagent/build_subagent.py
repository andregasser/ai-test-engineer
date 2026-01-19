from langchain_core.tools import tool
from shared_utils.prompt_utils import get_inherited_prompt
from shared_utils.schema_utils import BuildAgentOutput

BUILD_ROLE = "You are a Build & CI Specialist Agent. Your job is to execute builds and tests for a Java/Gradle project."

BUILD_PROTOCOL = """
1. Use the `shell` tool to run `./gradlew` commands.
2. Execute the narrowest possible Gradle task(s) that validate the required changes.
3. Provide the relevant success/fail status and error logs if failed.
"""

BUILD_RULES = """
- **COMPILER ERROR PRIORITIZATION:** In failed build logs, focus exclusively on the FIRST compilation error. Subsequent errors are often 'noise' caused by the first failure.
- **TEST RESULT SUMMARY:** When a test task fails, don't just return the log. Extract and summarize the specific test method name and the assertion failure message (e.g., 'Expected X but was Y').
- **NARROW GRADLE TASKS:** Use specific module tasks (e.g. `:module:test`) instead of root-level ones.
- **SKIP CLEAN:** Avoid using 'clean' for quick iterations unless stale artifacts are suspected.
- **OUTPUT FORMAT:** To finish your task, you **MUST** call the `submit_build_output` tool. This is the only way to return your result. Refer to the tool's definition for the required arguments.
"""

BUILD_SYSTEM_PROMPT = get_inherited_prompt(BUILD_ROLE, BUILD_PROTOCOL, BUILD_RULES)

@tool(args_schema=BuildAgentOutput)
def submit_build_output(**kwargs):
    """Finalizes the Build agent's work and returns the structured result."""
    return kwargs

def get_build_subagent():
    """Factory function to create the Build Subagent."""
    return {
        "name": "build-subagent",
        "description": "Runs Gradle builds and tests to verify code changes.",
        "system_prompt": BUILD_SYSTEM_PROMPT,
        "tools": [submit_build_output],
    }