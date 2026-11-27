from datetime import date
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from gigs.models import Band, Listing


def make_listing(location="Glasgow & Co"):
    user = User.objects.create_user(username="geoband", password="pw12345!")
    band = Band.objects.create(user=user, name="Geo Band", bio="b", location="Glasgow")
    return Listing(
        band=band, title="Gig", req_instruments="Guitar", deadline=date(2030, 1, 1),
        is_urgent=False, location=location,
    )


class GeocodingTest(TestCase):
    @override_settings(GOOGLE_MAPS_BACKEND_KEY=None)
    def test_no_key_skips_request_and_saves(self):
        listing = make_listing()
        with mock.patch("gigs.models.requests.get") as get:
            listing.save()
        get.assert_not_called()
        self.assertIsNone(listing.latitude)
        self.assertIsNotNone(listing.pk)

    @override_settings(GOOGLE_MAPS_BACKEND_KEY="test-key")
    def test_address_is_passed_as_param_with_timeout(self):
        listing = make_listing()
        fake = mock.Mock()
        fake.json.return_value = {
            "status": "OK",
            "results": [{"geometry": {"location": {"lat": 55.86, "lng": -4.25}}}],
        }
        with mock.patch("gigs.models.requests.get", return_value=fake) as get:
            listing.save()
        _, kwargs = get.call_args
        self.assertEqual(kwargs["params"]["address"], "Glasgow & Co")
        self.assertEqual(kwargs["params"]["key"], "test-key")
        self.assertEqual(kwargs["timeout"], 5)
        self.assertEqual(listing.latitude, 55.86)
        self.assertEqual(listing.longitude, -4.25)

    @override_settings(GOOGLE_MAPS_BACKEND_KEY="test-key")
    def test_network_error_does_not_block_save(self):
        import requests
        listing = make_listing()
        with mock.patch("gigs.models.requests.get", side_effect=requests.exceptions.Timeout):
            listing.save()
        self.assertIsNotNone(listing.pk)
        self.assertIsNone(listing.latitude)

    @override_settings(GOOGLE_MAPS_BACKEND_KEY="test-key")
    def test_provider_error_status_does_not_block_save(self):
        listing = make_listing()
        fake = mock.Mock()
        fake.json.return_value = {"status": "REQUEST_DENIED", "error_message": "The provided API key is invalid."}
        with mock.patch("gigs.models.requests.get", return_value=fake):
            with self.assertLogs("gigs.models", level="ERROR") as logs:
                listing.save()
        self.assertIn("REQUEST_DENIED", logs.output[0])
        self.assertIsNotNone(listing.pk)
        self.assertIsNone(listing.latitude)
        self.assertIsNone(listing.longitude)

    @override_settings(GOOGLE_MAPS_BACKEND_KEY="test-key")
    def test_non_json_provider_response_does_not_block_save(self):
        listing = make_listing()
        fake = mock.Mock()
        fake.json.side_effect = ValueError("not json")
        with mock.patch("gigs.models.requests.get", return_value=fake):
            listing.save()
        self.assertIsNotNone(listing.pk)
        self.assertIsNone(listing.latitude)

    @override_settings(GOOGLE_MAPS_BACKEND_KEY="test-key")
    def test_unmocked_network_attempt_fails_the_test(self):
        """The offline runner must turn a real request into an error, not a silent fallback."""
        import requests
        from find_my_gig.test_runner import NetworkBlockedError
        with self.assertRaises(NetworkBlockedError):
            requests.get("https://maps.googleapis.com/maps/api/geocode/json", timeout=1)

    def test_environment_key_is_ignored_under_test(self):
        from django.conf import settings
        self.assertIsNone(settings.GOOGLE_MAPS_BACKEND_KEY)
