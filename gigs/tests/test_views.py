from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from datetime import date, timedelta
from django.utils import timezone
import json

from gigs.models import Musician, Band, Listing, Application, Review

class ViewBaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.band_user = User.objects.create_user(username="banduser", email="band@test.com", password="pass123")
        cls.musician_user = User.objects.create_user(username="musicianuser", email="musician@test.com", password="pass123")

        cls.band = Band.objects.create(user=cls.band_user, name="Test Band", location="Glasgow", bio="Band bio")
        cls.musician = Musician.objects.create(user=cls.musician_user, bio="Musician bio", age=21, instruments="Guitar", location="Glasgow")

        cls.listing = Listing.objects.create(
            band=cls.band, title="Guitarist needed", deadline=timezone.localdate() + timedelta(days=30),
            is_urgent=False, description="Need a guitarist", location="Glasgow", req_instruments="Guitar"
        )

class PublicViewTests(ViewBaseTestCase):
    def test_home_page_loads_for_anonymous_user(self):
        response = self.client.get(reverse('gigs:home'))
        self.assertEqual(response.status_code, 200)

    def test_gig_detail_invalid_id_returns_404(self):
        """EDGE CASE: Looking up a gig that does not exist"""
        response = self.client.get(reverse('gigs:gig_detail', args=[999999]))
        self.assertEqual(response.status_code, 404)

