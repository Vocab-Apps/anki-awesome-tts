"""Offline Azure request tests; run with python -m unittest tests.test_azure_ssml."""

import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
from xml.etree import ElementTree


SERVICE_DIR = Path(__file__).resolve().parents[1] / 'awesometts' / 'service'
SSML = '{http://www.w3.org/2001/10/synthesis}'
XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'


def load_azure():
    # Avoid importing the Anki/Qt add-on initializer in these request-only tests.
    package = types.ModuleType('_azure_ssml_test')
    package.__path__ = [str(SERVICE_DIR)]
    base = types.ModuleType('_azure_ssml_test.base')
    base.Service = type('Service', (), {})
    modules = {package.__name__: package, base.__name__: base, 'requests': Mock()}
    with patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location(
            '_azure_ssml_test.azure', SERVICE_DIR / 'azure.py')
        azure = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(azure)
    return azure


class AzureSSMLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.azure = load_azure()

    def setUp(self):
        self.output = tempfile.TemporaryDirectory()
        self.addCleanup(self.output.cleanup)
        self.path = str(Path(self.output.name) / 'audio.mp3')
        self.service = self.azure.Azure()
        self.service.config = {}
        self.service._logger = Mock()
        self.service.languagetools = Mock()
        self.service.languagetools.use_plus_mode.return_value = False
        self.service.access_token = 'test-token'
        self.service.token_refresh_required = Mock(return_value=False)
        self.post = Mock(return_value=types.SimpleNamespace(
            status_code=200, content=b'test-audio'))
        for patcher in (patch.object(self.azure.requests, 'post', self.post),
                        patch.object(self.azure.time, 'sleep')):
            patcher.start()
            self.addCleanup(patcher.stop)

    def options(self, voice_name):
        voice = next(v for v in self.service.get_voices()
                     if f', {voice_name})' in v.get_key())
        return self.options_for_key(voice.get_key())

    def options_for_key(self, key):
        return dict(voice=key, azurespeed=1.0, azurepitch=0,
                    region='eastus', key='test-key')

    def synthesize(self, text, options):
        self.service.run(text, options, self.path)
        self.assertEqual(self.post.call_args[0][0],
                         'https://eastus.tts.speech.microsoft.com/cognitiveservices/v1')
        self.assertEqual(self.post.call_args[1]['headers']['Content-Type'],
                         'application/ssml+xml')
        body = self.post.call_args[1]['data']
        self.assertIsInstance(body, bytes)
        return ElementTree.fromstring(body.decode('utf-8'))

    def test_remy_explicit_french_locale_for_short_words(self):
        options = self.options('RemyMultilingualNeural')
        for word in ('portable', 'garage', 'restaurant', 'communication', 'été', 'février'):
            for rate in (0.85, 1.0):
                with self.subTest(word=word, rate=rate):
                    options['azurespeed'] = rate
                    root = self.synthesize(word, options)
                    self.assertEqual(root.tag, SSML + 'speak')
                    self.assertEqual(root.attrib[XML_LANG], 'fr-FR')
                    voice = root.find(SSML + 'voice')
                    self.assertEqual(voice.attrib['name'], options['voice'])
                    lang = voice.find(SSML + 'lang')
                    self.assertEqual(lang.attrib[XML_LANG], 'fr-FR')
                    prosody = lang.find(SSML + 'prosody')
                    self.assertEqual(prosody.text, word)
                    self.assertEqual(prosody.attrib['rate'], f'{rate:0.1f}')
                    self.assertEqual(prosody.attrib['pitch'], '+0Hz')

    def test_non_multilingual_voice_does_not_get_lang_element(self):
        root = self.synthesize('portable', self.options('HenriNeural'))
        self.assertEqual(root.attrib[XML_LANG], 'fr-FR')
        voice = root.find(SSML + 'voice')
        self.assertIsNone(voice.find(SSML + 'lang'))
        self.assertEqual(voice.find(SSML + 'prosody').text, 'portable')

    def test_english_non_multilingual_locales(self):
        for name, locale in (('JennyNeural', 'en-US'), ('LibbyNeural', 'en-GB')):
            with self.subTest(voice=name):
                root = self.synthesize('Hello, this is English.', self.options(name))
                self.assertEqual(root.attrib[XML_LANG], locale)
                voice = root.find(SSML + 'voice')
                self.assertIsNone(voice.find(SSML + 'lang'))
                self.assertEqual(voice.find(SSML + 'prosody').text,
                                 'Hello, this is English.')

    def test_english_multilingual_locales(self):
        for name, locale in (('JennyMultilingualNeural', 'en-US'),
                             ('OllieMultilingualNeural', 'en-GB')):
            for text in ('portable', 'garage', 'Hello, this is English.'):
                with self.subTest(voice=name, text=text):
                    root = self.synthesize(text, self.options(name))
                    self.assertEqual(root.attrib[XML_LANG], locale)
                    lang = root.find(SSML + 'voice').find(SSML + 'lang')
                    self.assertEqual(lang.attrib[XML_LANG], locale)
                    self.assertEqual(lang.find(SSML + 'prosody').text, text)

    def test_all_catalog_voices_match_locale_in_azure_identifier(self):
        # Use the Azure identifier as the independent source of expected locale.
        # Catalog audio_language_code can omit a script (sr_RS vs sr-Latn-RS).
        for voice in self.service.get_voices():
            key = voice.get_key()
            with self.subTest(voice=key):
                match = re.fullmatch(
                    r'Microsoft Server Speech Text to Speech Voice \(([^,]+), [^)]+\)',
                    key)
                locale = match.group(1) if match else key.rsplit('-', 1)[0]
                root = self.synthesize('test', self.options_for_key(key))
                self.assertEqual(root.tag, SSML + 'speak')
                self.assertEqual(root.attrib[XML_LANG], locale)
                element = root.find(SSML + 'voice')
                self.assertEqual(element.attrib['name'], key)
                if 'Multilingual' in key:
                    element = element.find(SSML + 'lang')
                    self.assertEqual(element.attrib[XML_LANG], locale)
                else:
                    self.assertIsNone(element.find(SSML + 'lang'))
                self.assertEqual(element.find(SSML + 'prosody').text, 'test')

    def test_script_specific_serbian_locale(self):
        for name in ('SophieNeural', 'NicholasNeural'):
            with self.subTest(voice=name):
                root = self.synthesize('Dobar dan', self.options(name))
                self.assertEqual(root.attrib[XML_LANG], 'sr-Latn-RS')

    def test_prosody_settings_are_preserved(self):
        for pitch, expected in ((20, '+20Hz'), (-15, '-15Hz')):
            with self.subTest(pitch=pitch):
                options = self.options('JennyMultilingualNeural')
                options.update(azurespeed=1.5, azurepitch=pitch)
                root = self.synthesize('Hello', options)
                prosody = root.find('.//' + SSML + 'prosody')
                self.assertEqual(prosody.attrib['rate'], '1.5')
                self.assertEqual(prosody.attrib['pitch'], expected)

    def test_existing_ssml_markup_is_preserved(self):
        root = self.synthesize('Bonjour<break time="100ms"/> encore',
                               self.options('RemyMultilingualNeural'))
        prosody = root.find('.//' + SSML + 'prosody')
        self.assertEqual(prosody.text, 'Bonjour')
        pause = prosody.find(SSML + 'break')
        self.assertEqual(pause.attrib['time'], '100ms')
        self.assertEqual(pause.tail, ' encore')

    def test_plus_keeps_original_language_code_and_plain_text(self):
        self.service.languagetools.use_plus_mode.return_value = True
        for name, language, text in (
                ('RemyMultilingualNeural', 'fr', 'été'),
                ('JennyMultilingualNeural', 'en', 'Hello'),
                ('OllieMultilingualNeural', 'en', 'Hello'),
                ('HenriNeural', 'fr', 'portable')):
            with self.subTest(voice=name):
                generate = self.service.languagetools.generate_audio_v2
                generate.reset_mock()
                options = self.options(name)
                options.update(azurespeed=0.85, azurepitch=-15)
                self.service.run(text, options, self.path)
                generate.assert_called_once_with(
                    text, 'Azure', 'batch', language, 'n/a',
                    {'name': options['voice']}, {'pitch': -15, 'rate': 0.85}, self.path)
        self.post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
