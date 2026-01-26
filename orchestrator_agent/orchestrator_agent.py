from typing import Dict, Any
import json
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from shared_utils.schema_utils import AgentReport

from deepagents import create_deep_agent
from git_subagent.git_subagent import get_git_subagent
from test_writer_subagent.test_writer_subagent import get_test_writer_subagent
from coverage_subagent.coverage_subagent import get_coverage_subagent
from build_subagent.build_subagent import get_build_subagent
from reviewer_subagent.reviewer_subagent import get_reviewer_subagent

from shared_utils.prompt_utils import get_inherited_prompt
from shared_utils.model_utils import GEMINI_FLASH_3_PREVIEW_MODEL
from shared_utils.logger import get_logger

logger = get_logger("orchestrator")

ORCHESTRATOR_ROLE = "You are a senior Java/Gradle QA Architect orchestrating work across specialized agents."

ORCHESTRATOR_PROTOCOL = """
PHASE 1: PREPARATION
1. **SETUP:** Prepare the repository and ensure the project is on the correct branch.

PHASE 2: BASELINE MEASUREMENT
1. **MEASURE:** Establish the initial coverage baseline and identify gaps in the target scope.

PHASE 3: BATCH IMPROVEMENT (Max 3 Batches)
Execute the following loop up to 3 times:
1. **SELECTION:** Identify high-priority candidate classes for improvement.
2. **GENERATION & REVIEW:** Coordinate the creation and quality audit of new tests.
3. **VERIFICATION:** Validate the new tests against the build system.
4. **MEASUREMENT:** Re-calculate coverage to record improvements.

PHASE 4: FINALIZATION
1. **REPORTING:** Consolidate all metrics and results into a final report.
"""

ORCHESTRATOR_RULES = """
- **TECHNICAL IMPLEMENTATION:** 
  - Delegate specialized work to sub-agents (Git, Test Writer, Reviewer, Build, Coverage) using the `task` tool.
  - You MUST use the `execute` tool for any direct shell operations.
- **GIT SETUP GUARDRAILS:**
  - Robustly handle branch setup via the `git-subagent`. 
  - If the requested branch fails to check out but the repository is usable (e.g. on `dev` or `main`), you MAY proceed with test generation on the current branch. Report this clearly in the final report.
  - If setup fails completely (cannot clone), STOP and report a hard failure.
- **COVERAGE TARGETS:** Respect the `target_coverage` provided in your input. When delegating to the `test-writer-subagent`, explicitly state that the goal is to reach this target, NOT necessarily 100%.
- **COMMAND WHITELIST:** ONLY the following prefixes are allowed for the `execute` tool: `test`, `git `, `gradle `, `./gradlew `, `chmod +x gradlew`. All others will fail.
- **PARALLELISM:** MANDATORY: Trigger multiple `test-writer-subagent` calls in ONE turn for independent classes.
- **BATCHING:** Execute ONE consolidated build per batch after all test generation/review steps are complete.
- **RESILIENCE:** If a build fails, retry once with the `--info` flag.
- **FIX-REVIEW LOOP:** Limit the "Fix-Review" cycle to 2 iterations per class. If still rejected, discard the test using the `execute` tool (to `rm`).
- **STOPPING CRITERIA:** Stop if the target is met, if progress stalls (delta < 1%), or after 3 batches.
- **SANDBOX:** You operate within a sandboxed directory. All paths are relative to your root (/).
- **FINALIZE:** To finish your task, you **MUST** call the `submit_agent_report` tool. This is the only way to return your result.
"""

ORCHESTRATOR_SYSTEM_PROMPT = get_inherited_prompt(ORCHESTRATOR_ROLE, ORCHESTRATOR_PROTOCOL, ORCHESTRATOR_RULES)

@tool(args_schema=AgentReport)
def submit_agent_report(**kwargs):
    """Finalizes the Orchestrator's work and returns the structured report."""
    initial = kwargs.get('initial_coverage', 0.0)
    final = kwargs.get('final_coverage', 0.0)
    
    if initial > 1.0: initial /= 100.0
    if final > 1.0: final /= 100.0
    
    delta = final - initial
    kwargs['initial_coverage'] = initial
    kwargs['final_coverage'] = final
    kwargs['coverage_delta'] = delta
    
    logger.info(f"🏁 Orchestrator finished. Coverage: {initial:.2%} -> {final:.2%} (Delta: {delta:+.2%})")
    return kwargs

def handle_orchestrator_error(input_state: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback error handler."""
    failure_data = {
        "initial_coverage": 0.0, "final_coverage": 0.0, "coverage_delta": 0.0,
        "classes_targeted": [], "classes_improved": [], "classes_failed": [],
        "total_iterations": 0, "duration_seconds": 0.0, "termination_reason": "model_overloaded"
    }
    messages = input_state.get("messages", [])
    return {**input_state, "messages": messages + [AIMessage(content=json.dumps(failure_data))]}

def get_orchestrator_agent(project_root: str):
    logger.info(f"🤖 Initializing Orchestrator Agent for project: {project_root}")
    
    # Dynamically create subagents
    subagents = [
        get_git_subagent(),
        get_test_writer_subagent(),
        get_reviewer_subagent(),
        get_build_subagent(),
        get_coverage_subagent()
    ]
    
    agent = create_deep_agent(
        model=GEMINI_FLASH_3_PREVIEW_MODEL,
        tools=[submit_agent_report], 
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
        subagents=subagents,
        backend=lambda rt: HostSandboxBackend(root_dir=project_root)
    )
    
    return agent.with_fallbacks([RunnableLambda(handle_orchestrator_error)])