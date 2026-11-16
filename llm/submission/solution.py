from __future__ import annotations

import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from assistant import Assistant
from llm_client import log, make_client, set_deadline

QUESTION_FILES = ("questions.csv",)
KB_FILES = ("knowledge-base.zip", "kb.zip", "knowledge_base.zip")


def find_file(names: tuple[str, ...]) -> Path:
    roots = (config.DATA_DIR, Path(__file__).resolve().parent / config.DATA_DIR, Path.cwd())
    for root in roots:
        for name in names:
            path = root / name
            if path.is_file():
                return path
    raise FileNotFoundError(f"none of {', '.join(names)} found")


def load_questions(path: Path) -> list[tuple[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames or not {"id", "question"} <= set(reader.fieldnames):
            raise ValueError("questions.csv must have id and question columns")
        rows = [(row["id"], row["question"] or "") for row in reader]
    identifiers = [qid for qid, _ in rows]
    if any(not qid or not qid.strip() for qid in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("questions.csv must contain unique nonempty IDs")
    return rows


def write_submission(questions: list[tuple[str, str]], answers: dict[int, str]) -> None:
    with open("submission.csv", "w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writerow(["id", "answer"])
        for index, (qid, _) in enumerate(questions):
            text = answers.get(index) or config.FALLBACK_ANSWER
            writer.writerow([qid, text[:10000]])


def main() -> int:
    started = time.monotonic()
    deadline = started + config.TIME_BUDGET_SECONDS
    set_deadline(started + config.HARD_DEADLINE_SECONDS)
    questions = load_questions(find_file(QUESTION_FILES))
    answers: dict[int, str] = {}
    log(f"questions: {len(questions)}; workers: {config.MAX_WORKERS}")
    try:
        assistant = Assistant.from_archive(find_file(KB_FILES))
        with make_client() as client:
            assistant.prepare(client)

            def work(index: int, question: str) -> tuple[int, str]:
                if time.monotonic() > deadline:
                    return index, config.FALLBACK_ANSWER
                try:
                    text = assistant.answer(client, question).text
                    return index, text
                except Exception as exc:
                    # Технический сбой не является доказательством отсутствия нормы.
                    log(f"question #{index}: {type(exc).__name__}")
                    return index, config.FALLBACK_ANSWER

            with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as pool:
                futures = [pool.submit(work, index, question) for index, (_, question) in enumerate(questions)]
                for done, future in enumerate(as_completed(futures), 1):
                    index, text = future.result()
                    answers[index] = text
                    if done % 10 == 0 or done == len(questions):
                        log(f"answered {done}/{len(questions)} in {time.monotonic() - started:.0f}s")
    finally:
        write_submission(questions, answers)
        missing = sum(1 for index in range(len(questions)) if answers.get(index) in (None, config.FALLBACK_ANSWER))
        log(f"submission.csv written: {len(questions)} rows; technical errors: {missing}; total {time.monotonic() - started:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
