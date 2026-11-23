import json
from datetime import date
from unittest import mock

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from gigs.models import Application, Band, Listing, Musician
from gigs.tests.test_views import ViewBaseTestCase


class MalformedAndWrongRoleRequests(ViewBaseTestCase):
    def test_delete_listing_by_musician_returns_json_error(self):
        self.client.login(username="musicianuser", password="pass123")
        response = self.client.post(reverse('gigs:delete_listing', args=[self.listing.id]))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['success'])
        self.assertTrue(Listing.objects.filter(id=self.listing.id).exists())

    def test_create_gig_listing_malformed_json(self):
        self.client.login(username="banduser", password="pass123")
        response = self.client.post(reverse('gigs:create_gig_listing'), data="{not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'success': False, 'error': 'invalid_json'})

    def test_create_gig_listing_bad_date(self):
        self.client.login(username="banduser", password="pass123")
        payload = {'title': 't', 'req_instruments': 'Guitar', 'date': 'not-a-date',
                   'description': 'd', 'location': 'Glasgow'}
        response = self.client.post(reverse('gigs:create_gig_listing'), data=json.dumps(payload),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_send_interest_malformed_json(self):
        self.client.login(username="banduser", password="pass123")
        response = self.client.post(reverse('gigs:send_interest', args=[self.musician.id]),
                                    data="][", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'success': False, 'error': 'invalid_json'})


class ApplicationUniqueness(ViewBaseTestCase):
    def test_database_rejects_duplicate_application(self):
        Application.objects.create(applicant=self.musician_user, listing=self.listing)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Application.objects.create(applicant=self.musician_user, listing=self.listing)

    def test_apply_race_returns_already_applied(self):
        """Two concurrent requests can both pass the exists() check; the DB constraint catches the loser."""
        self.client.login(username="musicianuser", password="pass123")
        with mock.patch("gigs.views.Application.objects.create", side_effect=IntegrityError):
            response = self.client.post(reverse('gigs:apply_gig', args=[self.listing.id]))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'success': False, 'error': 'already_applied'})


def fake_geocode_response(lat, lng):
    fake = mock.Mock()
    fake.json.return_value = {"status": "OK", "results": [{"geometry": {"location": {"lat": lat, "lng": lng}}}]}
    return fake


@override_settings(GOOGLE_MAPS_BACKEND_KEY="test-key")
class GeocodingLifecycle(ViewBaseTestCase):
    def new_listing(self, **kwargs):
        defaults = dict(band=self.band, title="x", deadline=date(2030, 1, 1), is_urgent=False,
                        description="d", req_instruments="Guitar", location="Glasgow")
        defaults.update(kwargs)
        return Listing(**defaults)

    def test_location_change_regeocodes(self):
        listing = self.new_listing()
        with mock.patch("gigs.models.requests.get", return_value=fake_geocode_response(55.8, -4.2)):
            listing.save()
        listing.location = "Edinburgh"
        with mock.patch("gigs.models.requests.get", return_value=fake_geocode_response(55.9, -3.2)) as get:
            listing.save()
        get.assert_called_once()
        self.assertEqual(listing.latitude, 55.9)

    def test_unchanged_location_is_not_geocoded_again(self):
        listing = self.new_listing()
        with mock.patch("gigs.models.requests.get", return_value=fake_geocode_response(55.8, -4.2)):
            listing.save()
        with mock.patch("gigs.models.requests.get") as get:
            listing.title = "renamed"
            listing.save()
        get.assert_not_called()

    def test_failed_lookup_is_not_retried_on_every_save(self):
        listing = self.new_listing(location="Nowhere xyz")
        fake = mock.Mock()
        fake.json.return_value = {"status": "ZERO_RESULTS"}
        with mock.patch("gigs.models.requests.get", return_value=fake) as get:
            listing.save()
            listing.save()
        self.assertEqual(get.call_count, 1)
        self.assertIsNone(listing.latitude)

    def test_zero_coordinates_count_as_geocoded(self):
        listing = self.new_listing(latitude=0.0, longitude=0.0)
        with mock.patch("gigs.models.requests.get") as get:
            listing.save()
        get.assert_not_called()
        self.assertEqual(listing.latitude, 0.0)

    def test_changed_location_with_failed_lookup_clears_stale_coordinates(self):
        listing = self.new_listing()
        with mock.patch("gigs.models.requests.get", return_value=fake_geocode_response(55.8, -4.2)):
            listing.save()
        listing.location = "Nowhere xyz"
        fake = mock.Mock()
        fake.json.return_value = {"status": "ZERO_RESULTS"}
        with mock.patch("gigs.models.requests.get", return_value=fake):
            listing.save()
        self.assertIsNone(listing.latitude)


