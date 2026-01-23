# AI-Driven Autonomous Test Engineer

## 🚀 Project Overview
This project implements a sophisticated, multi-agent autonomous system designed to solve one of the most persistent
bottlenecks in modern software development: **maintaining high-quality test coverage**.

Powered by the **Gemini 3 Flash Preview** model and the **LangChain/LangGraph** ecosystem, the system acts as a
"Virtual QA Engineer." It autonomously clones Java repositories, analyzes production code, generates robust JUnit 5
test suites, and iteratively heals them until the build passes and the coverage targets are met.

---

## 🎯 Problem To Be Solved
Maintaining high code coverage in large Java/Gradle multi-module projects is historically difficult because:
1. **Manual Effort:** Writing boilerplate unit tests is time-consuming for developers.
2. **Maintenance Debt:** As logic evolves, tests break. Fixing them is often deprioritized.
3. **Complexity:** Mocking intricate dependencies and handling edge cases requires deep code analysis.
4. **Consistency:** Enforcing project-wide testing standards (naming, libraries, tagging) is hard to scale manually.

---

## ✨ Key Features
Experience the future of automated testing with a system designed for power, precision, and reliability:

- **🤖 Fully Autonomous Workflow:** Just point to a repository, and the system handles the rest — cloning, analyzing,
  generating tests, verifying builds, and committing changes.
- **🧠 Self-Healing Intelligence:** It doesn't just write code; it fixes it. If a test fails or code doesn't compile,
  the agent iteratively repairs its own work until the build passes.
- **🎨 Infinite Flexibility:** Define your exact testing requirements in a simple `TESTING_STANDARDS.md` file. Whether
  you use JUnit 5, TestNG, Spock, or custom libraries, the agent adapts its output to match your stack.
- **🚀 Multi-Repo Scalability:** Seamlessly manage dozens of repositories in one workspace. The system automatically
  handles isolated subdirectories and project-specific contexts, letting you scale your QA efforts across your entire
  organization.
- **🎯 Surgical Precision:** Advanced coverage analysis identifies critical "hotspots" (complex methods with zero
  coverage) and targets them for maximum impact.
- **🛡️ Enterprise-Grade Safety:** Built-in guardrails ensure production code remains untouched, while strict
  "Read-Before-Mock" protocols eliminate hallucinations.
- **🤝 Specialized Multi-Agent Core:** A team of five expert agents — including a dedicated Architect, Test Writer, and
  Build Specialist — collaborates to solve complex testing challenges.
- **⚡ High-Performance Architecture:** Features like parallel processing, intelligent context folding, and Gradle
  daemon management ensure speed and efficiency at scale.
- **✅ Enforced Consistency:** Automatically enforces the best practices defined in your `TESTING_STANDARDS.md`,
  ensuring that every generated test feels like it was written by your lead engineer.

---

## 🛠 Implementation
The system is built on a **Modular Multi-Agent Architecture** where specialized agents collaborate to achieve
the coverage objective:

### 1. The Agentic Core
The system is built on a modular, decentralized architecture where each agent is a specialist in a specific domain.
Instead of one massive prompt, responsibility is split across **six** distinct personas that communicate via a
structured delegation protocol:

- **Orchestrator (The Architect):** Acts as the high-level Project Manager. It steers the multi-phase workflow
  (Preparation → Baseline → Improvement → Finalization), coordinates sub-agents via the native `task` tool, and
  enforces the "Stopping Hierarchy." It also consolidates performance metrics across the entire run.
- **Git Agent (The Repository Manager):** The gatekeeper of the codebase. It handles repository lifecycles using
  specialized tools like `ensure_branch` to safely create or check out local branches without destructive actions.
  It enforces strict **Branch Safety** and performs **Repository Existence Checks**.
- **Build Agent (The Gradle Specialist):** Responsible for the "Feedback Loop." It optimizes for efficiency by
  identifying the narrowest possible Gradle tasks (e.g., `:module:test`) and manages the Gradle daemon to reduce
  initialization overhead. It is trained to extract the **Root Cause** of build failures.
- **Test Writer Agent (The Coding Specialist):** The engine of code generation. It inspects production code and
  generates robust JUnit 5 tests. It follows a "Read-Before-Mock" protocol to prevent hallucinations and employs a
  **One-Shot Strategy** to generate entire test suites in a single operation.
