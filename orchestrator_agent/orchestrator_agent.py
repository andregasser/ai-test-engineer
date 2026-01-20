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
from shared_utils.middleware_utils import get_agent_runtime

ORCHESTRATOR_ROLE = "You are a senior Java/Gradle QA Architect orchestrating work across specialized agents."

ORCHESTRATOR_PROTOCOL = """
PHASE 1: PREPARATION
1. **SETUP:** Use `git-subagent` to clone/checkout the repo. IMPORTANT: Clone into the current directory (.).

PHASE 2: BASELINE MEASUREMENT
1. **REPORT:** Use `build-subagent` to run the baseline coverage report.
2. **ANALYZE:** Use `coverage-subagent` to read the baseline metrics. IMPORTANT: You MUST pass the `target_modules`, `target_packages`, and `target_classes` from your input to `read_coverage_report` to ensure the analysis is scoped correctly.

PHASE 3: BATCH IMPROVEMENT (Max 3 Batches)
Execute the following loop up to 3 times:
1. **CANDIDATES:** Use coverage data to select the top 3 worst classes (prioritize services/acm-service).
2. **GENERATE & REVIEW LOOP:**
   For each candidate (can be parallelized):
   a. **GENERATE:** Call `test-writer-subagent` (using FQN).
   b. **REVIEW:** Call `reviewer-subagent` passing the path of the generated test file.
   c. **DECIDE:**
      - If `status="approved"`: Proceed.
      - If `status="rejected"`: Call `test-writer-subagent` again with the `constructive_feedback`.
      - **LIMIT:** Retry step (a) at most 2 times. If still rejected, mark as failed and skip.
3. **VERIFY:** Wait for all approved tests. Run ONE targeted build/test command that covers ONLY the modified classes.
4. **MEASURE:** Run `coverage-subagent` with `target_classes`.
5. **DECIDE:** Record improvement. Stop if target met.
"""

ORCHESTRATOR_RULES = """
- **ORCHESTRATION:** You manage specialized sub-agents. Delegate deep work to them.
- **PARALLELISM:** You are authorized and encouraged to run independent sub-agent tasks in parallel.
  - **MANDATORY:** Whenever generating tests for multiple independent classes, you **MUST** output multiple `test-writer-subagent` tool calls in the SAME response turn. Do not sequentialize them.
- **BATCHING:** In Phase 3, wait for all test generation tasks to complete before running the build. **DO NOT** run verification for individual classes immediately after generation. Run ONE consolidated build per batch.
- **METRICS:** Summarize timings and iterations in your final answer.
- **RESILIENCE & ERROR HANDLING:**
  - **BUILD FAILURES:** If `build-subagent` returns `status="failure"`, you MUST retry exactly ONCE with the `--info` flag to gather more details. If it fails a second time, consider it a hard failure for that batch.
  - **GENERATION FAILURES:** If `test-writer-subagent` fails for a specific class (returns `status="failure"`), do NOT retry. Mark that class as failed in your internal tracking, add it to `classes_failed`, and proceed immediately with the remaining candidates. Do not let one failure stall the entire batch.
  - **REVIEW LOOPS:** Strictly limit the "Fix-Review" loop to 2 iterations per class to avoid infinite loops. If a test is rejected 3 times, discard it (delete the file using `run_shell_command`) and mark the class as failed.
- **STOPPING CRITERIA (STRICT):**
  1. **SUCCESS:** Stop if `final_coverage` >= `target_coverage` (as defined in input). Set termination_reason="target_met".
  2. **STALLED:** Stop if:
     - Coverage does not increase by at least 0.01 (1%) across two consecutive measurement cycles.
     - OR The last 2 builds fail with the same error.
     - Set termination_reason="stalled_no_progress".
  3. **LIMIT:** Never perform more than 3 improvement batches. If you complete Batch 3 and target is not met, stop immediately. Set termination_reason="max_batches_reached".

**OUTPUT FORMAT:**
To finish your task, you **MUST** call the `submit_agent_report` tool. This is the only way to return your result. Refer to the tool's definition for the required arguments.
"""

ORCHESTRATOR_SYSTEM_PROMPT = get_inherited_prompt(ORCHESTRATOR_ROLE, ORCHESTRATOR_PROTOCOL, ORCHESTRATOR_RULES)

@tool(args_schema=AgentReport)
def submit_agent_report(**kwargs):
    """Finalizes the Orchestrator's work and returns the structured report."""
    logger.info("🏁 Orchestrator submitting final report.")
    return kwargs

def handle_orchestrator_error(input_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fallback handler that returns a graceful failure JSON when the agent crashes (e.g. LLM overload).
    """
    failure_data = {
        "initial_coverage": 0.0,
        "final_coverage": 0.0,
        "coverage_delta": 0.0,
        "classes_targeted": [],
        "classes_improved": [],
        "classes_failed": [],
        "total_iterations": 0,
        "duration_seconds": 0.0,
        "termination_reason": "model_overloaded"
    }
    
    # Ensure messages list exists
    messages = input_state.get("messages", [])
    if not isinstance(messages, list):
        messages = [messages] if messages else []
        
    # Append the failure message as an AIMessage, mimicking the agent's final response
    failure_message = AIMessage(content=json.dumps(failure_data))
    
    return {
        **input_state,
        "messages": messages + [failure_message]
    }

from shared_utils.logger import get_logger

logger = get_logger("orchestrator")

def get_orchestrator_agent(project_root: str):
    logger.info(f"🤖 Initializing Orchestrator Agent for project: {project_root}")
    middleware, backend = get_agent_runtime(project_root)
    
    # Dynamically create subagents
    subagents = [
        get_git_subagent(),
        get_test_writer_subagent(project_root),
        get_reviewer_subagent(project_root),
        get_build_subagent(),
        get_coverage_subagent()
    ]
    
    agent = create_deep_agent(
        model=GEMINI_FLASH_3_PREVIEW_MODEL,
        tools=[submit_agent_report], 
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
        subagents=subagents,
        middleware=middleware,
        backend=backend
    )
    
    return agent.with_fallbacks([RunnableLambda(handle_orchestrator_error)])
