from langchain_core.tools import tool
from shared_utils.prompt_utils import get_inherited_prompt
from shared_utils.schema_utils import GitAgentOutput

GIT_ROLE = "You are a Git specialist agent working inside a sandboxed environment."

GIT_PROTOCOL = """
1. Use the `shell` tool to run git commands (clone, checkout, commit, push).
2. All operations should happen within the logical root (/).
3. Return a concise summary of what was achieved.
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

@tool(args_schema=GitAgentOutput)
def submit_git_output(**kwargs):
    """Finalizes the Git agent's work and returns the structured result."""
    return kwargs

def get_git_subagent():
    """Factory function to create the Git Subagent."""
    return {
        "name": "git-subagent",
        "description": "Handles repository management: cloning, checking out branches, committing, and pushing.",
        "system_prompt": GIT_SYSTEM_PROMPT,
        "tools": [submit_git_output],
    }
