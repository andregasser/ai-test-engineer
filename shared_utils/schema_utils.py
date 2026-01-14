from pydantic import BaseModel, Field
from typing import List, Optional

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