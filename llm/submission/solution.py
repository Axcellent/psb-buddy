from __future__ import annotations

import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from assistant import Assistant
from llm_client import LLMError, log, make_client, set_deadline

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
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not {"id", "question"} <= set(reader.fieldnames):
            raise ValueError("questions.csv must have id and question columns")
        rows = [(str(r["id"]).strip(), str(r["question"] or "").strip()) for r in reader]
    return [(qid, q) for qid, q in rows if qid]


def write_submission(questions: list[tuple[str, str]], answers: dict[int, str]) -> None:
    with open("submission.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writerow(["id", "answer"])
        for index, (qid, _) in enumerate(questions):
            writer.writerow([qid, answers.get(index) or config.FALLBACK_ANSWER])


def main() -> int:
    started = time.monotonic()
    deadline = started + config.TIME_BUDGET_SECONDS
    set_deadline(started + config.HARD_DEADLINE_SECONDS)
    questions = load_questions(find_file(QUESTION_FILES))
    answers: dict[int, str] = {}
    extracted: set[int] = set()
    log(f"questions: {len(questions)}; model: set; workers: {config.MAX_WORKERS}")
    try:
        assistant = Assistant.from_archive(find_file(KB_FILES))
        laws = sum(1 for d in assistant.documents if d.kind == "law")
        log(
            f"documents: {len(assistant.documents)} ({laws} laws); "
            f"law fragments: {len(assistant.retriever.chunks)}; "
            f"company full text: {assistant.company_fulltext}"
        )
        with make_client() as client:
            assistant.prepare(client)

            def backup(index: int, question: str) -> str:
                extracted.add(index)
                try:
                    return assistant.extract(question)
                except Exception as exc:
                    log(f"question #{index}: extract failed: {type(exc).__name__}")
                    return config.FALLBACK_ANSWER

            def work(index: int, question: str) -> tuple[int, str]:
                if time.monotonic() > deadline:
                    return index, backup(index, question)
                try:
                    text = assistant.answer(client, question).text
                    extracted.discard(index)
                    return index, text
                except LLMError as exc:
                    log(f"question #{index}: {exc}")
                except Exception as exc:
                    log(f"question #{index}: {type(exc).__name__}: {exc}")
                return index, backup(index, question)

            with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as pool:
                futures = [pool.submit(work, i, q) for i, (_, q) in enumerate(questions)]
                for done, future in enumerate(as_completed(futures), 1):
                    index, text = future.result()
                    answers[index] = text
                    if done % 10 == 0 or done == len(questions):
                        log(f"answered {done}/{len(questions)} in {time.monotonic() - started:.0f}s")

            retry = sorted(extracted)
            if len(retry) > len(questions) // 2:
                retry = []
            for index in retry:
                if time.monotonic() > deadline:
                    break
                answers[index] = work(index, questions[index][1])[1]
    finally:
        write_submission(questions, answers)
        missing = sum(1 for i in range(len(questions)) if answers.get(i) in (None, config.FALLBACK_ANSWER))
        log(
            f"submission.csv written: {len(questions)} rows; model answers: "
            f"{len(questions) - len(extracted) - missing}; extracted without model: {len(extracted)}; "
            f"fallback answers: {missing}; total {time.monotonic() - started:.0f}s"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
