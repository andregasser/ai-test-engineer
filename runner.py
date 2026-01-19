from dotenv import load_dotenv

load_dotenv()

import langchain
import os
import config
from orchestrator_agent.orchestrator_agent import get_orchestrator_agent

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
    return result


if __name__ == "__main__":
    import json

    # --- CONFIGURATION SECTION ---
    # Repo details
    REPO_URL = "ssh://git@code.swisscom.com:2222/swisscom/tsp/my-ai/backend/myai-integration-backend.git"
    BRANCH = "feature/acm-service-ai-tests-2026-01-18"
    TARGET_COVERAGE = 1.00

    # Scope control:
    # List of module paths or None
    # Example: (e.g., ["fancy-modules/my-module"])
    TARGET_MODULES = ["services/acm-service"]

    # List of package names or None
    # Exmaple: ["com.foo.bar"]
    TARGET_PACKAGES = None

    # List of specific fully qualified class names to target or None
    # Example: ["com.foo.bar.MyCustomService"]
    TARGET_CLASSES = None

    # Type control: "Unit Tests", "Integration Tests", or "Both"
    TEST_TYPE = "Both"
    # -----------------------------

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
        final_output = result["messages"][-1].content
        # Attempt to clean up potential markdown formatting if the model slipped
        cleaned_output = final_output.replace("```json", "").replace("```", "").strip()
        report_data = json.loads(cleaned_output)
        print("\n" + "=" * 50)
        print("📊 FINAL AGENT REPORT")
        print("=" * 50)
        print(json.dumps(report_data, indent=4))
        print("=" * 50)

        # Save to file
        with open("agent_report.json", "w") as f:
            json.dump(report_data, f, indent=4)
        print("✅ Report saved to agent_report.json")

    except json.JSONDecodeError:
        print("\n⚠️  Could not parse JSON report. Raw output:")
        print(final_output)
    except Exception as e:
        print(f"\n❌ Error processing report: {e}")
        print("Raw output:")
        print(result["messages"][-1].content)