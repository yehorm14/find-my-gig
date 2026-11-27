from django.test import override_settings
from django.urls import reverse

from gigs.models import Application
from gigs.tests.test_views import ViewBaseTestCase


@override_settings(GOOGLE_MAPS_FRONTEND_KEY="test-key")
class MapZeroCoordinateTests(ViewBaseTestCase):
    """Valid 0 latitude/longitude must render a map; None must show the placeholder."""

    def _set_coords(self, lat, lng):
        type(self.listing).objects.filter(pk=self.listing.pk).update(latitude=lat, longitude=lng)

    def _detail(self):
        return self.client.get(reverse('gigs:gig_detail', args=[self.listing.id]))

    def _applications(self):
        Application.objects.get_or_create(applicant=self.musician_user, listing=self.listing)
        self.client.login(username="musicianuser", password="pass123")
        return self.client.get(reverse('gigs:my_applications'))

    def assertMap(self, response, lat, lng):
        self.assertContains(response, 'gig-mini-map')
        self.assertContains(response, f'data-lat="{lat}"')
        self.assertContains(response, f'data-lng="{lng}"')
        self.assertNotContains(response, 'Coordinates pending')

    def assertPlaceholder(self, response):
        self.assertNotContains(response, 'data-lat=')
        self.assertContains(response, 'Coordinates pending')

    def test_detail_zero_latitude_and_longitude_render_map(self):
        self._set_coords(0.0, 0.0)
        self.assertMap(self._detail(), '0.0', '0.0')

    def test_detail_zero_latitude_only_renders_map(self):
        self._set_coords(0.0, -4.25)
        self.assertMap(self._detail(), '0.0', '-4.25')

    def test_detail_zero_longitude_only_renders_map(self):
        self._set_coords(55.86, 0.0)
        self.assertMap(self._detail(), '55.86', '0.0')

    def test_detail_missing_coordinates_show_placeholder(self):
        self._set_coords(None, None)
        self.assertPlaceholder(self._detail())

    def test_detail_partial_coordinates_show_placeholder(self):
        self._set_coords(0.0, None)
        self.assertPlaceholder(self._detail())

    def test_my_applications_zero_coordinates_render_map(self):
        self._set_coords(0.0, 0.0)
        self.assertMap(self._applications(), '0.0', '0.0')

    def test_my_applications_missing_coordinates_show_placeholder(self):
        self._set_coords(None, None)
        self.assertPlaceholder(self._applications())

    @override_settings(GOOGLE_MAPS_FRONTEND_KEY=None)
    def test_missing_key_shows_not_configured_placeholder(self):
        self._set_coords(0.0, 0.0)
        response = self._detail()
        self.assertContains(response, 'Map not configured')
        self.assertNotContains(response, 'data-lat=')
