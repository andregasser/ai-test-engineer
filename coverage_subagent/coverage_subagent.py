from pathlib import Path
import re
from langchain_core.tools import tool
from shared_utils.prompt_utils import get_inherited_prompt
from shared_utils.schema_utils import CoverageSummaryResponse
from shared_utils.schema_utils import CoverageAgentOutput
from shared_utils.logger import get_logger
from lxml import etree

logger = get_logger("coverage-subagent")

COVERAGE_ROLE = "You are a coverage analysis agent for a Java/Gradle project."

COVERAGE_PROTOCOL = "1. Analyze coverage using `read_coverage_report`. Use the `target_classes` parameter to verify specific improvements in batch."

COVERAGE_RULES = """
- **GAP IDENTIFICATION:** Beyond returning metrics, identify specific 'Hotspot Methods' (methods with 0% coverage in a low-coverage class) to give the Test Writer a clear target.
- **IMPROVEMENT VERIFICATION:** Explicitly compare the current line/branch counts with the previous iteration to calculate the exact percentage-point delta achieved.
- **ONLY READ:** You do NOT run builds. 
- **NO OTHER TOOLS:** Do NOT attempt other tools.
- **OUTPUT FORMAT:** To finish your task, you **MUST** call the `submit_coverage_output` tool. This is the only way to return your result. Refer to the tool's definition for the required arguments.
"""

COVERAGE_SYSTEM_PROMPT = get_inherited_prompt(COVERAGE_ROLE, COVERAGE_PROTOCOL, COVERAGE_RULES)

def _parse_and_filter_report(report_path: Path, exclude_patterns: list, targets_p: list, targets_c: list):
    """
    Parses a single JaCoCo report using lxml.iterparse for high performance and low memory usage.
    Applies filters on-the-fly.
    """
    lines_missed = 0
    lines_covered = 0
    branches_missed = 0
    branches_covered = 0
    class_data = []

    try:
        # Use iterparse to process the file incrementally
        context = etree.iterparse(str(report_path), events=("start", "end"))
        
        current_package = ""
        skip_current_package = False

        for event, elem in context:
            tag_name = elem.tag
            
            if event == "start":
                if tag_name == "package":
                    current_package = elem.get("name", "").replace("/", ".")
                    skip_current_package = False
                    
                    # Optimization: Skip entire package if it doesn't match target_packages
                    if targets_p:
                        # Check if this package starts with any target prefix
                        if not any(current_package.startswith(p) for p in targets_p):
                            skip_current_package = True
                    
                    # Optimization: Skip excluded packages immediately
                    if not skip_current_package and any(re.search(p, current_package, re.IGNORECASE) for p in exclude_patterns):
                        skip_current_package = True

            elif event == "end":
                if tag_name == "counter":
                    # Global counters (usually at the end of report or bundle)
                    # We only care about global counters if we are processing the root element or a relevant scope.
                    # However, extracting global metrics from filtered classes is safer.
                    pass

                elif tag_name == "class":
                    if skip_current_package:
                        elem.clear()
                        continue

                    class_name = elem.get("name", "").replace("/", ".")
                    
                    # Class Level Filtering
                    # 1. Exclusions
                    if any(re.search(p, class_name, re.IGNORECASE) for p in exclude_patterns):
                        elem.clear()
                        continue

                    # 2. Scope Matching (Class specific)
                    if targets_c:
                        is_match = False
                        for t in targets_c:
                            if class_name == t or class_name.endswith("." + t):
                                is_match = True
                                break
                        if not is_match:
                            elem.clear()
                            continue
                    
                    # If we reached here, the class is included. Extract its counters.
                    c_l_m = 0
                    c_l_c = 0
                    
                    for child in elem:
                        if child.tag == "counter":
                            ctype = child.get("type")
                            missed = int(child.get("missed"))
                            covered = int(child.get("covered"))
                            
                            if ctype == "LINE":
                                c_l_m = missed
                                c_l_c = covered
                                lines_missed += missed
                                lines_covered += covered
                            elif ctype == "BRANCH":
                                branches_missed += missed
                                branches_covered += covered
                    
                    # Store class data
                    if (c_l_m + c_l_c) > 0:
                        class_data.append((class_name, c_l_c / (c_l_m + c_l_c)))
                    
                    # Clear element to free memory
                    elem.clear()
                    
                elif tag_name == "package":
                    current_package = ""
                    skip_current_package = False
                    elem.clear()

        return {
            "lines_missed": lines_missed, 
            "lines_covered": lines_covered, 
            "branches_missed": branches_missed, 
            "branches_covered": branches_covered, 
            "class_data": class_data
        }
        
    except Exception as e:
        logger.error(f"Error parsing {report_path}: {e}")
        return None

