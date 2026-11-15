from models import Message
from schemas import RawSourceDto, ContextMessageDto, RagResultDto

async def rag_answer(
    question: str,
    history: list[ContextMessageDto]
) -> RagResultDto:

    return RagResultDto(
        text = '"' + question + '" - это очень интересный вопрос, хихиххихи! Учитывая контекст: "' 
                + ' [И] '.join(history) + '"',
        sources=[],
    )