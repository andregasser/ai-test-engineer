COMMON_PROJECT_CONTEXT = f"""
# PROJECT CONTEXT:
1. **Root:** / (This is the ONLY allowed absolute root. All project files live here.)

# CRITICAL RULES (All tool use):
1. **ABSOLUTE LOGICAL PATHS:** All paths MUST be absolute, starting with `/`. Never use host or relative paths.
2. **NO TRAVERSAL:** Never use '..' in paths. You are NOT allowed to escape the `/` root.
4. **DOMAIN-AWARE SEARCH (Multi-module):** Use glob patterns from root (e.g. `/**/src/main/java/**`).
5. **PLANNING DISCIPLINE:** Maintain a clear plan. Update only for complex tasks (3+ steps).
6. **SHELL PATHS:** When using the `execute` tool, you are already in the logical root. Use relative paths (e.g., `./gradlew`) for command arguments. NEVER start a path argument with `/` in a shell command.
7. **STRICT SHELL WHITELIST:** You may ONLY run commands starting with these prefixes:
   - `test` (e.g. `test -d ".git"`)
   - `git ` (e.g. `git status`)
   - `gradle `
   - `./gradlew `
   - `chmod +x gradlew`
   **DO NOT** attempt any other commands (no `ls`, `pwd`, `rm`, `curl`, `ssh`, etc.). If a command is not on this list, you CANNOT run it.
"""

def get_inherited_prompt(agent_role: str, agent_protocol: str, agent_rules: str = "") -> str:
    return f"""
{agent_role}

{COMMON_PROJECT_CONTEXT}

# PROTOCOL:
{agent_protocol}

# AGENT-SPECIFIC RULES:
{agent_rules}
"""