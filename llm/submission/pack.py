from __future__ import annotations

import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXCLUDE = {"pack.py"}


def main() -> None:
    files = sorted(p for p in HERE.glob("*.py") if p.name not in EXCLUDE)
    files.append(HERE / "requirements.txt")
    target = HERE / "submission.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)
    print(f"{target.name}: {', '.join(p.name for p in files)}")


if __name__ == "__main__":
    main()
