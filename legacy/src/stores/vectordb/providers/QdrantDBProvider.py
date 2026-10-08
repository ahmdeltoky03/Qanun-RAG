from ..VectorDBInterface import VectorDBInterface
from ..VectorDBEnums import VectorDBEnums, DistanceMethodEnums
from qdrant_client import models, QdrantClient
from models.db_schemas import RetrievedDocument
from typing import List
import logging


class QdrantDBProvider(VectorDBInterface):
  
  def __init__(self, db_client , default_vector_size: int = 784 ,
                distance_method : str = None, index_threshold : int= 100):
    
    self.client = None
    self.db_client = db_client
    self.distance_method = distance_method
    self.default_vector_size=default_vector_size

    if distance_method == DistanceMethodEnums.COSINE.value:
      distance_method = models.Distance.COSINE
    
    if distance_method == DistanceMethodEnums.DOT.value:
      distance_method = models.Distance.DOT
      
    self.logger = logging.getLogger('uvicorn')
    
    
    
  async def connect(self):
    self.client = QdrantClient(path=self.db_client)
    
    
  async def disconnect(self):
    self.client = None
    
    # raise NotImplementedError
  
    
  async def is_collection_existed(self, collection_name: str) -> bool:
    return self.client.collection_exists(collection_name=collection_name)
  
  
  async def list_all_collections(self) -> List:
    return self.client.get_collections()
  
  
  async def get_collection_info(self, collection_name: str) -> dict:
    return self.client.get_collection(collection_name=collection_name)
  
  
  async def delete_collection(self, collection_name: str):
    if self.is_collection_existed(collection_name=collection_name):
      self.logger.info(f"Deleting Collection: {collection_name}")
      self.client.delete_collection(collection_name=collection_name)
    # else:
    #   self.logger.error("Collection Not Exist In Vector DB")


  async def create_collection(self, collection_name: str,
                        embedding_size : int,
                        do_reset: bool = False):
    if do_reset:
      _ = self.delete_collection(collection_name=collection_name)
    
    if not self.is_collection_existed(collection_name=collection_name):
      self.logger.info(f"Creating New Qdrant collection: {collection_name}")
      _ = self.client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(size=embedding_size, distance=self.distance_method))

      return True
    
    return False
  

  async def insert_one(self,collection_name: str, text: str, vector: list,
                      metadata: dict = None,
                      record_id : str = None):
    if not self.is_collection_existed(collection_name=collection_name):
      self.logger.error(f"Cannot Insert New Record to Non exist Collection Name {collection_name}")
      return False
    
    try:
      _ = self.client.upload_records(collection_name=collection_name,
                                    records=[
                                      models.Record(
                                        id = [record_id],
                                        vector=vector,
                                        payload={
                                          "text":text,
                                          "metadata":metadata
                                        }
                                      )
                                    ])
    except Exception as e:
      self.logger.error(f"Error While Inserting batch {e}")
      return False
    
    return True
  
  async def insert_many(self,collection_name: str, texts: list, vectors: list,
                      metadata: list = None,
                      record_ids : list = None,
                      batch_size : int = 50):
    
    if not metadata:
      metadata = [None] * len(texts)
      
    if not record_ids:
      record_ids = list(range(0, len(texts)))
      
    for i in range(0, len(texts), batch_size):
      batch_texts = texts[i: i + batch_size]
      batch_vectors = vectors[i: i + batch_size]
      batch_metadata = metadata[i: i + batch_size]
      batch_record_ids = record_ids[i: i + batch_size]
      
      batch_records = [

      
      models.Record(
        id = batch_record_ids[x],
        vector=batch_vectors[x],
        payload={
          "text":batch_texts[x],
          "metadata":batch_metadata[x]
        }
        )
        for x in range(len(texts))
      ]
      
      try:
        _ = self.client.upload_records(collection_name=collection_name,
                                      records=batch_records)
      except Exception as e:
        self.logger.error(f"Error While Inserting Batch {e}")
        return False
      
    return True
  
  async def search_by_vector(self,collection_name: str, vector : list, limit: int = 5) :
    results = self.client.search(
      collection_name=collection_name,
      query_vector=vector,
      limit=limit
    )
    
    if not results or len(results) == 0:
      return None
    
    return [
      
      RetrievedDocument(**{
        "score": result.score ,
        "text": result.payload["text"]
      })
      for result in results
    ]