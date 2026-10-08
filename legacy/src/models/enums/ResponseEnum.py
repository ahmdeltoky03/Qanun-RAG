from enum import Enum

class ResponseSignal(Enum):
  
  FILE_VALIDATED_SUCCESSFULLY = "File validated successfully."
  FILE_TYPE_NOT_SUPPORTED = "File type not allowed."
  FILE_SIZE_EXCEEDED = "File size exceeded."
  FILE_UPLOADED_SUCCESS = "File uploaded successfully."
  FILE_UPLOADED_FAILED = "File upload failed."
  FILE_PROCESSING_FAILED = "File processing failed."
  FILE_PROCESSING_SUCCESS = "File processed successfully."
  NO_FILES_ERROR = "Not Found Files"
  FILE_ID_ERROR = "No File Found With This Id"
  PROJECT_NOT_FOUND_ERROR = "project not found"
  INSERT_INTO_VECTORDB_ERROR = "insert into vectordb error"
  INSERT_INTO_VECTORDB_SUCCESS = "insert into vectordb success"
  VECTORDB_COLLECTION_RETRIEVED = "vector db collection retrieved"
  VECTORDB_SEARCH_ERROR = "search vector db error"
  VECTORDB_SEARCH_SUCCESS = "search vector db success"
  RAG_ANSWER_ERROR = "rag answer error"
  RAG_ANSWER_SUCCESS = "rag answer success"