@tool
def read_coverage_report(project_root: str, target_modules: str = None, target_packages: str = None, target_classes: str = None) -> CoverageSummaryResponse:
    """
    Parses JaCoCo XML reports with advanced filtering using fast streaming parsing.
    """
    try:
        import os
        root = Path(project_root)
        if not root.is_absolute():
            root = Path(os.getcwd()) / project_root
        
        logger.info(f"📊 Reading coverage report. Modules: {target_modules}, Packages: {target_packages}, Classes: {target_classes}")
        
        standards_file = root / "TESTING_STANDARDS.md"
        report_files = []

        # 1. Try to read path from TESTING_STANDARDS.md
        if standards_file.exists():
            try:
                content = standards_file.read_text()
                match = re.search(r"(?:Report Path|Jacoco Report):\s*([^\s\n]+)", content, re.IGNORECASE)
                if match:
                    custom_path = root / match.group(1).strip()
                    if custom_path.exists():
                        report_files = [custom_path]
            except Exception:
                pass 

        # 2. Logic: If target_modules is provided, prefer reports INSIDE those modules
        targets_m = [t.strip() for t in target_modules.split(",") if t.strip()] if target_modules else []
        
        if not report_files and targets_m:
            for module in targets_m:
                candidates = [
                    root / module / "build/reports/jacoco/test/jacocoTestReport.xml",
                ]
                for cand in candidates:
                    if cand.exists():
                        report_files.append(cand)
                        break
        
        # 3. Fallback to standard locations (root aggregate or search)
        if not report_files:
            std_path = root / "build/reports/jacoco/test/jacocoTestReport.xml"
            if std_path.exists():
                report_files = [std_path]
            else:
                possible_root = root / "build/reports/jacoco/root/jacocoRootReport.xml"
                if possible_root.exists():
                    report_files = [possible_root]
                else:
                    report_files = list(root.glob("**/jacocoTestReport.xml"))
        
        if not report_files:
            return CoverageSummaryResponse(success=False, error=f"No reports found in {root}")
            
        # Parse and Aggregation
        total_lines_missed = 0
        total_lines_covered = 0
        total_branches_missed = 0
        total_branches_covered = 0
        all_class_data = []
        
        exclude_patterns = [r"\.generated\.", r"\.dto\.", r"\.model\.", r"\.exception\."]
        targets_p = [t.strip() for t in target_packages.split(",") if t.strip()] if target_packages else []
        targets_c = [t.strip() for t in target_classes.split(",") if t.strip()] if target_classes else []

        # Process sequentially (faster for I/O bound XML parsing than mp overhead usually, especially with iterparse)
        for report_path in report_files:
            res = _parse_and_filter_report(report_path, exclude_patterns, targets_p, targets_c)
            if res:
                total_lines_missed += res["lines_missed"]
                total_lines_covered += res["lines_covered"]
                total_branches_missed += res["branches_missed"]
                total_branches_covered += res["branches_covered"]
                all_class_data.extend(res["class_data"])

        # Sort: worst coverage first
        all_class_data.sort(key=lambda x: x[1])
        top_worst = all_class_data[:20]

        overall_line = total_lines_covered / (total_lines_missed + total_lines_covered) if (total_lines_missed + total_lines_covered) > 0 else 0.0
        overall_branch = total_branches_covered / (total_branches_missed + total_branches_covered) if (total_branches_missed + total_branches_covered) > 0 else 0.0
        
        return CoverageSummaryResponse(
            success=True, 
            line_coverage=overall_line, 
            branch_coverage=overall_branch, 
            worst_classes=[c for c, _ in top_worst]
        )
    except Exception as e:
        return CoverageSummaryResponse(success=False, error=str(e))

from shared_utils.logger import get_logger

logger = get_logger("coverage-subagent")

@tool(args_schema=CoverageAgentOutput)
def submit_coverage_output(**kwargs):
    """Finalizes the Coverage agent's work and returns the structured result."""
    overall = kwargs.get('overall_coverage')
    hotspots = kwargs.get('hotspots', [])
    logger.info(f"📊 Coverage analysis finished. Overall: {overall:.2%}. Hotspots found: {len(hotspots)}")
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