import re
from pathlib import Path

REPORT_DIR = Path(__file__).resolve().parent.parent
SOURCE = REPORT_DIR / "report.md"
TARGET = REPORT_DIR / "rendered" / "report.md"
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

if __name__ == "__main__":
    TARGET.parent.mkdir(exist_ok=True)
    TARGET.write_text(COMMENT.sub("", SOURCE.read_text()))
    print(TARGET)
