from typing import Dict, Any
import time

from deepagents import create_deep_agent
from git_subagent.git_subagent import GIT_SUBAGENT
from test_writer_subagent.test_writer_subagent import TEST_WRITER_SUBAGENT
from coverage_subagent.coverage_subagent import COVERAGE_SUBAGENT
from build_subagent.build_subagent import BUILD_SUBAGENT

from shared_utils.prompt_utils import get_inherited_prompt
from shared_utils.model_utils import GEMINI_FLASH_3_PREVIEW_MODEL
from shared_utils.middleware_utils import get_agent_runtime

ORCHESTRATOR_ROLE = "You are a senior Java/Gradle QA Architect orchestrating work across specialized agents."

ORCHESTRATOR_PROTOCOL = """
PHASE 1: PREPARATION
1. **SETUP:** Use `git-subagent` to clone/checkout the repo. IMPORTANT: Clone into the current directory (.).

PHASE 2: BASELINE MEASUREMENT
1. **REPORT:** Use `build-subagent` to run the baseline coverage report.
2. **ANALYZE:** Use `coverage-subagent` to read the baseline metrics.

PHASE 3: BATCH IMPROVEMENT (Max 3 Batches)
1. **CANDIDATES:** Identify the top 3 target classes that need improvement.
2. **GENERATE:** Call `test-writer-subagent` for all 3 candidates SIMULTANEOUSLY. You MUST output 3 separate tool calls in the same response turn. Do NOT wait for one to finish before starting the next. Pass the EXACT class name to `inspect_java_class`.
3. **VERIFY:** Use `build-subagent` ONCE to verify the changes. Prefer targeted tests (e.g. `:module:test --tests ClassTest`) over full builds.
4. **MEASURE:** Use `coverage-subagent` with `target_classes` parameter (comma-separated) to verify improvements for the specific batch of candidates in one go.
"""

ORCHESTRATOR_RULES = """
- **ORCHESTRATION:** You manage specialized sub-agents. Delegate deep work to them.
- **PARALLELISM:** You are authorized and encouraged to run independent sub-agent tasks in parallel (e.g., generating tests for multiple classes simultaneously).
- **BATCHING:** In Phase 3, wait for all test generation tasks to complete before running the build.
- **METRICS:** Summarize timings and iterations in your final answer.
- **STOPPING:** Stop if target reached or stalled.

Final answer MUST be a raw JSON string (no markdown formatting) matching the following schema:
{
    "initial_coverage": float,
    "final_coverage": float,
    "coverage_delta": float,
    "classes_targeted": [str],
    "classes_improved": [str],
    "classes_failed": [str],
    "total_iterations": int,
    "duration_seconds": float,
    "termination_reason": str
}
"""

ORCHESTRATOR_SYSTEM_PROMPT = get_inherited_prompt(ORCHESTRATOR_ROLE, ORCHESTRATOR_PROTOCOL, ORCHESTRATOR_RULES)

# Sub-agents registry
SUBAGENTS = [
    GIT_SUBAGENT,
    TEST_WRITER_SUBAGENT,
    BUILD_SUBAGENT,
    COVERAGE_SUBAGENT
]

def get_orchestrator_agent(project_root: str):
    middleware, backend = get_agent_runtime(project_root)
    
    return create_deep_agent(
        model=GEMINI_FLASH_3_PREVIEW_MODEL,
        tools=[], 
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
        subagents=SUBAGENTS,
        middleware=middleware,
        backend=backend
    )