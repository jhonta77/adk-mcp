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

resp_xml = requests.get(f"{base}/rest/wikis/xwiki/spaces", auth=auth, headers={'Accept': 'application/xml'})
print('XML status:', resp_xml.status_code)
print(resp_xml.text[:500])

resp_json = requests.get(f"{base}/rest/wikis/xwiki/spaces", auth=auth, headers={'Accept': 'application/json'})
print('\nJSON status:', resp_json.status_code)
print(resp_json.text[:500])
