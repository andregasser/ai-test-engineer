from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class ToolResponse(BaseModel):
    """Base class for all tool responses."""
    success: bool = Field(..., description="Whether the tool operation was successful.")
    error: Optional[str] = Field(None, description="Error message if success is False.")

class BuildResultResponse(ToolResponse):
    build_duration_sec: float = Field(0.0, description="Time taken for the build process.")
    logs: str = Field(..., description="The captured (and potentially truncated) build logs.")
    command: str = Field(..., description="The exact Gradle command executed.")

class CoverageSummaryResponse(ToolResponse):
    line_coverage: float = Field(0.0, description="Overall line coverage (0.0 to 1.0).")
    branch_coverage: float = Field(0.0, description="Overall branch coverage (0.0 to 1.0).")
    worst_classes: List[str] = Field(default_factory=list, description="The top 20 classes with lowest coverage.")

class AgentReport(BaseModel):
    """Final machine-readable report from the orchestrator."""
    initial_coverage: float = Field(..., description="Coverage percentage before the run.")
    final_coverage: float = Field(..., description="Coverage percentage after the run.")
    coverage_delta: float = Field(..., description="Absolute change in coverage.")
    classes_targeted: List[str] = Field(..., description="List of classes selected for improvement.")
    classes_improved: List[str] = Field(..., description="List of classes where coverage successfully increased.")
    classes_failed: List[str] = Field(..., description="List of classes that failed to improve or compile.")
    total_iterations: int = Field(..., description="Number of improvement cycles run.")
    duration_seconds: float = Field(..., description="Total execution time.")
    termination_reason: str = Field(..., description="Why the agent stopped (e.g., 'Target Reached', 'Max Iterations').")

# --- Sub-Agent Output Models ---

class GitAgentOutput(BaseModel):
    """Structured output for the Git Sub-Agent."""
    status: str = Field(..., description="'success' or 'failure'")
    repo_path: str = Field(..., description="Local path to the cloned/checked-out repository.")
    current_branch: str = Field(..., description="The currently active branch.")
    commit_hash: Optional[str] = Field(None, description="The HEAD commit hash.")
    error_message: Optional[str] = Field(None, description="Error details if status is failure.")

class TestWriterAgentOutput(BaseModel):
    """Structured output for the Test Writer Sub-Agent."""
    status: str = Field(..., description="'success' or 'failure'")
    files_created: List[str] = Field(default_factory=list, description="List of test files created or modified.")
    classes_covered: List[str] = Field(default_factory=list, description="List of production classes targeted.")
    compilation_status: Optional[str] = Field(None, description="predicted compilation status (not verified).")
    error_message: Optional[str] = Field(None, description="Error details if generation failed.")

class BuildAgentOutput(BaseModel):
    """Structured output for the Build Sub-Agent."""
    status: str = Field(..., description="'success' or 'failure'")
    scope: str = Field(..., description="Scope of the build (e.g., 'module::service-a', 'class::MyTest').")
    exit_code: int = Field(..., description="Process exit code.")
    failed_tests: List[str] = Field(default_factory=list, description="List of failed test methods (Class.method).")
    commands_run: List[str] = Field(default_factory=list, description="List of shell commands executed.")
    summary: str = Field(..., description="Brief summary of the build result.")

class CoverageAgentOutput(BaseModel):
    """Structured output for the Coverage Sub-Agent."""
    module: str = Field(..., description="The module or scope analyzed.")
    overall_coverage: float = Field(..., description="Overall line coverage (0.0 to 1.0) for the scope.")
    by_class: Dict[str, float] = Field(default_factory=dict, description="Mapping of FQN to coverage float (0.0 to 1.0).")
    hotspots: List[str] = Field(default_factory=list, description="List of methods with 0% coverage to target.")

class ReviewerAgentOutput(BaseModel):
    """Structured output for the Reviewer Sub-Agent."""
    status: str = Field(..., description="'approved' or 'rejected'")
    critical_violations: List[str] = Field(default_factory=list, description="List of specific standard violations found.")
    constructive_feedback: str = Field(..., description="Actionable instructions for the Test Writer to fix the issues.")