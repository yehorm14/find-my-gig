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
