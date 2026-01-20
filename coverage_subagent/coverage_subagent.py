from concurrent.futures import ProcessPoolExecutor
import xml.etree.ElementTree as ET
from pathlib import Path
import re
from langchain_core.tools import tool
from shared_utils.prompt_utils import get_inherited_prompt
from shared_utils.schema_utils import CoverageSummaryResponse
from shared_utils.schema_utils import CoverageAgentOutput

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

def _parse_single_report(report_path: Path):
    """Function to parse a single JaCoCo report."""
    try:
        tree = ET.parse(report_path)
        root_xml = tree.getroot()
        lines_missed = 0
        lines_covered = 0
        branches_missed = 0
        branches_covered = 0
        class_data = []
        for c in root_xml:
            tag_name = c.tag.split("}")[-1]
            if tag_name == "counter":
                ctype = c.attrib.get("type")
                if ctype == "LINE":
                    lines_missed += int(c.attrib["missed"])
                    lines_covered += int(c.attrib["covered"])
                elif ctype == "BRANCH":
                    branches_missed += int(c.attrib["missed"])
                    branches_covered += int(c.attrib["covered"])
        for element in root_xml.iter():
            tag_name = element.tag.split("}")[-1]
            if tag_name == "class":
                class_name = element.attrib.get("name", "")
                for child in element:
                    if child.tag.split("}")[-1] == "counter":
                        if child.attrib.get("type") == "LINE":
                            l_m = int(child.attrib["missed"])
                            l_c = int(child.attrib["covered"])
                            if (l_m + l_c) > 0:
                                class_data.append((class_name.replace("/", "."), l_c / (l_m + l_c)))
                            break
        return {"lines_missed": lines_missed, "lines_covered": lines_covered, "branches_missed": branches_missed, "branches_covered": branches_covered, "class_data": class_data}
    except Exception:
        return None

@tool
def read_coverage_report(project_root: str, target_modules: str = None, target_packages: str = None, target_classes: str = None) -> CoverageSummaryResponse:
    """
    Parses JaCoCo XML reports with advanced filtering.
    ...
    """
    logger.info(f"📊 Reading coverage report. Modules: {target_modules}, Packages: {target_packages}, Classes: {target_classes}")
    try:
        import os
        root = Path(project_root)
        if not root.is_absolute():
            root = Path(os.getcwd()) / project_root
        
        logger.info(f"Searching for reports in: {root}")
        
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

        # 2. Fallback to standard locations
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
            
        total_lines_missed = total_lines_covered = total_branches_missed = total_branches_covered = 0
        all_classes_data = []
        with ProcessPoolExecutor() as executor:
            results = list(executor.map(_parse_single_report, report_files))
        for res in results:
            if res:
                total_lines_missed += res["lines_missed"]; total_lines_covered += res["lines_covered"]
                total_branches_missed += res["branches_missed"]; total_branches_covered += res["branches_covered"]
                all_classes_data.extend(res["class_data"])
        
        # Filtering Logic
        exclude_patterns = [r"\.generated\.", r"\.dto\.", r"\.model\.", r"\.exception\."]
        
        targets_m = [t.strip() for t in target_modules.split(",") if t.strip()] if target_modules else []
        targets_p = [t.strip() for t in target_packages.split(",") if t.strip()] if target_packages else []
        targets_c = [t.strip() for t in target_classes.split(",") if t.strip()] if target_classes else []

        filtered_classes = []
        for c_name, cov in all_classes_data:
            # 1. Exclusions (skip generated code, etc.)
            # NOTE: If user explicitly requested a class that looks generated, we might want to allow it.
            # But generally, we skip.
            if any(re.search(p, c_name, re.IGNORECASE) for p in exclude_patterns):
                continue

            # 2. Scope Matching
            # Logic: If ANY filter is provided, the class must match AT LEAST ONE of the provided scopes.
            # If NO filters are provided, we show everything (minus exclusions).
            
            is_included = True # Default to include if no filters
            
            if targets_p or targets_c:
                is_included = False # Filters exist, so default is now exclude
                
                # Check Package Match
                if targets_p and any(c_name.startswith(p) for p in targets_p):
                    is_included = True
                
                # Check Class Match (override)
                if targets_c:
                    for t in targets_c:
                        if c_name == t or c_name.endswith("." + t):
                            is_included = True
                            break
            
            if is_included:
                filtered_classes.append((c_name, cov))

        # Sort: worst coverage first
        filtered_classes.sort(key=lambda x: x[1])
        top_worst = filtered_classes[:20]

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