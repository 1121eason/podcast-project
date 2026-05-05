import os
from google.cloud import secretmanager
from app.core.config import settings

def get_secret(secret_id: str, version_id: str = "latest") -> str:
    if settings.ENVIRONMENT == "dev" and os.environ.get(secret_id):
        return os.environ.get(secret_id)
    
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{settings.GCP_PROJECT_ID}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")
