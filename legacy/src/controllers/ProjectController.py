from .BaseController import BaseController
from fastapi import UploadFile
from models import ResponseSignal
import os

class ProjectController(BaseController):
  def __init__(self):
    super().__init__()
    
  def get_project_path(self, project_id : str):
    project_dir = os.path.join(self.files_dir,str(project_id))
    os.makedirs(project_dir, exist_ok=True)
    return project_dir