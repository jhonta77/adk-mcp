import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import dotenv_values

config = dotenv_values('xwiki_agent/.env')
for key, value in config.items():
    if value is not None:
        os.environ[key] = value

base = os.environ['XWIKI_URL']
user = os.environ['XWIKI_USER']
password = os.environ['XWIKI_PASS']

auth = HTTPBasicAuth(user, password)

url = f"{base}/rest/wikis/xwiki/spaces/Main/pages/WebHome"
resp = requests.get(url, auth=auth, headers={'Accept': 'application/xml'})
print('Status:', resp.status_code)
print(resp.text[:500])
