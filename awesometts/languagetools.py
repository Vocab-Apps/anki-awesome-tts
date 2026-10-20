import os
import requests
import json
import base64
from typing import Optional
from dataclasses import dataclass

from . import trial

@dataclass
class TrialRequestReponse:
    success: bool
    api_key: Optional[str] = None
    error: Optional[str] = None

class LanguageTools:
    def __init__(self, api_key, logger, client_version, client_uuid):
        self.logger = logger
        # override with VOCABAI_API_HOSTNAME for dev/qa testing
        hostname = os.environ.get('VOCABAI_API_HOSTNAME', 'app.vocab.ai')
        self.vocab_api_base_url = f'https://{hostname}/languagetools-api/v3'
        self.api_key = api_key
        self.client_version = client_version
        self.client_uuid = client_uuid
        self.trial_instant_signed_up = False
        self.api_key_verified = False

    def set_api_key(self, api_key):
        self.api_key = api_key
        self.api_key_verified = False

    def get_api_key(self):
        return self.api_key

    def use_plus_mode(self):
        return len(self.api_key) > 0

    def verify_api_key(self, api_key):
        response = requests.get(self.vocab_api_base_url + '/account', headers={'Authorization': f'Api-Key {api_key}'})
        if response.status_code == 200:
            self.api_key = api_key
            self.api_key_verified = True
            return {
                'key_valid': True,
            }

        return {
            'key_valid': False,
            'msg': f'api key not valid'
        }
    
    def ensure_key_verified(self):
        if self.api_key == None:
            raise ValueError('API Key not set')
        if self.api_key_verified == False:
            self.verify_api_key(self.api_key)

    def account_info(self):
        self.ensure_key_verified()

        response = requests.get(self.vocab_api_base_url + '/account', headers={'Authorization': f'Api-Key {self.api_key}'})
        data = json.loads(response.content)
        return data

    def generate_audio_v2(self, source_text, service, request_mode, language_code, deck_name, voice_key, options, path):
        self.ensure_key_verified()

        data = {
            'text': source_text,
            'service': service,
            'request_mode': request_mode,
            'language_code': language_code,
            'deck_name': deck_name,
            'voice_key': voice_key,
            'options': options
        }

        headers={
            'Authorization': f'Api-Key {self.api_key}',
            'User-Agent': f'anki-awesometts/{self.client_version}',
            'X-Vocab-Addon-ID': self.client_uuid
        }
        full_url = self.vocab_api_base_url + '/audio'
        response = requests.post(full_url, json=data, headers=headers)

        if response.status_code == 200:
            self.logger.info('success, receiving audio')
            with open(path, 'wb') as f:
                f.write(response.content)
        else:
            error_message = f"Status code: {response.status_code} ({response.content})"
            self.logger.error(error_message)
            raise ValueError(error_message)                    


    def build_trial_key_request_data(self, email, password, client_uuid):
        namespace = {}
        exec(base64.b64decode(trial.TRIAL_CHECK_1).decode('utf-8'), namespace)        
        exec(base64.b64decode(trial.REQUEST_TRIAL_PAYLOAD).decode('utf-8'), namespace)
        data = namespace['build_trial_request_payload'](email, client_uuid)
        data['email'] = email
        data['password'] = password
        return data

    def request_trial_key(self, email, password) -> TrialRequestReponse:
        self.logger.info(f'requesting trial key for email {email}')
        
        data = self.build_trial_key_request_data(email, password, self.client_uuid)
        
        # Make sure we have the method to get headers
        if not hasattr(self, 'get_trial_request_headers'):
            # Default headers if method doesn't exist
            headers = {
                'User-Agent': f'anki-awesometts/{self.client_version}',
                'Content-Type': 'application/json'
            }
        else:
            headers = self.get_trial_request_headers()
        
        response = requests.post(self.vocab_api_base_url + '/register_trial', 
                                 json=data,
                                 headers=headers)
        
        try:
            data = json.loads(response.content)
            self.logger.info(f'retrieved {data}, status_code: {response.status_code}')

            if response.status_code == 201:
                # trial key was successfully created
                return TrialRequestReponse(
                    success=True,
                    api_key=data['api_key']
                )
            else:
                error_message = '<b>error:</b> ' + ', '.join([f"{key}: {value}" for key, value in data.items()])
                return TrialRequestReponse(
                    success=False,
                    error=error_message
                )
        except Exception as e:
            self.logger.error(f"Error processing trial key request: {str(e)}")
            return TrialRequestReponse(
                success=False,
                error=f"Error: {str(e)}"
            )
