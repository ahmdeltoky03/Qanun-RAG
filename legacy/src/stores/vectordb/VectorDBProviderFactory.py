from .VectorDBInterface import VectorDBInterface
from .providers import QdrantDBProvider, PGVectorProvider
from .VectorDBEnums import VectorDBEnums
from controllers.BaseController import BaseController
from sqlalchemy.orm import sessionmaker

class VectorDBProviderFactory:
  
  def __init__(self, config: dict, db_client: sessionmaker):
    self.config = config
    self.base_controller = BaseController()
    self.db_client=db_client
    
  def create(self, provider: str):
    if provider == VectorDBEnums.QDRANT.value:
      
      return QdrantDBProvider(
      
        db_client=self.base_controller.get_database_path(db_name=self.config.VECTOR_DB_PATH),
        default_vector_size=self.config.EMBEDDING_MODEL_SIZE,
        index_threshold=self.config.VECTOR_DB_PGVEC_INDEX_THRESHOLD,
        distance_method=self.config.VECTOR_DB_DISTANCE_METHOD
      
      )
      
    if provider == VectorDBEnums.PGVECTOR.value:
      
      return PGVectorProvider(
      
        db_client=self.db_client,
        default_vector_size=self.config.EMBEDDING_MODEL_SIZE,
        index_threshold=self.config.VECTOR_DB_PGVEC_INDEX_THRESHOLD,
        distance_method=self.config.VECTOR_DB_DISTANCE_METHOD
        
      )
    return None