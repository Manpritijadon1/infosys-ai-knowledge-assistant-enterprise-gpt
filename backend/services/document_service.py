
import os
import tempfile
from pathlib import Path
from uuid import uuid4

import boto3
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.database.models import Document, DocumentChunk
from ingestion_pipeline.chunking.text_chunker import chunk_text
from ingestion_pipeline.document_parsing.pdf_parser import extract_text_from_pdf
from ingestion_pipeline.embedding_jobs.embedding_job import generate_document_embeddings

ALLOWED_EXTENSIONS = {".pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("R2_ENDPOINT_URL"),
        aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )


async def save_document(
    file: UploadFile,
    title: str,
    department: str,
    document_type: str,
    current_user,
    db: Session,
    access_scope: str = "all_users",
) -> dict:
    """Validate, store, parse, chunk, and embed an uploaded PDF document."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is missing",
        )

    extension = Path(file.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed",
        )

    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds 10 MB limit",
        )

    stored_filename = f"{uuid4().hex}.pdf"
    storage_key = f"documents/{stored_filename}"
    bucket_name = os.getenv("R2_BUCKET_NAME")

    if not bucket_name or not os.getenv("R2_ENDPOINT_URL"):
        raise RuntimeError("Cloudflare R2 environment variables are missing")

    document = None
    uploaded_to_r2 = False
    file_path = None

    try:
        # Temporary file is used only for existing PDF text extraction
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            file_path = Path(temp_file.name)
            temp_file.write(content)

        pages = extract_text_from_pdf(str(file_path))

        if not pages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No readable text found in the PDF",
            )

        chunks = chunk_text(
            pages,
            chunk_size=1000,
            chunk_overlap=200,
        )

        # Upload original PDF to private Cloudflare R2 bucket
        get_r2_client().put_object(
            Bucket=bucket_name,
            Key=storage_key,
            Body=content,
            ContentType="application/pdf",
        )
        uploaded_to_r2 = True

        document = Document(
            document_id=f"DOC-{uuid4().hex[:12].upper()}",
            title=title.strip(),
            filename=file.filename,
            department=department.strip() if department else "General",
            document_type=document_type.strip() if document_type else "SOP",
            storage_key=storage_key,
            uploaded_by=current_user.id,
            access_scope=access_scope,
        )

        db.add(document)
        db.flush()

        for chunk in chunks:
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk["chunk_index"],
                    page_number=chunk["page_number"],
                    content=chunk["content"],
                )
            )

        db.commit()
        db.refresh(document)

        # Generate and store embeddings for the uploaded document
        embeddings_generated = generate_document_embeddings(
            db=db,
            document_id=document.id,
        )

        return {
            "document_id": document.document_id,
            "title": document.title,
            "filename": document.filename,
            "department": document.department,
            "document_type": document.document_type,
            "total_pages": len(pages),
            "total_chunks": len(chunks),
            "embeddings_generated": embeddings_generated,
        }

    except Exception:
        db.rollback()

        if document is not None and document.id is not None:
            try:
                db.delete(document)
                db.commit()
            except Exception:
                db.rollback()

        if uploaded_to_r2:
            try:
                get_r2_client().delete_object(
                    Bucket=bucket_name,
                    Key=storage_key,
                )
            except Exception:
                pass

        raise

    finally:
        if file_path and file_path.exists():
            file_path.unlink()


def delete_document_by_id(doc_id: int, db: Session) -> None:
    """Delete a document from R2 and its database records."""
    document = db.query(Document).filter(Document.id == doc_id).first()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if document.storage_key:
        try:
            get_r2_client().delete_object(
                Bucket=os.getenv("R2_BUCKET_NAME"),
                Key=document.storage_key,
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not delete document from cloud storage",
            )

    db.delete(document)
    db.commit()
