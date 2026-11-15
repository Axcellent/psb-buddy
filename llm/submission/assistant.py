from __future__ import annotations

from dataclasses import dataclass

import httpx

import config
import kb
import prompts
from llm_client import chat
from retrieval import Retriever


@dataclass
class Answer:
    text: str
    company_docs: list[kb.Document]
    company_chunks: list[kb.Chunk]
    law_chunks: list[kb.Chunk]


class Assistant:
    def __init__(self, documents: list[kb.Document]) -> None:
        self.documents = documents
        self.docs_by_id = {doc.doc_id: doc for doc in documents}
        self.company = [doc for doc in documents if doc.kind == "company"]
        company_size = sum(len(doc.text) for doc in self.company)
        self.company_fulltext = company_size <= config.COMPANY_FULLTEXT_LIMIT
        self.retriever = Retriever(documents, use_company=not self.company_fulltext)
        self.catalog = kb.catalog(documents)

    @classmethod
    def from_archive(cls, path) -> "Assistant":
        return cls(kb.load_documents(path))

    def prepare(self, client: httpx.Client | None) -> None:
        if client is not None:
            self.retriever.build_embeddings(client)

    def context(self, client: httpx.Client | None, question: str):
        turns = prompts.parse_dialog(question)
        found = self.retriever.search(client, prompts.retrieval_query(turns))
        law_chunks = [c for c in found if self.docs_by_id[c.doc_id].kind == "law"]
        company_chunks = [c for c in found if self.docs_by_id[c.doc_id].kind == "company"]
        company_docs = self.company if self.company_fulltext else []
        messages = prompts.build_messages(
            turns, company_docs, company_chunks, law_chunks, self.docs_by_id, self.catalog
        )
        return messages, company_docs, company_chunks, law_chunks

    def answer(self, client: httpx.Client, question: str) -> Answer:
        messages, company_docs, company_chunks, law_chunks = self.context(client, question)
        text = prompts.clean_answer(chat(client, messages))
        return Answer(text, company_docs, company_chunks, law_chunks)
