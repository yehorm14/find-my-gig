from datetime import date
import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from gigs.models import Application, Band, Listing, Musician, Review


class DemoBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.band_user = User.objects.create_user('band_user_1', password='Password123!')
        cls.musician_user = User.objects.create_user('musician_1', password='Password123!')
        cls.band = Band.objects.create(user=cls.band_user, name='Demo Band', location='Glasgow', bio='b')
        cls.musician = Musician.objects.create(
            user=cls.musician_user, bio='m', age=25, instruments='Guitar', location='Glasgow')
        cls.listing = Listing.objects.create(
            band=cls.band, title='Guitarist', deadline=date(2030, 1, 1), is_urgent=False,
            description='d', location='Glasgow', req_instruments='Guitar')


class DemoOffByDefaultTests(DemoBase):
    def test_default_is_off(self):
        from django.conf import settings
        self.assertFalse(settings.DEMO_MODE)

    def test_demo_start_404_when_off(self):
        r = self.client.post(reverse('gigs:demo_start', args=['musician']))
        self.assertEqual(r.status_code, 404)

    def test_normal_writes_still_work_when_off(self):
        self.client.force_login(self.musician_user)
        r = self.client.post(reverse('gigs:apply_gig', args=[self.listing.id]),
                             content_type='application/json', data='{}')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Application.objects.filter(listing=self.listing).exists())

    def test_no_banner_when_off(self):
        self.assertNotContains(self.client.get(reverse('gigs:home')), 'Portfolio demo')


@override_settings(DEMO_MODE=True)
class DemoModeTests(DemoBase):
    def test_anonymous_can_browse_both_roles(self):
        for name, args in [('home', []), ('gig_listings', []), ('gig_detail', [self.listing.id]),
                           ('musicians_list', []), ('bands_list', []),
                           ('musician_detail', [self.musician.id]), ('band_detail', [self.band.id])]:
            r = self.client.get(reverse(f'gigs:{name}', args=args))
            self.assertEqual(r.status_code, 200, name)
        self.assertContains(self.client.get(reverse('gigs:home')), 'sample data')

    def test_no_maps_key_path(self):
        with self.settings(GOOGLE_MAPS_FRONTEND_KEY=None):
            r = self.client.get(reverse('gigs:gig_detail', args=[self.listing.id]))
        self.assertContains(r, 'Map not configured')
        self.assertNotContains(r, 'maps.googleapis.com')

    def test_demo_start_requires_post(self):
        self.assertEqual(self.client.get(reverse('gigs:demo_start', args=['band'])).status_code, 405)

    def test_demo_start_unknown_role_404(self):
        self.assertEqual(self.client.post('/demo/start/admin/').status_code, 404)  # not a role

    def test_demo_start_unseeded_404(self):
        User.objects.filter(username='band_user_1').delete()
        self.assertEqual(self.client.post(reverse('gigs:demo_start', args=['band'])).status_code, 404)

    def test_musician_demo_sees_dashboard(self):
        r = self.client.post(reverse('gigs:demo_start', args=['musician']))
        self.assertRedirects(r, reverse('gigs:dashboard'))
        for name in ['dashboard', 'my_applications', 'my_bookmarks', 'my_reviews', 'my_inbox', 'my_profile']:
            self.assertEqual(self.client.get(reverse(f'gigs:{name}')).status_code, 200, name)

    def test_band_demo_sees_dashboard(self):
        self.client.post(reverse('gigs:demo_start', args=['band']))
        for name in ['dashboard', 'my_listings', 'my_reach_outs', 'my_profile']:
            self.assertEqual(self.client.get(reverse(f'gigs:{name}')).status_code, 200, name)

    def test_demo_user_cannot_write(self):
        self.client.post(reverse('gigs:demo_start', args=['musician']))
        before = (Application.objects.count(), Listing.objects.count(), Review.objects.count())
        bio = Musician.objects.get(pk=self.musician.pk).bio
        attempts = [
            reverse('gigs:apply_gig', args=[self.listing.id]),
            reverse('gigs:save_gig', args=[self.listing.id]),
            reverse('gigs:submit_review', args=[self.listing.id]),
            reverse('gigs:update_profile'),
            reverse('gigs:delete_account'),
            reverse('gigs:create_gig_listing'),
            reverse('gigs:delete_listing', args=[self.listing.id]),
            reverse('gigs:send_interest', args=[self.musician.id]),
        ]
        for url in attempts:
            r = self.client.post(url, data=json.dumps({'bio': 'hacked'}),
                                 content_type='application/json')
            self.assertEqual(r.status_code, 403, url)
            self.assertEqual(r.json()['error'], 'demo_read_only')
            self.assertEqual(self.client.put(url).status_code, 403)
            self.assertEqual(self.client.delete(url).status_code, 403)
        # Plain form post gets an HTML 403 page
        r = self.client.post(reverse('gigs:update_profile'), {'bio': 'x'})
        self.assertEqual(r.status_code, 403)
        self.assertContains(r, 'read-only', status_code=403)
        self.assertEqual(before, (Application.objects.count(), Listing.objects.count(), Review.objects.count()))
        self.assertEqual(Musician.objects.get(pk=self.musician.pk).bio, bio)
        self.assertTrue(User.objects.filter(pk=self.musician_user.pk).exists())

    def test_anonymous_and_real_logins_cannot_write(self):
        before = User.objects.count()
        self.assertEqual(self.client.post(reverse('gigs:signup'), {'username': 'new'}).status_code, 403)
        self.assertEqual(self.client.post(reverse('gigs:login'), {
            'username': 'musician_1', 'password': 'Password123!'}).status_code, 403)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.post(reverse('gigs:password_reset'), {'email': 'a@b.c'}).status_code, 403)
        self.assertEqual(self.client.post('/admin/login/', {'username': 'x', 'password': 'y'}).status_code, 403)
        self.assertEqual(User.objects.count(), before)

    def test_real_account_session_cannot_write_either(self):
        self.client.force_login(self.musician_user)
        r = self.client.post(reverse('gigs:apply_gig', args=[self.listing.id]),
                             content_type='application/json', data='{}')
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Application.objects.exists())

    def test_logout_allowed_and_visitors_isolated(self):
        other = type(self.client)()
        self.client.post(reverse('gigs:demo_start', args=['musician']))
        other.post(reverse('gigs:demo_start', args=['band']))
        self.assertEqual(self.client.session['_auth_user_id'], str(self.musician_user.pk))
        self.assertEqual(other.session['_auth_user_id'], str(self.band_user.pk))
        self.assertEqual(self.client.post(reverse('gigs:logout')).status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertIn('_auth_user_id', other.session)  # other visitor unaffected
