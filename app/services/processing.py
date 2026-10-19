from uuid import UUID


def process_file(file_id: UUID) -> None:
    """Dispatch a persisted file to the document-processing integration."""
    del file_id