class FilterTests(ViewBaseTestCase):
    def test_filter_gigs_by_instrument_match(self):
        """EDGE CASE: Using the search filter should return matching gigs"""
        response = self.client.get(reverse('gigs:gig_listings'), {'instrument': 'Guitar'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.listing, response.context['gigs'])

    def test_filter_gigs_by_instrument_no_match(self):
        """EDGE CASE: Using the search filter should exclude non-matching gigs"""
        response = self.client.get(reverse('gigs:gig_listings'), {'instrument': 'Drums'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.listing, response.context['gigs'])

class AjaxActionTests(ViewBaseTestCase):
    def setUp(self):
        self.client.login(username='musicianuser', password='pass123')

    def test_apply_for_gig_success(self):
        response = self.client.post(reverse('gigs:apply_gig', args=[self.listing.id]))
        self.assertEqual(response.json()['success'], True)
        self.assertTrue(Application.objects.filter(applicant=self.musician_user, listing=self.listing).exists())

    def test_duplicate_application_blocked(self):
        """EDGE CASE: Spamming the apply button should return an error"""
        Application.objects.create(applicant=self.musician_user, listing=self.listing)
        response = self.client.post(reverse('gigs:apply_gig', args=[self.listing.id]))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['success'], False)
        self.assertEqual(response.json()['error'], 'already_applied')

    def test_invalid_http_method_blocked(self):
        """EDGE CASE: Sending a GET request to an AJAX POST endpoint"""
        response = self.client.get(reverse('gigs:apply_gig', args=[self.listing.id]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()['success'], False)
        self.assertEqual(response.json()['error'], 'Invalid request')

    def test_save_gig_bookmark(self):
        response = self.client.post(reverse('gigs:save_gig', args=[self.listing.id]))
        self.assertEqual(response.json()['success'], True)
        self.assertTrue(self.listing.bookmarks.filter(id=self.musician_user.id).exists())

class ReviewViewTests(ViewBaseTestCase):
    def setUp(self):
        self.client.login(username='musicianuser', password='pass123')

    def test_submit_valid_review(self):
        Application.objects.create(applicant=self.musician_user, listing=self.listing,
                                   status=Application.ACCEPTED)
        response = self.client.post(reverse('gigs:submit_review', args=[self.listing.id]), data={
            'rating': '5',
            'comment': 'Awesome band!'
        })
        self.assertEqual(response.status_code, 302) 
        self.assertTrue(Review.objects.filter(reviewer=self.musician_user, listing=self.listing).exists())

    def test_review_refused_until_application_accepted(self):
        Application.objects.create(applicant=self.musician_user, listing=self.listing)
        response = self.client.post(reverse('gigs:submit_review', args=[self.listing.id]), data={
            'rating': '5', 'comment': 'Awesome band!'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Review.objects.exists())

    def test_duplicate_review_blocked(self):
        """EDGE CASE: Submitting two reviews for the exact same gig is forbidden"""
        Review.objects.create(reviewer=self.musician_user, reviewee=self.band_user, listing=self.listing, rating=4, comment="Good")
        
        response = self.client.post(reverse('gigs:submit_review', args=[self.listing.id]), data={
            'rating': '5',
            'comment': 'I am trying to review them again!'
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Review.objects.filter(reviewer=self.musician_user, listing=self.listing).count(), 1)


class SecurityViewTests(TestCase):
    """EDGE CASE: Verifying that unauthenticated users are blocked from protected views."""
    
    @classmethod
    def setUpTestData(cls):
        cls.band_user = User.objects.create_user(username="secureband", email="band@test.com", password="pass")
        cls.band = Band.objects.create(user=cls.band_user, name="Secure Band", location="Glasgow")
        cls.listing = Listing.objects.create(
            band=cls.band, title="Gig", deadline=timezone.localdate() + timedelta(days=30),
            is_urgent=False,
            description="Desc", location="Glasgow", req_instruments="Guitar"
        )

    def test_dashboard_requires_login(self):
        """EDGE CASE: Anonymous user trying to access the dashboard"""
        response = self.client.get(reverse('gigs:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('gigs:login')))

    def test_create_gig_requires_login(self):
        """EDGE CASE: Anonymous user trying to load the create gig form"""
        response = self.client.get(reverse('gigs:create_gig'))
        self.assertEqual(response.status_code, 302)

    def test_submit_review_requires_login(self):
        """EDGE CASE: Anonymous user trying to submit a review directly via URL"""
        response = self.client.post(reverse('gigs:submit_review', args=[self.listing.id]), data={
            'rating': '5',
            'comment': 'Hacked review!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Review.objects.exists())

    def test_ajax_apply_requires_login(self):
        """EDGE CASE: Anonymous user trying to hit the apply endpoint"""
        response = self.client.post(reverse('gigs:apply_gig', args=[self.listing.id]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['success'], False)
        self.assertEqual(response.json()['error'], 'not_logged_in')

class AccountManagementTests(TestCase):
    """EDGE CASE: Verifying that users can successfully register and update their profiles."""
    
    def test_signup_creates_musician_profile(self):
        """EDGE CASE: Submitting the signup form as a 'musician' should create both a User and a Musician."""
        data = {
            'username': 'new_drummer',
            'first_name': 'Test',       
            'last_name': 'Musician',    
            'email': 'drummer@test.com',
            'password1': 'SecurePassword123!',  
            'password2': 'SecurePassword123!',  
            'location': 'Glasgow',             
            'user_type': 'musician'
        }
        response = self.client.post(reverse('gigs:signup'), data=data)
        

        self.assertEqual(response.status_code, 302) 
        self.assertTrue(User.objects.filter(username='new_drummer').exists())
        self.assertTrue(Musician.objects.filter(user__username='new_drummer').exists())

    def test_signup_creates_band_profile(self):
        """EDGE CASE: Submitting the signup form as a 'band' should create both a User and a Band."""
        data = {
            'username': 'new_manager',
            'first_name': 'Test',       
            'last_name': 'Manager',     
            'email': 'manager@test.com',
            'password1': 'SecurePassword123!',
            'password2': 'SecurePassword123!',
            'location': 'Glasgow',
            'user_type': 'band',
            'band_name': 'The Rockers'
        }
        response = self.client.post(reverse('gigs:signup'), data=data)


        self.assertEqual(response.status_code, 302)
        self.assertTrue(Band.objects.filter(name='The Rockers').exists())


class DataDeletionTests(ViewBaseTestCase):
    """EDGE CASE: Verifying that users can safely delete their data without server crashes."""
    
    def test_withdraw_application(self):
        """EDGE CASE: Withdrawing an application should remove the database record."""
        self.client.login(username='musicianuser', password='pass123')
        Application.objects.create(applicant=self.musician_user, listing=self.listing)
        
      
        response = self.client.post(reverse('gigs:withdraw_gig', args=[self.listing.id]))
        self.assertEqual(response.json()['success'], True)
        self.assertFalse(Application.objects.filter(applicant=self.musician_user, listing=self.listing).exists())

    def test_delete_listing(self):
        """EDGE CASE: A band deleting their own listing."""
        self.client.login(username='banduser', password='pass123')
        
        response = self.client.post(reverse('gigs:delete_listing', args=[self.listing.id]))
        self.assertEqual(response.json()['success'], True)
        self.assertFalse(Listing.objects.filter(id=self.listing.id).exists())

class ApplicationDecisionTests(ViewBaseTestCase):
    """Bands accept or decline applications to their own listings (issue #12)."""

    def setUp(self):
        self.application = Application.objects.create(applicant=self.musician_user, listing=self.listing)
        self.other_band_user = User.objects.create_user(username="otherband", password="pass123")
        Band.objects.create(user=self.other_band_user, name="Other Band")

    def url(self, action, pk=None):
        return reverse(f'gigs:{action}_application', args=[pk or self.application.id])

    def status(self):
        self.application.refresh_from_db()
        return self.application.status

    def test_default_status_is_pending(self):
        self.assertEqual(self.status(), 'Pending')

    def test_owner_can_accept_and_decline(self):
        self.client.login(username='banduser', password='pass123')
        response = self.client.post(self.url('accept'))
        self.assertEqual(response.json(), {'success': True, 'status': 'Accepted'})
        self.assertEqual(self.status(), 'Accepted')
        response = self.client.post(self.url('decline'))
        self.assertEqual(response.json(), {'success': True, 'status': 'Declined'})
        self.assertEqual(self.status(), 'Declined')

    def test_other_band_cannot_change_status(self):
        self.client.login(username='otherband', password='pass123')
        for action in ('accept', 'decline'):
            response = self.client.post(self.url(action))
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json(), {'success': False, 'error': 'not_found'})
            self.assertEqual(self.status(), 'Pending')

    def test_musician_cannot_change_status(self):
        self.client.login(username='musicianuser', password='pass123')
        for action in ('accept', 'decline'):
            response = self.client.post(self.url(action))
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json(), {'success': False, 'error': 'not_a_band'})
            self.assertEqual(self.status(), 'Pending')

    def test_anonymous_cannot_change_status(self):
        for action in ('accept', 'decline'):
            response = self.client.post(self.url(action))
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json(), {'success': False, 'error': 'not_logged_in'})
            self.assertEqual(self.status(), 'Pending')

    def test_get_is_rejected_and_changes_nothing(self):
        self.client.login(username='banduser', password='pass123')
        response = self.client.get(self.url('accept'))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()['error'], 'invalid_request')
        self.assertEqual(self.status(), 'Pending')

    def test_unknown_application_is_not_found(self):
        self.client.login(username='banduser', password='pass123')
        response = self.client.post(self.url('accept', 999999))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error'], 'not_found')

    def test_csrf_is_enforced(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.login(username='banduser', password='pass123')
        self.assertEqual(client.post(self.url('accept')).status_code, 403)
        self.assertEqual(self.status(), 'Pending')

    def test_band_listings_page_shows_applicants_and_buttons(self):
        self.client.login(username='banduser', password='pass123')
        response = self.client.get(reverse('gigs:my_listings'))
        self.assertContains(response, 'accept-application-btn')
        self.assertContains(response, 'decline-application-btn')
        self.assertContains(response, 'musicianuser')

    def test_musician_sees_status_on_my_applications(self):
        self.client.login(username='musicianuser', password='pass123')
        self.assertContains(self.client.get(reverse('gigs:my_applications')), 'Status: Pending')
        Application.objects.update(status=Application.ACCEPTED)
        self.assertContains(self.client.get(reverse('gigs:my_applications')), 'Status: Accepted')
        Application.objects.update(status=Application.DECLINED)
        self.assertContains(self.client.get(reverse('gigs:my_applications')), 'Status: Declined')


class DateFilterTests(ViewBaseTestCase):
    def test_invalid_date_is_ignored(self):
        for bad in ('abc', '2026-13-45', '2026-02-30'):
            response = self.client.get(reverse('gigs:gig_listings'), {'date': bad})
            self.assertEqual(response.status_code, 200, bad)
            self.assertIn(self.listing, response.context['gigs'])
            self.assertEqual(response.context['selected_date'], '')

    def test_invalid_date_keeps_other_filters(self):
        response = self.client.get(reverse('gigs:gig_listings'), {'date': 'abc', 'instrument': 'Drums'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.listing, response.context['gigs'])

    def test_valid_date_still_filters(self):
        day = self.listing.deadline
        match = self.client.get(reverse('gigs:gig_listings'), {'date': day.isoformat()})
        self.assertIn(self.listing, match.context['gigs'])
        self.assertEqual(match.context['selected_date'], day.isoformat())
        miss = self.client.get(reverse('gigs:gig_listings'), {'date': (day + timedelta(days=1)).isoformat()})
        self.assertNotIn(self.listing, miss.context['gigs'])


class BandApplyRestrictionTests(ViewBaseTestCase):
    """Band accounts must not be able to apply to gigs (issue #10)."""

    def setUp(self):
        self.other_band_user = User.objects.create_user(username="otherband", password="pass123")
        Band.objects.create(user=self.other_band_user, name="Other Band")

    def test_band_cannot_apply_to_other_bands_gig(self):
        self.client.login(username='otherband', password='pass123')
        response = self.client.post(reverse('gigs:apply_gig', args=[self.listing.id]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {'success': False, 'error': 'not_a_musician'})
        self.assertFalse(Application.objects.filter(listing=self.listing).exists())

    def test_band_cannot_apply_to_own_gig(self):
        self.client.login(username='banduser', password='pass123')
        response = self.client.post(reverse('gigs:apply_gig', args=[self.listing.id]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {'success': False, 'error': 'not_a_musician'})
        self.assertFalse(Application.objects.filter(listing=self.listing).exists())

    def test_musician_apply_and_withdraw_still_work(self):
        self.client.login(username='musicianuser', password='pass123')
        self.assertTrue(self.client.post(reverse('gigs:apply_gig', args=[self.listing.id])).json()['success'])
        self.assertTrue(Application.objects.filter(applicant=self.musician_user, listing=self.listing).exists())
        self.assertTrue(self.client.post(reverse('gigs:withdraw_gig', args=[self.listing.id])).json()['success'])
        self.assertFalse(Application.objects.filter(applicant=self.musician_user, listing=self.listing).exists())

    def test_apply_button_not_rendered_for_band(self):
        self.client.login(username='banduser', password='pass123')
        detail = self.client.get(reverse('gigs:gig_detail', args=[self.listing.id]))
        self.assertNotContains(detail, 'gig-detail-apply-btn')
        listings = self.client.get(reverse('gigs:gig_listings'))
        self.assertNotContains(listings, 'data-gig-id')

    def test_apply_button_rendered_for_musician(self):
        self.client.login(username='musicianuser', password='pass123')
        detail = self.client.get(reverse('gigs:gig_detail', args=[self.listing.id]))
        self.assertContains(detail, 'gig-detail-apply-btn')

    def test_account_owning_the_band_cannot_apply_even_with_musician_profile(self):
        Musician.objects.create(user=self.band_user)
        self.client.login(username='banduser', password='pass123')
        response = self.client.post(reverse('gigs:apply_gig', args=[self.listing.id]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {'success': False, 'error': 'own_gig'})
        self.assertFalse(Application.objects.filter(listing=self.listing).exists())



class PastGigTests(ViewBaseTestCase):
    """Past gigs are hidden by default, cannot be posted and cannot be applied to (issue #16)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.past = Listing.objects.create(
            band=cls.band, title="Old gig", deadline=timezone.localdate() - timedelta(days=1),
            is_urgent=False, description="Gone", location="Glasgow", req_instruments="Guitar")
        cls.today = Listing.objects.create(
            band=cls.band, title="Today gig", deadline=timezone.localdate(),
            is_urgent=False, description="Now", location="Glasgow", req_instruments="Guitar")

    def test_past_gigs_hidden_by_default(self):
        gigs = self.client.get(reverse('gigs:gig_listings')).context['gigs']
        self.assertIn(self.listing, gigs)
        self.assertIn(self.today, gigs)
        self.assertNotIn(self.past, gigs)

    def test_past_gigs_shown_with_toggle(self):
        response = self.client.get(reverse('gigs:gig_listings'), {'show_past': '1'})
        self.assertIn(self.past, response.context['gigs'])
        self.assertTrue(response.context['show_past'])

    def test_posting_past_date_is_invalid_data(self):
        self.client.login(username='banduser', password='pass123')
        payload = {'title': 't', 'req_instruments': 'Guitar', 'description': 'd', 'location': 'Glasgow',
                   'date': str(timezone.localdate() - timedelta(days=1))}
        response = self.client.post(reverse('gigs:create_gig_listing'), data=json.dumps(payload),
                                    content_type='application/json')
        self.assertEqual(response.json(), {'success': False, 'error': 'invalid_data'})
        self.assertFalse(Listing.objects.filter(title='t').exists())

    def test_posting_today_is_allowed(self):
        self.client.login(username='banduser', password='pass123')
        payload = {'title': 't', 'req_instruments': 'Guitar', 'description': 'd', 'location': 'Glasgow',
                   'date': str(timezone.localdate())}
        response = self.client.post(reverse('gigs:create_gig_listing'), data=json.dumps(payload),
                                    content_type='application/json')
        self.assertTrue(response.json()['success'])

    def test_applying_to_past_gig_refused(self):
        self.client.login(username='musicianuser', password='pass123')
        response = self.client.post(reverse('gigs:apply_gig', args=[self.past.id]))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'success': False, 'error': 'deadline_passed'})
        self.assertFalse(Application.objects.filter(listing=self.past).exists())

    def test_applying_on_deadline_day_allowed(self):
        self.client.login(username='musicianuser', password='pass123')
        self.assertTrue(self.client.post(reverse('gigs:apply_gig', args=[self.today.id])).json()['success'])
