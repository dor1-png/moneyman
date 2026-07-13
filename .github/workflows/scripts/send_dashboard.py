"""Friday report: fetch latest dashboard + summary from the shared Drive folder
and send them to Dor's Telegram. Credentials come from MONEYMAN_CONFIG."""
import json, os, sys, datetime
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
 
cfg = json.loads(os.environ["MONEYMAN_CONFIG"])
gs = cfg["storage"]["googleSheets"]
tg = cfg["options"]["notifications"]["telegram"]
API = f"https://api.telegram.org/bot{tg['apiKey']}"
CHAT = tg["chatId"]
 
def tg_text(text):
    requests.post(f"{API}/sendMessage", data={"chat_id": CHAT, "text": text}, timeout=30).raise_for_status()
 
try:
    creds = service_account.Credentials.from_service_account_info(
        {"type": "service_account", "client_email": gs["serviceAccountEmail"],
         "private_key": gs["serviceAccountPrivateKey"],
         "token_uri": "https://oauth2.googleapis.com/token"},
        scopes=["https://www.googleapis.com/auth/drive.readonly"])
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
 
    folders = drive.files().list(
        q="sharedWithMe and mimeType='application/vnd.google-apps.folder' and name='Finance Handoff'",
        fields="files(id)").execute()["files"]
    if not folders:
        tg_text("⚠️ Friday report: the 'Finance Handoff' folder is not shared with the service account.")
        sys.exit(0)
    fid = folders[0]["id"]
 
    def latest(name):
        fs = drive.files().list(q=f"'{fid}' in parents and name='{name}' and trashed=false",
            orderBy="modifiedTime desc", fields="files(id,modifiedTime)").execute()["files"]
        return fs[0] if fs else None
 
    dash, summ = latest("Finance Dashboard.html"), latest("summary.txt")
    lines = ["📊 Weekly Finance Report"]
    if summ:
        lines.append(drive.files().get_media(fileId=summ["id"]).execute().decode("utf-8"))
    if dash:
        mod = datetime.datetime.fromisoformat(dash["modifiedTime"].replace("Z", "+00:00"))
        age = (datetime.datetime.now(datetime.timezone.utc) - mod).days
        if age > 3:
            lines.append(f"⚠️ Dashboard is {age} days old — the home computer probably wasn't on this Friday. Open the Claude app to refresh it.")
        tg_text("\n\n".join(lines))
        data = drive.files().get_media(fileId=dash["id"]).execute()
        r = requests.post(f"{API}/sendDocument", data={"chat_id": CHAT, "caption": "Open me in a browser 📈"},
            files={"document": ("Finance Dashboard.html", data, "text/html")}, timeout=60)
        r.raise_for_status()
    else:
        lines.append("⚠️ No dashboard file found in the handoff folder yet.")
        tg_text("\n\n".join(lines))
    print("done")
except Exception as e:
    try: tg_text(f"❌ Friday report failed: {type(e).__name__}: {e}")
    except Exception: pass
    raise
