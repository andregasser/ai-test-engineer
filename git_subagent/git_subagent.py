import subprocess
from langchain_core.tools import tool
from shared_utils.prompt_utils import get_inherited_prompt
from shared_utils.schema_utils import GitAgentOutput

GIT_ROLE = "You are a Git specialist agent working inside a sandboxed environment."

GIT_PROTOCOL = """
1. **BRANCHING:** You MUST use the `ensure_branch` tool to switch branches. This tool handles creation vs checkout logic automatically.
2. Use the `shell` tool to run other git commands (clone, commit, push) if needed.
3. All operations should happen within the logical root (/).
4. Return a concise summary of what was achieved.
"""

GIT_RULES = """
- **NON-INTERACTIVE ENFORCEMENT:** You are in a non-interactive environment. If a command prompts for credentials, confirmation, or input, it will HANG. Always use flags like `--no-edit` or `-y` where applicable. If a hang is detected, report it as a terminal failure.
- **REPOSITORY EXISTENCE CHECK:** You MUST NOT run git in or against a directory unless you are 100% sure it is a valid repo. If unsure, first run `test -d ".git"` using `shell`. If the check fails, DO NOT run git commands; instead, report the missing repo and re-clone if necessary.
- **BRANCH SAFETY:** NEVER perform any damaging or destructive operations (reset, delete, force push) on any branch other than the explicitly assigned feature branch. You are ONLY allowed to work on the feature branch.
- **DIRTY TREE PREVENTION:** Before switching branches or performing a hard reset, verify the status of the working tree to ensure no valuable partial work is accidentally lost.
- **FAIL FAST:** If a command fails, inspect the error text. If it says "not a git repository", STOP and do not run more git commands on that path. Explain that the repository is missing or needs cloning. Report all other exit codes and stderr immediately.
- **OUTPUT FORMAT:** To finish your task, you **MUST** call the `submit_git_output` tool. This is the only way to return your result. Refer to the tool's definition for the required arguments.
"""

GIT_SYSTEM_PROMPT = get_inherited_prompt(GIT_ROLE, GIT_PROTOCOL, GIT_RULES)

from shared_utils.logger import get_logger

logger = get_logger("git-subagent")

@tool
def ensure_branch(branch_name: str, project_root: str = ".") -> str:
    """
    Checks if a branch exists locally. 
    If it exists, checks it out. 
    If not, creates it (git checkout -b) and checks it out.
    """
    try:
        # Check if branch exists
        check_cmd = ["git", "branch", "--list", branch_name]
        result = subprocess.run(check_cmd, cwd=project_root, capture_output=True, text=True, check=True)
        
        if branch_name in result.stdout:
            # Branch exists, simply checkout
            cmd = ["git", "checkout", branch_name]
            action = "checked out existing"
        else:
            # Branch does not exist, create and checkout
            cmd = ["git", "checkout", "-b", branch_name]
            action = "created and checked out"
            
        subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, check=True)
        return f"Successfully {action} branch '{branch_name}'."
        
    except subprocess.CalledProcessError as e:
        return f"Error managing branch '{branch_name}': {e.stderr}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"

@tool(args_schema=GitAgentOutput)
def submit_git_output(**kwargs):
    """Finalizes the Git agent's work and returns the structured result."""
    logger.info(f"✅ Git operation finished with status: {kwargs.get('status')}")
    return kwargs

def get_git_subagent(project_root: str):
    """Factory function to create the Git Subagent."""
    logger.info("🛠️  Initializing Git Subagent...")
    return {
        "name": "git-subagent",
        "description": "Handles repository management: cloning, checking out branches, committing, and pushing.",
        "system_prompt": GIT_SYSTEM_PROMPT,
        "tools": [ensure_branch, submit_git_output],
    }
