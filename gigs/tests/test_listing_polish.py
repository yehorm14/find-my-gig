from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from gigs.models import Band, Listing
import population_script


class SeedCoherenceTests(SimpleTestCase):
    KEYWORDS = {
        'Guitar': ('guitar',),
        'Bass': ('bass',),
        'Drums': ('drum',),
        'Vocals': ('vocal', 'singer'),
        'Keys/Synth': ('keys', 'synth'),
    }

    def test_each_seed_post_title_matches_its_instrument(self):
        for post in population_script.GIG_POSTS:
            self.assertIn(post['instrument'], population_script.INSTRUMENTS)
            words = self.KEYWORDS[post['instrument']]
            self.assertTrue(any(w in post['title'].lower() for w in words), post['title'])


class DeadlineLabelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = User.objects.create_user(username='b', password='x')
        band = Band.objects.create(user=user, name='B', location='Glasgow', bio='b')
        cls.listing = Listing.objects.create(
            band=band, title='Guitarist', deadline=date.today() + timedelta(days=10),
            is_urgent=False, description='d', location='Glasgow', req_instruments='Guitar')

    def test_listing_card_labels_deadline_as_apply_by(self):
        response = self.client.get(reverse('gigs:gig_listings'))
        self.assertContains(response, 'Apply by')
        self.assertNotContains(response, 'Deadline:')

    def test_detail_labels_deadline_as_apply_by(self):
        response = self.client.get(reverse('gigs:gig_detail', args=[self.listing.id]))
        self.assertContains(response, 'Apply By')

    def test_filter_offers_keys_synth(self):
        response = self.client.get(reverse('gigs:gig_listings'))
        self.assertContains(response, 'value="Keys/Synth"')
