"""P0.5 regression tests: safe production settings resolution."""

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

import config.settings as settings_module


class SettingsResolutionTests(SimpleTestCase):
    def test_debug_defaults_to_false(self):
        self.assertFalse(settings_module._resolve_debug({}))

    def test_debug_true_only_for_one(self):
        self.assertTrue(settings_module._resolve_debug({"DJANGO_DEBUG": "1"}))
        self.assertFalse(settings_module._resolve_debug({"DJANGO_DEBUG": "0"}))
        self.assertFalse(settings_module._resolve_debug({"DJANGO_DEBUG": "true"}))

    def test_secret_required_when_debug_off(self):
        with self.assertRaises(ImproperlyConfigured):
            settings_module._resolve_secret_key({"DJANGO_SECRET_KEY": ""}, False)

    def test_secret_dev_fallback_when_debug_on(self):
        key = settings_module._resolve_secret_key({"DJANGO_SECRET_KEY": ""}, True)
        self.assertTrue(key)

    def test_explicit_secret_is_used_in_production(self):
        self.assertEqual(
            settings_module._resolve_secret_key({"DJANGO_SECRET_KEY": "s3cret"}, False),
            "s3cret",
        )

    def test_loaded_settings_have_a_secret(self):
        # The service must never boot with an empty signing key.
        self.assertTrue(settings_module.SECRET_KEY)
