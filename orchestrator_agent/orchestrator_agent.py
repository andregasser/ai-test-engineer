from typing import Dict, Any
import time
import json
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

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
Execute the following loop up to 3 times:
1. **CANDIDATES:** Use coverage data to select the top 3 worst classes (prioritize services/acm-service).
2. **GENERATE:** Call `test-writer-subagent` for all 3 candidates SIMULTANEOUSLY using their EXACT Fully Qualified Class Names (FQN). You MUST output 3 separate tool calls in the same response turn.
3. **VERIFY:** Wait for all 3 writers to finish. Run ONE targeted build/test command that covers ONLY the modified classes (e.g. `:module:test --tests "com.example.ClassATest,com.example.ClassBTest"`). Do NOT run full module tests if possible.
4. **MEASURE:** Run `coverage-subagent` with `target_classes` set to the comma-separated list of the 3 classes.
5. **DECIDE:** Record per-class improvement. If target met or stalled, stop. Else continue to next batch.
"""

ORCHESTRATOR_RULES = """
- **ORCHESTRATION:** You manage specialized sub-agents. Delegate deep work to them.
- **PARALLELISM:** You are authorized and encouraged to run independent sub-agent tasks in parallel.
  - **MANDATORY:** Whenever generating tests for multiple independent classes, you **MUST** output multiple `test-writer-subagent` tool calls in the SAME response turn. Do not sequentialize them.
- **BATCHING:** In Phase 3, wait for all test generation tasks to complete before running the build. **DO NOT** run verification for individual classes immediately after generation. Run ONE consolidated build per batch.
- **METRICS:** Summarize timings and iterations in your final answer.
- **STOPPING CRITERIA (STRICT):**
  1. **SUCCESS:** Stop if `final_coverage` >= `target_coverage` (as defined in input). Set termination_reason="target_met".
  2. **STALLED:** Stop if:
     - Coverage does not increase by at least 0.01 (1%) across two consecutive measurement cycles.
     - OR The last 2 builds fail with the same error.
     - Set termination_reason="stalled_no_progress".
  3. **LIMIT:** Never perform more than 3 improvement batches. If you complete Batch 3 and target is not met, stop immediately. Set termination_reason="max_batches_reached".

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

def get_orchestrator_agent(project_root: str):
    middleware, backend = get_agent_runtime(project_root)
    
    agent = create_deep_agent(
        model=GEMINI_FLASH_3_PREVIEW_MODEL,
        tools=[], 
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
        subagents=SUBAGENTS,
        middleware=middleware,
        backend=backend
    )
    
    return agent.with_fallbacks([RunnableLambda(handle_orchestrator_error)])