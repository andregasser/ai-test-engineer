import subprocess
import os
from langchain_core.tools import tool
from shared_utils.prompt_utils import get_inherited_prompt
from shared_utils.schema_utils import GitAgentOutput

GIT_ROLE = "You are a Git specialist agent working inside a sandboxed environment."

GIT_PROTOCOL = """
1. **PREPARATION:** Ensure the repository is in the correct state for the requested operation.
2. **MODIFICATION:** Perform the requested git actions (clone, checkout, commit, or push).
3. **VERIFICATION:** Confirm that the operation was successful and the state is consistent.
4. **SUMMARY:** Provide a concise report of the changes or the repository state.
"""

GIT_RULES = """
- **TECHNICAL IMPLEMENTATION:** 
  - For repository setup (clone/branch), you MUST use the `git_setup_repo` tool. It handles the deterministic logic for remote vs local branches.
  - Use `git_list_branches` and `git_current_branch` to verify state instead of raw `git branch` commands.
  - You MUST use the `execute` tool for all other shell-based git commands (commit, push).
- **BRANCH POLICY:** 
  - If the requested branch exists on the remote, track it. 
  - If it only exists locally, switch to it. 
  - If it exists nowhere, create it from the primary development branch (e.g. `origin/dev`).
- **NO DESTRUCTIVE ACTIONS:** You are STRICTLY FORBIDDEN from performing any destructive operations on the local or remote repository. This includes:
  - `git reset --hard` (locally or against remote).
  - Deleting remote branches (`git push origin --delete ...`).
  - Force pushing (`--force`, `-f`, or `--force-with-lease`).
  - Modifying existing history (rebase, squash, or reset).
- **SANDBOX:** You operate within a sandboxed directory. All paths are relative to your root (/).
- **FINALIZE:** To finish your task, you **MUST** call the `submit_git_output` tool. This is the only way to return your result.
"""

GIT_SYSTEM_PROMPT = get_inherited_prompt(GIT_ROLE, GIT_PROTOCOL, GIT_RULES)

from shared_utils.logger import get_logger

logger = get_logger("git-subagent")

@tool
def git_list_branches() -> dict:
    """Lists all local and remote branches."""
    try:
        # We assume the execute tool is used for the logic, but here we implement the bound tool
        # In deep_agent mode, we can just use subprocess if we know the project_root
        # However, to be consistent with the user's request for robustness:
        res = subprocess.run(["git", "branch", "-a"], capture_output=True, text=True)
        lines = res.stdout.splitlines()
        local = []
        remote = []
        for line in lines:
            line = line.strip().replace("* ", "")
            if line.startswith("remotes/"):
                remote.append(line)
            else:
                local.append(line)
        return {"local": local, "remote": remote}
    except Exception as e:
        return {"error": str(e)}

@tool
def git_current_branch() -> str:
    """Returns the name of the current active branch."""
    try:
        res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
        return res.stdout.strip()
    except Exception as e:
        return f"Error: {str(e)}"

@tool
def git_setup_repo(repo_url: str, branch: str) -> dict:
    """
    Robustly prepares the repository:
    1. Clones if .git missing.
    2. Fetches origin.
    3. Handles branch creation/checkout logic deterministically.
    """
    try:
        if not os.path.exists(".git"):
            logger.info(f"Cloning {repo_url}")
            res = subprocess.run(["git", "clone", repo_url, "."], capture_output=True, text=True)
            if res.returncode != 0:
                return {"status": "error", "step": "clone", "stderr": res.stderr}
        
        subprocess.run(["git", "fetch", "origin"], capture_output=True, text=True)
        
        res = subprocess.run(["git", "branch", "-r"], capture_output=True, text=True)
        remote_branches = [b.strip() for b in res.stdout.splitlines()]
        
        res = subprocess.run(["git", "branch"], capture_output=True, text=True)
        local_branches = [b.strip().replace("* ", "") for b in res.stdout.splitlines()]
        
        remote_target = f"origin/{branch}"
        
        if remote_target in remote_branches:
            if branch in local_branches:
                cmd = ["git", "checkout", branch]
            else:
                cmd = ["git", "checkout", "-b", branch, remote_target]
        elif branch in local_branches:
            cmd = ["git", "checkout", branch]
        else:
            base = "origin/dev" if "origin/dev" in remote_branches else "origin/main"
            cmd = ["git", "checkout", "-b", branch, base]
            
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            return {"status": "error", "step": "checkout", "stderr": res.stderr}
            
        return {"status": "success", "current_branch": branch, "message": f"Repo ready on {branch}"}
    except Exception as e:
        return {"status": "error", "step": "setup", "stderr": str(e)}

@tool(args_schema=GitAgentOutput)
def submit_git_output(**kwargs):
    """Finalizes the Git agent's work and returns the structured result."""
    logger.info(f"✅ Git operation finished with status: {kwargs.get('status')}")
    return kwargs

def get_git_subagent():
    """Factory function to create the Git Subagent."""
    logger.info("🛠️  Initializing Git Subagent...")
    return {
        "name": "git-subagent",
        "description": "Handles repository management: cloning, checking out branches, committing, and pushing.",
        "system_prompt": GIT_SYSTEM_PROMPT,
        "tools": [git_setup_repo, git_list_branches, git_current_branch, submit_git_output],
    }