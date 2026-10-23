"""Offline Azure request tests; run with python -m unittest tests.test_azure_ssml."""

import importlib.util
from pathlib import Path
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
                     if v.get_key() == voice_name or f', {voice_name})' in v.get_key())
        return dict(voice=voice.get_key(), azurespeed=1.0, azurepitch=0,
                    region='eastus', key='test-key')

    def synthesize(self, voice_name):
        options = self.options(voice_name)
        self.service.run('portable', options, self.path)
        root = ElementTree.fromstring(self.post.call_args[1]['data'].decode('utf-8'))
        self.assertEqual(root.tag, SSML + 'speak')
        self.assertEqual(root.find(SSML + 'voice').attrib['name'], options['voice'])
        return root

    def test_multilingual_speaking_locale(self):
        for name, locale in (('RemyMultilingualNeural', 'fr-FR'),
                             ('JennyMultilingualNeural', 'en-US'),
                             ('OllieMultilingualNeural', 'en-GB')):
            with self.subTest(voice=name):
                root = self.synthesize(name)
                self.assertEqual(root.attrib[XML_LANG], locale)
                lang = root.find(SSML + 'voice').find(SSML + 'lang')
                self.assertEqual(lang.attrib[XML_LANG], locale)
                self.assertEqual(lang.find(SSML + 'prosody').text, 'portable')

    def test_non_multilingual_voices_have_no_lang_element(self):
        for name, locale in (('JennyNeural', 'en-US'), ('LibbyNeural', 'en-GB')):
            with self.subTest(voice=name):
                root = self.synthesize(name)
                self.assertEqual(root.attrib[XML_LANG], locale)
                voice = root.find(SSML + 'voice')
                self.assertIsNone(voice.find(SSML + 'lang'))
                self.assertEqual(voice.find(SSML + 'prosody').text, 'portable')

    def test_script_locale_and_short_voice_name(self):
        for name, locale in (('SophieNeural', 'sr-Latn-RS'),
                             ('en-US-Jenny:DragonHDLatestNeural', 'en-US')):
            with self.subTest(voice=name):
                root = self.synthesize(name)
                self.assertEqual(root.attrib[XML_LANG], locale)

    def test_plus_keeps_language_code_and_plain_text(self):
        self.service.languagetools.use_plus_mode.return_value = True
        for name, language, text in (('RemyMultilingualNeural', 'fr', 'été'),
                                     ('JennyMultilingualNeural', 'en', 'Hello')):
            with self.subTest(voice=name):
                generate = self.service.languagetools.generate_audio_v2
                generate.reset_mock()
                options = self.options(name)
                self.service.run(text, options, self.path)
                generate.assert_called_once_with(
                    text, 'Azure', 'batch', language, 'n/a',
                    {'name': options['voice']}, {'pitch': 0, 'rate': 1.0}, self.path)
        self.post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
