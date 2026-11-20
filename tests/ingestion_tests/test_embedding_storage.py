
from backend.database.connection import SessionLocal
from backend.database.models import Document, DocumentChunk
from ingestion_pipeline.embedding_jobs.embedding_job import generate_document_embeddings


def main():
    db = SessionLocal()

    try:
        document = (
            db.query(Document)
            .filter(Document.document_id == "DOC-106EA6EBF40D")
            .first()
        )

        if document is None:
            print("Document not found: DOC-106EA6EBF40D")
            return

        print(f"Document found: {document.filename}")
        print(f"Database document ID: {document.id}")

        count = generate_document_embeddings(db, document.id)

        print("Embeddings generated:", count)

        saved_count = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.document_id == document.id,
                DocumentChunk.embedding.isnot(None)
            )
            .count()
        )

        print("Embeddings verified:", saved_count)

        if saved_count == 0:
            print("WARNING: No embeddings were found in the database.")
        elif saved_count != count:
            print("WARNING: Generated and saved embedding counts differ.")
        else:
            print("SUCCESS: Embeddings generated and verified.")

    except Exception as e:
        print(f"Embedding generation failed: {e}")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