- **Reviewer Agent (The Gatekeeper):** A dedicated quality assurance agent that strictly reviews generated code
  against `TESTING_STANDARDS.md` *before* it reaches the compiler. It checks for idiomatic usage, naming conventions,
  and mandatory annotations like `@Tag("ai-generated")`, forcing the Test Writer to fix issues immediately.
- **Coverage Agent (The Metrics Specialist):** A data-processing specialist. It parses JaCoCo XML reports in
  parallel using a `ProcessPoolExecutor`. Beyond reporting raw percentages, it identifies **Hotspot Methods**
  (0% coverage in low-coverage classes) to provide the Test Writer with surgical targets.

### 2. The Collaboration Flow ("The Hand-off")
The agents interact in a deterministic sequence managed by the Orchestrator:
1. **Setup:** Orchestrator triggers the **Git Agent** to prepare the sandbox and ensure the correct branch.
2. **Analysis:** Orchestrator uses the **Build** and **Coverage** agents to identify current gaps and hotspots.
3. **Execution:** Orchestrator picks a target class and tasks the **Test Writer** to generate a complete suite.
4. **Review:** The **Reviewer Agent** analyzes the generated code. If rejected, the Test Writer must fix it.
5. **Validation:** Once approved, the Orchestrator sends the result to the **Build Agent** for verification.
6. **Self-Healing:** If verification fails, the Orchestrator sends the **Test Writer** back into the code with the
   specific error logs until the build passes.
7. **Finalization:** The **Coverage Agent** calculates the final delta, and the Orchestrator prepares the
   machine-friendly report.

### 3. Technical Guardrails
- **Security & Safety:**
    - **Command Whitelist:** The agent is restricted to a strict set of allowed commands (`git`, `gradle`, `./gradlew`, `test`).
      Dangerous commands like `grep`, `rm`, or `cat` are blocked at the middleware level to prevent unintended side effects.
    - **Branch Isolation:** Git operations are confined to specific feature branches to protect the main line.
- **Logical Sandboxing:** All agents operate in a virtual filesystem where the project is anchored at `/`. A custom
  `HostSandboxBackend` maps this to the physical filesystem while preventing path traversal.
- **Quota & Token Management:**
    - **Adaptive Backoff:** Dynamically adjusts request pacing based on API pressure.
    - **Intelligent Context Folding:** Uses `SummarizationMiddleware` to collapse long histories.
- **Self-Healing Loop:** An iterative "Generate -> Review -> Verify -> Fix" protocol that allows the system to repair
  its own logic and compilation errors.

---

## 🧠 Challenges
During development, several key challenges were addressed:
- **Path Divergence:** Resolving the mismatch between how an AI "sees" a file path versus how a shell command
  executes it on the host.
- **Hallucination Control:** Preventing the AI from mocking non-existent methods by mandating a "Mocking Verification"
  phase where it must read the dependency source first.
- **Recursive Loops:** Managing LangGraph recursion limits by implementing custom step counters and early-exit
  conditions.
- **Parallelism vs. Quota:** Balancing the speed of concurrent test generation with the strict per-minute token
  limits of LLM APIs.

---

## ⚠️ Known Limitations
- **Ecosystem Coupling:** The current implementation is specifically tuned for Java, Gradle, and JUnit 5.
- **Local Execution:** Commands run on the host system via a logical sandbox; it is not yet fully isolated via Docker
  (though the architecture supports it).
- **Complexity Cap:** Extremely large classes with deeply nested dependencies may still require multiple iterations
  to reach very high (>90%) coverage.

---

## 🔮 Outlook
The next phases of the project will focus on:
- **Integration Test Support:** Expanding the Test Writer's capabilities to handle `@SpringBootTest` and Testcontainers.
- **Pull Request Integration:** Automatically submitting generated tests as PRs to GitLab/GitHub.
- **MCP Integration:** Integrating the system into Gemini CLI or other coding agents using the Model Context Protocol
  (MCP). This would allow developers to trigger autonomous test generation via natural language prompts directly from
  their development environment, keeping them unblocked while the agent works in the background.
- **Proactive Refactoring:** Allowing the agents to suggest production code improvements to make classes more
  "testable."

---
André Gasser, January 2026