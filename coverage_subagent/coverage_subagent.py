import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from lxml import etree
from langchain_core.tools import tool
from shared_utils.prompt_utils import get_inherited_prompt
from shared_utils.schema_utils import CoverageSummaryResponse, CoverageAgentOutput
from shared_utils.logger import get_logger

logger = get_logger("coverage-subagent")

COVERAGE_ROLE = "You are a coverage analysis agent for a Java/Gradle project."

COVERAGE_PROTOCOL = """
1. **DATA RETRIEVAL:** Gather the latest coverage metrics for the target scope.
2. **GAP ANALYSIS:** Identify specific methods and classes with low or zero coverage.
3. **IMPROVEMENT TRACKING:** Calculate the delta between current and previous metrics.
4. **REPORTING:** Provide a structured summary of coverage status and hotspots.
"""

COVERAGE_RULES = """
- **TECHNICAL IMPLEMENTATION:** You MUST use the `read_coverage_report` tool to gather metrics.
- **XML ONLY:** You only process JaCoCo XML reports. HTML reports are ignored.
- **GAP IDENTIFICATION:** Identify 'Hotspot Methods' (0% coverage in a low-coverage class) using high-performance lxml streaming to provide surgical targets.
- **VERIFICATION:** Explicitly compare current metrics with previous iterations to calculate the percentage-point delta.
- **READ ONLY:** You are only an analyst. Do not attempt to run builds or modify files.
- **SANDBOX:** You operate within a sandboxed directory. All paths are relative to your root (/).
- **FINALIZE:** To finish your task, you **MUST** call the `submit_coverage_output` tool.
"""

COVERAGE_SYSTEM_PROMPT = get_inherited_prompt(COVERAGE_ROLE, COVERAGE_PROTOCOL, COVERAGE_RULES)

def _parse_and_filter_report(report_path: Path, exclude_patterns: list, targets_p: list, targets_c: list):
    """Parses a JaCoCo report."""
    lines_missed = 0
    lines_covered = 0
    branches_missed = 0
    branches_covered = 0
    class_data = []
    try:
        context = etree.iterparse(str(report_path), events=("end",), tag="class")
        for event, elem in context:
            class_name = elem.get("name", "").replace("/", ".")
            if any(re.search(p, class_name, re.IGNORECASE) for p in exclude_patterns):
                elem.clear()
                while elem.getprevious() is not None:
                    del elem.getparent()[0]
                continue
            if targets_p and not any(class_name.startswith(p) for p in targets_p):
                elem.clear()
                while elem.getprevious() is not None:
                    del elem.getparent()[0]
                continue
            if targets_c and not any(class_name == t or class_name.endswith("." + t) for t in targets_c):
                elem.clear()
                while elem.getprevious() is not None:
                    del elem.getparent()[0]
                    continue
            c_l_m = c_l_c = 0
            for child in elem:
                if child.tag == "counter":
                    ctype = child.get("type")
                    missed, covered = int(child.get("missed")), int(child.get("covered"))
                    if ctype == "LINE":
                        c_l_m, c_l_c = missed, covered
                        lines_missed += missed
                        lines_covered += covered
                    elif ctype == "BRANCH":
                        branches_missed += missed
                        branches_covered += covered
            if (c_l_m + c_l_c) > 0:
                class_data.append((class_name, c_l_c / (c_l_m + c_l_c)))
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]
        return {"lines_missed": lines_missed, "lines_covered": lines_covered, "branches_missed": branches_missed, "branches_covered": branches_covered, "class_data": class_data}
    except Exception as e:
        logger.error(f"Error parsing {report_path}: {e}")
        return None

@tool
def read_coverage_report(target_modules: str = None, target_packages: str = None, target_classes: str = None) -> CoverageSummaryResponse:
    """Parses JaCoCo XML reports ONLY. Uses high-performance lxml streaming."""
    try:
        report_files = []
        if Path("TESTING_STANDARDS.md").exists():
            try:
                content = Path("TESTING_STANDARDS.md").read_text()
                match = re.search(r"(?:Report Path|Jacoco XML Report):\s*([^\s\n]+\.xml)", content, re.IGNORECASE)
                if match:
                    custom_path = Path(match.group(1).strip())
                    if custom_path.exists():
                        report_files = [custom_path]
            except Exception: pass
        targets_m = [t.strip() for t in target_modules.split(",") if t.strip()] if target_modules else []
        if not report_files and targets_m:
            for module in targets_m:
                cand = Path(module) / "build/reports/jacoco/test/jacocoTestReport.xml"
                if cand.exists(): report_files.append(cand)
        if not report_files:
            std_path = Path("build/reports/jacoco/test/jacocoTestReport.xml")
            if std_path.exists(): report_files = [std_path]
            else:
                possible_root = Path("build/reports/jacoco/root/jacocoRootReport.xml")
                if possible_root.exists(): report_files = [possible_root]
                else: report_files = list(Path(".").glob("**/jacocoTestReport.xml"))
        if not report_files: return CoverageSummaryResponse(success=False, error="No JaCoCo XML reports found.")
        total_lines_missed = total_lines_covered = total_branches_missed = total_branches_covered = 0
        all_class_data = []
        exclude_patterns = [r"\.generated\.", r"\.dto\.", r"\.model\.", r"\.exception\."]
        targets_p = [t.strip() for t in target_packages.split(",") if t.strip()] if target_packages else []
        targets_c = [t.strip() for t in target_classes.split(",") if t.strip()] if target_classes else []
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(_parse_and_filter_report, rp, exclude_patterns, targets_p, targets_c) for rp in report_files]
            results = [f.result() for f in futures]
        for res in results:
            if res:
                total_lines_missed += res["lines_missed"]; total_lines_covered += res["lines_covered"]
                total_branches_missed += res["branches_missed"]; total_branches_covered += res["branches_covered"]
                all_class_data.extend(res["class_data"])
        all_class_data.sort(key=lambda x: x[1])
        top_worst = all_class_data[:20]
        overall_line = total_lines_covered / (total_lines_missed + total_lines_covered) if (total_lines_missed + total_lines_covered) > 0 else 0.0
        overall_branch = total_branches_covered / (total_branches_missed + total_branches_covered) if (total_branches_missed + total_branches_covered) > 0 else 0.0
        return CoverageSummaryResponse(success=True, line_coverage=overall_line, branch_coverage=overall_branch, worst_classes=[c for c, _ in top_worst])
    except Exception as e: return CoverageSummaryResponse(success=False, error=str(e))

@tool(args_schema=CoverageAgentOutput)
def submit_coverage_output(**kwargs):
    """Finalizes the Coverage agent's work."""
    logger.info(f"📊 Coverage finished. Overall: {kwargs.get('overall_coverage'):.2%}")
    return kwargs

def get_coverage_subagent():
    """Factory function to create the Coverage Subagent."""
    logger.info("📈 Initializing Coverage Subagent...")
    return {
        "name": "coverage-subagent",
        "description": "Parses and analyzes JaCoCo coverage reports.",
        "system_prompt": COVERAGE_SYSTEM_PROMPT,
        "tools": [read_coverage_report, submit_coverage_output],
    }
