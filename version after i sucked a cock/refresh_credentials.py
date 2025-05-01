from google_auth_oauthlib.flow import InstalledAppFlow
import json

SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']
CLIENT_SECRETS_FILE = '/home/impostorboy/prjcts/Leather_outfit_v2_backup/client_secrets.json'
CREDENTIALS_FILE = '/home/impostorboy/prjcts/Leather_outfit_v2_backup/credentials.json'

flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
credentials = flow.run_local_server(port=0)
with open(CREDENTIALS_FILE, 'w') as f:
    json.dump({
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }, f)
print(f'Credentials saved to {CREDENTIALS_FILE}')
