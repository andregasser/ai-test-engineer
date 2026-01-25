from dotenv import load_dotenv

load_dotenv()

import langchain
import os
import config
import time
import argparse
import json
from orchestrator_agent.orchestrator_agent import get_orchestrator_agent
from shared_utils.logger import get_logger

logger = get_logger("runner")

langchain.debug = True


def run_coverage_optimization(repo_url: str, branch: str | None, target_coverage: float,
                              target_modules: list[str] = None,
                              target_packages: list[str] = None,
                              target_classes: list[str] = None,
                              test_type: str = "Unit Tests"):
    # 1. Determine Project Path
    repo_name = repo_url.split("/")[-1].replace(".git", "")
    project_path = os.path.join(config.WORKSPACE_DIR, repo_name)

    # Ensure the directory exists so the backend can initialize
    os.makedirs(project_path, exist_ok=True)

    # 2. Initialize Agent
    orchestrator_agent = get_orchestrator_agent(project_path)

    # Build a descriptive instruction for the orchestrator
    instruction = f"Improve coverage for {repo_url} on branch {branch} to {target_coverage}"

    if target_modules:
        instruction += f"\n- TARGET MODULES: {', '.join(target_modules)}"
    if target_packages:
        instruction += f"\n- TARGET PACKAGES: {', '.join(target_packages)}"
    if target_classes:
        instruction += f"\n- TARGET CLASSES: {', '.join(target_classes)}"

    instruction += f"\n- REQUIRED TEST TYPE: {test_type}"
    instruction += "\n- IMPORTANT: Strictly follow the standards in TESTING_STANDARDS.md."

    max_retries = 3
    retry_delay = 60  # seconds

    for attempt in range(max_retries):
        try:
            result = orchestrator_agent.invoke(
                {
                    "messages": [("user", instruction)],
                    "repo_url": repo_url,
                    "branch": branch,
                    "target_coverage": target_coverage,
                    "target_modules": target_modules,
                    "target_packages": target_packages,
                    "target_classes": target_classes,
                    "test_type": test_type,
                },
                config={"recursion_limit": 500}
            )

            # Check for specific termination reason in the output
            if result and "messages" in result and result["messages"]:
                last_content = result["messages"][-1].content
                # Simple string check to avoid full parse overhead inside the loop, 
                # but could use json.loads if preferred for robustness.
                if '"termination_reason": "model_overloaded"' in last_content:
                    if attempt < max_retries - 1:
                        logger.warning(f"⚠️  Model overloaded. Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                        continue
            
            return result

        except Exception as e:
            # Optional: Catch specific transport errors here if they bubble up
            logger.error(f"❌ An error occurred during execution: {e}")
            if attempt < max_retries - 1:
                 logger.info(f"🔄 Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                 time.sleep(retry_delay)
            else:
                 raise e
    
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Test Engineer - Coverage Optimization Runner")

    parser.add_argument("--repo-url", required=True, help="SSH or HTTP URL of the git repository.")
    parser.add_argument("--branch", required=False, help="Specific branch to work on (optional).")
    parser.add_argument("--target-coverage", type=float, default=0.80, help="Target coverage percentage (0.0 to 1.0). Default: 0.80")
    
    parser.add_argument("--target-modules", nargs="*", help="List of specific modules to target (space separated).")
    parser.add_argument("--target-packages", nargs="*", help="List of specific packages to target (space separated).")
    parser.add_argument("--target-classes", nargs="*", help="List of specific fully qualified class names to target (space separated).")
    
    parser.add_argument("--test-type", default="Unit Tests", choices=["Unit Tests", "Integration Tests", "Both"], 
                        help="Type of tests to generate. Default: 'Unit Tests'")

    args = parser.parse_args()

    # --- CONFIGURATION FROM ARGS ---
    REPO_URL = args.repo_url
    BRANCH = args.branch
    TARGET_COVERAGE = args.target_coverage
    TARGET_MODULES = args.target_modules
    TARGET_PACKAGES = args.target_packages
    TARGET_CLASSES = args.target_classes
    TEST_TYPE = args.test_type
    # -------------------------------

    logger.info(f"🚀 Starting Coverage Optimization for {REPO_URL}")
    logger.info(f"🎯 Target Coverage: {TARGET_COVERAGE}")
    if BRANCH:
        logger.info(f"🌿 Branch: {BRANCH}")
    
    result = run_coverage_optimization(
        repo_url=REPO_URL,
        branch=BRANCH,
        target_coverage=TARGET_COVERAGE,
        target_modules=TARGET_MODULES,
        target_packages=TARGET_PACKAGES,
        target_classes=TARGET_CLASSES,
        test_type=TEST_TYPE
    )

    # Process the output
    try:
        final_output = None
        # Iterate backwards to find the final report
        for msg in reversed(result["messages"]):
            # Case 1: ToolMessage from submit_agent_report
            if msg.type == "tool" and msg.name == "submit_agent_report":
                final_output = msg.content
                break
            # Case 2: AIMessage containing the JSON directly (fallback)
            if msg.type == "ai" and isinstance(msg.content, str) and "termination_reason" in msg.content:
                final_output = msg.content
                break
        
        if not final_output:
            # Fallback: Just take the last string content we can find
            for msg in reversed(result["messages"]):
                if isinstance(msg.content, str) and msg.content.strip():
                    final_output = msg.content
                    break
        
        if not final_output:
             raise ValueError("No valid output content found in messages.")

        # Ensure final_output is a string before string manipulation
        if not isinstance(final_output, str):
            final_output = json.dumps(final_output)

        # Attempt to clean up potential markdown formatting if the model slipped
        cleaned_output = final_output.replace("```json", "").replace("```", "").strip()
        report_data = json.loads(cleaned_output)
        
        logger.info("\n" + "=" * 50)
        logger.info("📊 FINAL AGENT REPORT")
        logger.info("=" * 50)
        logger.info(json.dumps(report_data, indent=4))
        logger.info("=" * 50)

        # Save to file
        with open("agent_report.json", "w") as f:
            json.dump(report_data, f, indent=4)
        logger.info("✅ Report saved to agent_report.json")

    except json.JSONDecodeError:
        logger.warning("\n⚠️  Could not parse JSON report. Raw output:")
        logger.warning(final_output)
    except Exception as e:
        logger.error(f"\n❌ Error processing report: {e}")
        # print("Raw output:")
        # print(result["messages"][-1].content) # Unsafe
        logger.error(f"Last message content: {result['messages'][-1].content}")