import subprocess
import os
from pathlib import Path
from deepagents.backends import FilesystemBackend
from deepagents.backends.protocol import SandboxBackendProtocol, ExecuteResponse

class HostSandboxBackend(FilesystemBackend, SandboxBackendProtocol):
    """
    A unified backend that supports filesystem operations and host command execution.
    Anchored to a physical root but presented as logical '/'.
    """
    
    def __init__(self, root_dir: str | Path):
        # Initialize the FilesystemBackend part
        super().__init__(root_dir=root_dir, virtual_mode=True)
        self._id = f"host-sandbox-{os.getpid()}"

    @property
    def id(self) -> str:
        return self._id

    def execute(self, command: str) -> ExecuteResponse:
        """Executes a whitelisted command on the host machine within the sandbox root."""
        try:
            # Command Whitelist Check
            allowed_prefixes = ("test", "git ", "gradle ", "./gradlew ", "chmod +x gradlew")
            if not any(command.strip().startswith(prefix) for prefix in allowed_prefixes):
                return ExecuteResponse(
                    output=f"Security Error: Command '{command}' is not allowed. Only 'git', 'gradle', and './gradlew' are permitted.",
                    exit_code=1,
                    truncated=False
                )

            # Execute with self.cwd (the physical root) as the working directory
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                check=False
            )
            return ExecuteResponse(
                output=result.stdout + result.stderr,
                exit_code=result.returncode,
                truncated=False
            )
        except Exception as e:
            return ExecuteResponse(
                output=f"System Error: {str(e)}",
                exit_code=1,
                truncated=False
            )

    def upload_files(self, files):
        return super().upload_files(files)

    def download_files(self, paths):
        return super().download_files(paths)
