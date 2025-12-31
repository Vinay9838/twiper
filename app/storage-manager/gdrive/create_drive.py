from pathlib import Path

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

BASE_PATH = Path(__file__).parent.resolve()

creds = Credentials.from_service_account_file(
    BASE_PATH / "twiper-service-account.json",
    scopes=["https://www.googleapis.com/auth/drive"]
)

service = build("drive", "v3", credentials=creds)

folder = service.files().create(
    body={
        "name": "XYZBlob",
        "mimeType": "application/vnd.google-apps.folder"
    }
).execute()


service.permissions().create(
    fileId="164kRFfe5VQGSYxyqn2N2GNE8_vIGHHrw",
    body={
        "type": "user",
        "role": "writer",
        "emailAddress": "urworldceleb@gmail.com"
    }
).execute()

print("FOLDER_ID =", folder["id"])