class PopulationScriptGuard(TestCase):
    def run_populate(self, **kwargs):
        import population_script
        with mock.patch.object(population_script, "download_image", return_value=None):
            population_script.populate(**kwargs)

    def test_does_not_wipe_existing_users_without_reset(self):
        User.objects.create_user(username="real_user", password="pw12345!")
        self.run_populate()
        self.assertTrue(User.objects.filter(username="real_user").exists())
        self.assertEqual(Band.objects.count(), 0)

    def test_reset_reseeds(self):
        User.objects.create_user(username="real_user", password="pw12345!")
        self.run_populate(reset=True)
        self.assertFalse(User.objects.filter(username="real_user").exists())
        self.assertEqual(Band.objects.count(), 10)

    def test_seeded_reviews_match_accepted_applications(self):
        from gigs.models import Application, Review
        self.run_populate()
        self.assertTrue(Application.objects.filter(status=Application.ACCEPTED).exists())
        for review in Review.objects.filter(listing__isnull=False):
            applicant = review.reviewer if review.reviewer != review.listing.band.user else review.reviewee
            self.assertTrue(Application.objects.filter(
                applicant=applicant, listing=review.listing, status=Application.ACCEPTED).exists(), review)

    def test_seeded_gigs_are_all_upcoming(self):
        """Seed deadlines are relative to today, so the default listing is never empty."""
        from django.utils import timezone
        self.run_populate()
        self.assertEqual(Listing.objects.count(), 30)
        self.assertFalse(Listing.objects.filter(deadline__lt=timezone.localdate()).exists())

    def test_only_demo_accounts_have_usable_passwords(self):
        self.run_populate()
        usable = set(User.objects.filter(is_superuser=False).exclude(password__startswith="!")
                     .values_list("username", flat=True))
        self.assertEqual(usable, {"band_user_1", "musician_1"})


class AjaxErrorStatusCodes(ViewBaseTestCase):
    """Every AJAX failure carries a meaningful HTTP status along with the JSON payload."""

    def assertJsonError(self, response, status, error=None):
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertFalse(body['success'])
        if error is not None:
            self.assertEqual(body['error'], error)

    def test_create_listing_by_musician_is_403(self):
        self.client.login(username="musicianuser", password="pass123")
        response = self.client.post(reverse('gigs:create_gig_listing'), data='{}', content_type="application/json")
        self.assertJsonError(response, 403, 'not_a_band')

    def test_create_listing_missing_fields_is_400(self):
        self.client.login(username="banduser", password="pass123")
        response = self.client.post(reverse('gigs:create_gig_listing'), data='{"title": "x"}',
                                    content_type="application/json")
        self.assertJsonError(response, 400, 'missing_fields')

    def test_create_listing_get_is_405(self):
        self.client.login(username="banduser", password="pass123")
        self.assertJsonError(self.client.get(reverse('gigs:create_gig_listing')), 405)

    def test_delete_missing_listing_is_404(self):
        self.client.login(username="banduser", password="pass123")
        self.assertJsonError(self.client.post(reverse('gigs:delete_listing', args=[999999])), 404, 'not_found')

    def test_delete_listing_get_is_405(self):
        self.client.login(username="banduser", password="pass123")
        self.assertJsonError(self.client.get(reverse('gigs:delete_listing', args=[self.listing.id])), 405)

    def test_gig_actions_on_missing_gig_are_404(self):
        self.client.login(username="musicianuser", password="pass123")
        for name in ('apply_gig', 'withdraw_gig', 'save_gig', 'unsave_gig'):
            response = self.client.post(reverse(f'gigs:{name}', args=[999999]))
            self.assertJsonError(response, 404, 'not_found')

    def test_send_interest_errors(self):
        url = reverse('gigs:send_interest', args=[self.musician.id])
        self.client.login(username="musicianuser", password="pass123")
        self.assertJsonError(self.client.post(url, data='{"message": "hi"}', content_type="application/json"), 403)
        self.client.login(username="banduser", password="pass123")
        self.assertJsonError(self.client.post(url, data='{"message": " "}', content_type="application/json"), 400)
        self.assertJsonError(self.client.get(url), 405)
        self.client.post(url, data='{"message": "hi"}', content_type="application/json")
        self.assertJsonError(self.client.post(url, data='{"message": "again"}', content_type="application/json"), 400)

    def test_send_interest_missing_musician_is_json_404(self):
        self.client.login(username="banduser", password="pass123")
        response = self.client.post(reverse('gigs:send_interest', args=[999999]),
                                    data='{"message": "hi"}', content_type="application/json")
        self.assertJsonError(response, 404, 'not_found')

    def test_delete_interest_errors(self):
        self.client.login(username="musicianuser", password="pass123")
        self.assertJsonError(self.client.post(reverse('gigs:delete_interest', args=[999999])), 404, 'not_found')
        self.assertJsonError(self.client.get(reverse('gigs:delete_interest', args=[999999])), 405)
        self.client.login(username="banduser", password="pass123")
        self.assertJsonError(self.client.post(reverse('gigs:delete_interest', args=[999999])), 404, 'not_found')

    def test_delete_account_get_is_405(self):
        self.client.login(username="musicianuser", password="pass123")
        self.assertJsonError(self.client.get(reverse('gigs:delete_account')), 405)
