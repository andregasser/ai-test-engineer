from langchain_core.tools import tool
from shared_utils.prompt_utils import get_inherited_prompt
from shared_utils.schema_utils import BuildAgentOutput
from shared_utils.logger import get_logger

logger = get_logger("build-subagent")

BUILD_ROLE = "You are a Build & CI Specialist Agent. Your job is to execute builds and tests for a Java/Gradle project."

BUILD_PROTOCOL = """
1. **EXECUTION:** Trigger the build or test suite for the requested scope.
2. **DIAGNOSIS:** Monitor the output to determine success or failure.
3. **ANALYSIS:** If the build fails, identify the root cause from the logs.
4. **REPORTING:** Provide a structured summary of the results, including failing tests or compiler errors.
"""

BUILD_RULES = """
- **TECHNICAL IMPLEMENTATION:** You MUST use the `execute` tool to run shell commands (specifically `./gradlew` or `gradle`).
- **COMMAND WHITELIST:** ONLY the following prefixes are allowed for the `execute` tool: `gradle `, `./gradlew `, `test`, `git `, `chmod +x gradlew`. All others will fail.
- **COMPILER ERROR PRIORITIZATION:** In failed build logs, focus exclusively on the FIRST compilation error. Subsequent errors are often 'noise'.
- **TEST RESULT SUMMARY:** When a test task fails, extract and summarize the specific test method name and the assertion failure message (e.g., 'Expected X but was Y').
- **NARROW TASKS:** Always target the specific module tasks (e.g. `:module:test`) instead of root-level ones to save time.
- **SKIP CLEAN:** Avoid using 'clean' for quick iterations unless stale artifacts are suspected.
- **SANDBOX:** You operate within a sandboxed directory. All paths are relative to your root (/).
- **FINALIZE:** To finish your task, you **MUST** call the `submit_build_output` tool.
"""

BUILD_SYSTEM_PROMPT = get_inherited_prompt(BUILD_ROLE, BUILD_PROTOCOL, BUILD_RULES)

@tool(args_schema=BuildAgentOutput)
def submit_build_output(**kwargs):
    """Finalizes the Build agent's work."""
    logger.info(f"🏗️  Build finished. Status: {kwargs.get('status')}")
    return kwargs

def get_build_subagent():
    """Factory function to create the Build Subagent."""
    logger.info("🔨 Initializing Build Subagent...")
    return {
        "name": "build-subagent",
        "description": "Runs Gradle builds and tests to verify code changes.",
        "system_prompt": BUILD_SYSTEM_PROMPT,
        "tools": [submit_build_output],
    }
