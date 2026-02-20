# AI Test Engineer: Multi-Agent Architecture

## Agent Personas

### 1. Orchestrator
- **Role:** Manager.
- **Actions:** Plan phases (Prep → Baseline → Improve → Final). Delegate tasks. Enforce stopping logic. Consolidate metrics.
- **Tool:** `task`.

### 2. Git Agent
- **Role:** Repo Admin.
- **Actions:** Clone repos. Manage branches. Enforce branch safety. Initialize workspace.

### 3. Build Agent
- **Role:** Build Engineer.
- **Actions:** Identify Gradle tasks. Manage Gradle daemon. Analyze build failures. Extract error logs.

### 4. Test Writer
- **Role:** Coder.
- **Actions:** Inspect code. Write JUnit 5 tests. Read dependencies before mocking (No hallucinations). Generate full suites.

### 5. Reviewer
- **Role:** QA Gatekeeper.
- **Actions:** Analyze code before compilation. Enforce `TESTING_STANDARDS.md`. Check naming/annotations. Reject low-quality code.

### 6. Coverage Agent
- **Role:** Analyst.
- **Actions:** Parse JaCoCo reports. Identify hotspot methods (0% coverage). Target high-complexity gaps.

---

## Execution Flow

1. **Setup:** Git Agent clones/checks out.
2. **Analysis:** Build + Coverage agents find gaps.
3. **Loop:**
   - Test Writer generates suite.
   - Reviewer validates against standards.
   - Build Agent verifies compilation/execution.
   - (If Fail) Test Writer repairs code with error logs.
4. **Report:** Coverage Agent calculates delta. Orchestrator submits report.

---

## Running the System

### Prerequisites
- Python 3.10+
- Java 21 + Gradle
- `.env` file with `GOOGLE_API_KEY` (Gemini)

### Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Run coverage optimization
python3 runner.py \
  --repo-url <git_url> \
  --workspace ./workspace \
  --target-coverage 0.8 \
  --test-type "Unit Tests"
```

### Key Arguments
- `--repo-url`: Required. SSH/HTTPS URL.
- `--workspace`: Required. Base directory for projects.
- `--target-coverage`: Target float (e.g., 0.8).
- `--branch`: Specific branch (optional).
- `--target-classes`: Space-separated fully qualified names (optional).
- `--target-modules`: Specific Gradle modules (optional).

### Troubleshooting
- **Logs:** Check console output for `langchain.debug` traces.
- **Report:** View `agent_report.json` for final state.
- **Workdir:** Files are processed in the directory specified by `--workspace`.
- **Model Overload:** System retries automatically (3x) on rate limits.
