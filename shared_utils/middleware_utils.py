from langchain.agents.middleware import (
    ModelCallLimitMiddleware, 
    ModelRetryMiddleware, 
    ToolRetryMiddleware,
    ShellToolMiddleware,
    HostExecutionPolicy
)
from shared_utils.backend_utils import HostSandboxBackend

def get_agent_runtime(project_root: str):
    """
    Creates a dedicated runtime environment (middleware + backend) for a specific project root.
    """
    backend = HostSandboxBackend(root_dir=project_root)
    
    middleware = [
        ModelCallLimitMiddleware(run_limit=100, exit_behavior="end"),
        ModelRetryMiddleware(max_retries=3),
        ToolRetryMiddleware(max_retries=3),
        ShellToolMiddleware(
            workspace_root=project_root,
            execution_policy=HostExecutionPolicy()
        )
    ]
    
    return middleware, backend
