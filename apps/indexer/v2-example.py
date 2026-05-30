# Файл: apps/indexer/main.py
import sys
import json
import signal
import logging
from haystack import Pipeline, Document
from haystack.components.embedders import TEIDocumentEmbedder
from haystack_integrations.components.writers.qdrant import QdrantDocumentWriter

import config
from vector import compute_sparse_vector # Твой кастомный расчет для гибрида

logging.basicConfig(level=logging.INFO, format='{"time": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}')
logger = logging.getLogger("indexer")

graceful_exit = False
def handle_signal(signum, frame):
    global graceful_exit
    graceful_exit = True

signal.signal(signal.SIGTERM, handle_signal)

def build_haystack_pipeline():
    """
    Строим декларативный конвейер инжестии Haystack 2.0.
    Убираем ручные requests.post и циклы.
    """
    pipeline = Pipeline()

    # Шаг 1: Колокейтд TEI сидекар для эмбеддингов
    pipeline.add_component("embedder", TEIDocumentEmbedder(
        url=config.TEI_ENDPOINT,
        model="BAAI/bge-small-en-v1.5"
    ))

    # Шаг 2: Нативный врайтер в Qdrant
    pipeline.add_component("writer", QdrantDocumentWriter(
        host=config.QDRANT_HOST,
        port=config.QDRANT_PORT,
        collection=config.COLLECTION_NAME,
        prefer_grpc=True
    ))

    pipeline.connect("embedder.documents", "writer.documents")
    return pipeline

def process_sqs_message(message_body, pipeline):
    try:
        body = json.loads(message_body)
    except Exception:
        return True # Удаляем битый JSON

    doc_block = body.get("document", {})
    file_id = doc_block.get("file_id", "manual")
    file_name = doc_block.get("file_name", "unknown")
    chunks = body.get("chunks", [])

    if not chunks:
        return True

    # Перекладываем в нативные объекты Haystack Document
    haystack_docs = []
    for chunk in chunks:
        text = chunk.get("content", "")
        # Вычисляем разреженный вектор (твоя фича для гибридного поиска)
        sparse_res = compute_sparse_vector(text)

        doc = Document(
            content=text,
            meta={
                "file_id": file_id,
                "file_name": file_name,
                "chunk_index": chunk["chunk_index"],
                "page_number": chunk.get("page_number", 1)
            }
        )
        # Насильно пихаем sparse структуру, так как её QdrantWriter подхватит в sparse_embedding
        doc.sparse_embedding = sparse_res
        haystack_docs.append(doc)

    # Запуск конвейера — Haystack сам разобьет на батчи, сходит в TEI и запишет в Qdrant
    try:
        pipeline.run({"embedder": {"documents": haystack_docs}})
        return True
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        return False # Оставляем в очереди для ретрая

def main():
    import boto3
    sqs = boto3.client("sqs", region_name=config.AWS_DEFAULT_REGION)
    pipeline = build_haystack_pipeline()

    while not graceful_exit:
        res = sqs.receive_message(QueueUrl=config.AWS_SQS_STAGE_2_URL, MaxNumberOfMessages=1, WaitTimeSeconds=10)
        messages = res.get("Messages", [])
        if not messages:
            break # Очередь пустая -> KEDA тушит джобу. Честный Zero-Daemon.

        msg = messages[0]
        if process_sqs_message(msg["Body"], pipeline):
            sqs.delete_message(QueueUrl=config.AWS_SQS_STAGE_2_URL, ReceiptHandle=msg["ReceiptHandle"])

if __name__ == "__main__":
    main()
