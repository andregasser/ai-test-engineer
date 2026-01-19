from concurrent.futures import ProcessPoolExecutor
import xml.etree.ElementTree as ET
from pathlib import Path
import re

from langchain_core.tools import tool

from shared_utils.prompt_utils import get_inherited_prompt
from shared_utils.schema_utils import CoverageSummaryResponse

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
def read_coverage_report(project_root: str, target_classes: str = None) -> CoverageSummaryResponse:
    """
    Parses JaCoCo XML reports. 
    It checks TESTING_STANDARDS.md for custom report locations first.
    project_root should be the path to the project directory.
    target_classes: Optional comma-separated list of simple or fully qualified class names to filter results (e.g. "UserService, AuthController").
    """
    try:
        root = Path(project_root)
        standards_file = root / "TESTING_STANDARDS.md"
        report_files = []

        # 1. Try to read path from TESTING_STANDARDS.md
        if standards_file.exists():
            try:
                content = standards_file.read_text()
                # Simple regex to find path in markdown list or text
                # Looks for patterns like: "Report Path: path/to/report.xml" or "- Path: path/to/report.xml"
                match = re.search(r"(?:Report Path|Jacoco Report):\s*([^\s\n]+)", content, re.IGNORECASE)
                if match:
                    custom_path = root / match.group(1).strip()
                    if custom_path.exists():
                        report_files = [custom_path]
            except Exception:
                pass # Fallback if parsing fails

        # 2. Fallback to standard locations if no custom path found or valid
        if not report_files:
            possible_root = root / "build/reports/jacoco/root/jacocoRootReport.xml"
            if possible_root.exists():
                report_files = [possible_root]
            else:
                report_files = list(root.glob("**/jacocoTestReport.xml"))
        
        if not report_files:
            return CoverageSummaryResponse(success=False, error="No reports found. Checked TESTING_STANDARDS.md and standard paths.")
            
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
        filtered_classes = []
        if target_classes:
            targets = [t.strip() for t in target_classes.split(",") if t.strip()]
            for c_name, cov in all_classes_data:
                # Check if c_name matches ANY target
                is_match = False
                for t in targets:
                    if c_name == t or c_name.endswith("." + t):
                        is_match = True
                        break
                if is_match:
                    filtered_classes.append((c_name, cov))
        else:
            # Default behavior: worst 20
            filtered_classes = sorted(all_classes_data, key=lambda x: x[1])[:20]

        overall_line = total_lines_covered / (total_lines_missed + total_lines_covered) if (total_lines_missed + total_lines_covered) > 0 else 0.0
        overall_branch = total_branches_covered / (total_branches_missed + total_branches_covered) if (total_branches_missed + total_branches_covered) > 0 else 0.0
        
        return CoverageSummaryResponse(
            success=True, 
            line_coverage=overall_line, 
            branch_coverage=overall_branch, 
            worst_classes=[c for c, _ in filtered_classes]
        )
    except Exception as e:
        return CoverageSummaryResponse(success=False, error=str(e))

COVERAGE_ROLE = "You are a coverage analysis agent for a Java/Gradle project."
COVERAGE_PROTOCOL = "1. Analyze coverage using `read_coverage_report`. Use the `target_classes` parameter to verify specific improvements in batch."
COVERAGE_RULES = """
- **GAP IDENTIFICATION:** Beyond returning metrics, identify specific 'Hotspot Methods' (methods with 0% coverage in a low-coverage class) to give the Test Writer a clear target.
- **IMPROVEMENT VERIFICATION:** Explicitly compare the current line/branch counts with the previous iteration to calculate the exact percentage-point delta achieved.
- **ONLY READ:** You do NOT run builds. - **NO OTHER TOOLS:** Do NOT attempt other tools.
"""

COVERAGE_SYSTEM_PROMPT = get_inherited_prompt(COVERAGE_ROLE, COVERAGE_PROTOCOL, COVERAGE_RULES)

COVERAGE_SUBAGENT = {
    "name": "coverage-subagent",
    "description": "Parses and analyzes JaCoCo coverage reports.",
    "system_prompt": COVERAGE_SYSTEM_PROMPT,
    "tools": [read_coverage_report],
}