from datetime import date
import importlib

from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from gigs.models import Application, Band, Listing, Musician, Review
from gigs.tests.test_views import ViewBaseTestCase


class ReviewBase(ViewBaseTestCase):
    def setUp(self):
        # The band accepted the musician's application, so both flows are eligible by default.
        Application.objects.create(applicant=self.musician_user, listing=self.listing,
                                   status=Application.ACCEPTED)

    def gig_url(self):
        return reverse('gigs:submit_review', args=[self.listing.id])

    def musician_url(self):
        return reverse('gigs:submit_musician_review', args=[self.musician.id])


class GigReviewTests(ReviewBase):
    def login(self):
        self.client.login(username='musicianuser', password='pass123')

    def test_eligible_musician_can_review_and_review_counts(self):
        self.login()
        response = self.client.post(self.gig_url(), {'rating': '4', 'comment': 'Solid gig'})
        self.assertRedirects(response, reverse('gigs:gig_detail', args=[self.listing.id]))
        review = Review.objects.get()
        self.assertEqual((review.reviewer, review.reviewee, review.listing, review.rating),
                         (self.musician_user, self.band_user, self.listing, 4))

    def test_success_message_is_shown_on_gig_page(self):
        self.login()
        response = self.client.post(self.gig_url(), {'rating': '4', 'comment': 'Solid gig'}, follow=True)
        self.assertContains(response, 'successfully published')

    def test_form_page_loads_for_eligible_user(self):
        self.login()
        self.assertEqual(self.client.get(self.gig_url()).status_code, 200)

    def test_invalid_ratings_rejected_with_readable_error(self):
        self.login()
        for bad in ['', '0', '6', '-1', 'abc', '3.5']:
            with self.subTest(rating=bad):
                response = self.client.post(self.gig_url(), {'rating': bad, 'comment': 'ok'})
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, 'rating', status_code=400)
                self.assertFalse(Review.objects.exists())

    def test_missing_comment_rejected_and_input_kept(self):
        self.login()
        for comment in ['', '   ']:
            with self.subTest(comment=comment):
                response = self.client.post(self.gig_url(), {'rating': '3', 'comment': comment})
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, 'Please write a comment.', status_code=400)
                self.assertFalse(Review.objects.exists())
        response = self.client.post(self.gig_url(), {'rating': '3', 'comment': ''})
        self.assertContains(response, '<option value="3" selected>', status_code=400, html=False)

    def test_band_cannot_review_its_own_gig(self):
        self.client.login(username='banduser', password='pass123')
        response = self.client.post(self.gig_url(), {'rating': '5', 'comment': 'Me'}, follow=True)
        self.assertContains(response, 'cannot review your own gig')
        self.assertFalse(Review.objects.exists())

    def test_other_band_cannot_review_gig(self):
        other = User.objects.create_user(username='otherband', password='pass123')
        Band.objects.create(user=other, name='Other', location='X', bio='b')
        self.client.login(username='otherband', password='pass123')
        response = self.client.post(self.gig_url(), {'rating': '5', 'comment': 'x'}, follow=True)
        self.assertContains(response, 'Only musicians can review a gig')
        self.assertFalse(Review.objects.exists())

    def test_musician_without_application_cannot_review(self):
        Application.objects.all().delete()
        self.login()
        response = self.client.post(self.gig_url(), {'rating': '5', 'comment': 'x'}, follow=True)
        self.assertContains(response, 'only review gigs where your application was accepted')
        self.assertFalse(Review.objects.exists())

    def test_pending_or_declined_application_cannot_review_gig(self):
        self.login()
        for status in (Application.PENDING, Application.DECLINED):
            with self.subTest(status=status):
                Application.objects.update(status=status)
                response = self.client.post(self.gig_url(), {'rating': '5', 'comment': 'x'}, follow=True)
                self.assertContains(response, 'application was accepted')
                self.assertFalse(Review.objects.exists())

    def test_duplicate_blocked_with_message(self):
        self.login()
        self.client.post(self.gig_url(), {'rating': '5', 'comment': 'first'})
        response = self.client.post(self.gig_url(), {'rating': '1', 'comment': 'second'}, follow=True)
        self.assertContains(response, 'already left a review')
        self.assertEqual(Review.objects.count(), 1)
        self.assertEqual(Review.objects.get().comment, 'first')

    def test_requires_login(self):
        self.assertEqual(self.client.post(self.gig_url(), {'rating': '5', 'comment': 'x'}).status_code, 302)
        self.assertFalse(Review.objects.exists())


class MusicianReviewTests(ReviewBase):
    def login(self):
        self.client.login(username='banduser', password='pass123')

    def test_eligible_band_can_review(self):
        self.login()
        response = self.client.post(self.musician_url(), {'rating': '5', 'feedback': 'Great player'})
        self.assertRedirects(response, reverse('gigs:musician_detail', args=[self.musician.id]))
        review = Review.objects.get()
        self.assertEqual((review.reviewer, review.reviewee, review.listing, review.rating, review.comment),
                         (self.band_user, self.musician_user, None, 5, 'Great player'))

    def test_review_shows_on_musician_profile(self):
        self.login()
        self.client.post(self.musician_url(), {'rating': '5', 'feedback': 'Great player'})
        response = self.client.get(reverse('gigs:musician_detail', args=[self.musician.id]))
        self.assertContains(response, 'Great player')

    def test_invalid_ratings_rejected(self):
        self.login()
        for bad in ['', '0', '6', 'x']:
            with self.subTest(rating=bad):
                response = self.client.post(self.musician_url(), {'rating': bad, 'feedback': 'ok'})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(Review.objects.exists())

    def test_missing_comment_rejected(self):
        self.login()
        response = self.client.post(self.musician_url(), {'rating': '4', 'feedback': ' '})
        self.assertContains(response, 'Please write a comment.', status_code=400)
        self.assertFalse(Review.objects.exists())

    def test_musician_cannot_review_a_musician(self):
        other_user = User.objects.create_user(username='m2', password='pass123')
        Musician.objects.create(user=other_user, bio='b', instruments='Bass', location='X')
        self.client.login(username='m2', password='pass123')
        response = self.client.post(self.musician_url(), {'rating': '4', 'feedback': 'x'}, follow=True)
        self.assertContains(response, 'Only bands can review musicians')
        self.assertFalse(Review.objects.exists())

    def test_musician_cannot_review_self(self):
        self.client.login(username='musicianuser', password='pass123')
        response = self.client.post(self.musician_url(), {'rating': '5', 'feedback': 'me'}, follow=True)
        self.assertContains(response, 'cannot review yourself')
        self.assertFalse(Review.objects.exists())

    def test_band_cannot_review_musician_who_never_applied(self):
        Application.objects.all().delete()
        self.login()
        response = self.client.post(self.musician_url(), {'rating': '5', 'feedback': 'x'}, follow=True)
        self.assertContains(response, 'accepted for one of your gigs')
        self.assertFalse(Review.objects.exists())

    def test_application_to_a_different_band_does_not_count(self):
        Application.objects.all().delete()
        other = User.objects.create_user(username='otherband', password='pass123')
        other_band = Band.objects.create(user=other, name='Other', location='X', bio='b')
        listing = Listing.objects.create(band=other_band, title='t', deadline=date(2026, 5, 1), is_urgent=False,
                                         description='d', location='X', req_instruments='Guitar')
        Application.objects.create(applicant=self.musician_user, listing=listing,
                                   status=Application.ACCEPTED)
        self.login()
        self.client.post(self.musician_url(), {'rating': '5', 'feedback': 'x'})
        self.assertFalse(Review.objects.exists())

    def test_pending_or_declined_application_cannot_be_reviewed_by_band(self):
        self.login()
        for status in (Application.PENDING, Application.DECLINED):
            with self.subTest(status=status):
                Application.objects.update(status=status)
                response = self.client.post(self.musician_url(), {'rating': '5', 'feedback': 'x'}, follow=True)
                self.assertContains(response, 'accepted for one of your gigs')
                self.assertFalse(Review.objects.exists())

    def test_duplicate_blocked(self):
        self.login()
        self.client.post(self.musician_url(), {'rating': '5', 'feedback': 'first'})
        response = self.client.post(self.musician_url(), {'rating': '1', 'feedback': 'second'}, follow=True)
        self.assertContains(response, 'already reviewed this musician')
        self.assertEqual(Review.objects.count(), 1)

    def test_leave_review_button_only_when_eligible(self):
        detail = reverse('gigs:musician_detail', args=[self.musician.id])
        self.login()
        self.assertContains(self.client.get(detail), self.musician_url())
        Application.objects.all().delete()
        self.assertNotContains(self.client.get(detail), self.musician_url())


class ReviewConstraintTests(ViewBaseTestCase):
    """The database enforces the invariants that must hold under concurrent submissions."""

    def create(self, **kw):
        data = dict(reviewer=self.musician_user, reviewee=self.band_user, listing=self.listing,
                    rating=4, comment='ok')
        data.update(kw)
        with transaction.atomic():
            return Review.objects.create(**data)

    def test_rating_out_of_range_rejected(self):
        for bad in (0, 6):
            with self.assertRaises(IntegrityError):
                self.create(rating=bad)

    def test_self_review_rejected(self):
        with self.assertRaises(IntegrityError):
            self.create(reviewer=self.band_user, reviewee=self.band_user)

    def test_duplicate_gig_review_rejected(self):
        self.create()
        with self.assertRaises(IntegrityError):
            self.create(rating=1)

    def test_duplicate_direct_review_rejected(self):
        self.create(reviewer=self.band_user, reviewee=self.musician_user, listing=None)
        with self.assertRaises(IntegrityError):
            self.create(reviewer=self.band_user, reviewee=self.musician_user, listing=None)

    def test_gig_and_direct_review_by_same_pair_are_independent(self):
        self.create(reviewer=self.band_user, reviewee=self.musician_user, listing=self.listing)
        self.create(reviewer=self.band_user, reviewee=self.musician_user, listing=None)
        self.assertEqual(Review.objects.count(), 2)

    def test_legacy_blank_comment_still_stored_and_readable(self):
        review = self.create(comment='')
        self.assertEqual(Review.objects.get(pk=review.pk).comment, '')


class ReviewMigrationTests(TransactionTestCase):
    """Existing valid reviews survive the migration; bad data stops it with a clear error."""
    before = [('gigs', '0015_listing_geocoded_location_unique_application')]
    after = [('gigs', '0016_review_constraints')]

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def seed(self, apps, duplicate=False):
        U, Review_ = apps.get_model('auth', 'User'), apps.get_model('gigs', 'Review')
        a, b = U.objects.create(username='a'), U.objects.create(username='b')
        Review_.objects.create(reviewer=a, reviewee=b, rating=5, comment='fine')
        Review_.objects.create(reviewer=b, reviewee=a, rating=3, comment='')
        if duplicate:
            Review_.objects.create(reviewer=a, reviewee=b, rating=2, comment='again')

    def test_valid_reviews_survive(self):
        apps = self.migrate(self.before)
        self.seed(apps)
        self.migrate(self.after)
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(Review.objects.count(), 2)
        self.assertEqual(sorted(Review.objects.values_list('rating', flat=True)), [3, 5])

    def test_duplicates_stop_the_migration_without_deleting_anything(self):
        apps = self.migrate(self.before)
        self.seed(apps, duplicate=True)
        with self.assertRaisesMessage(RuntimeError, 'more than one direct review'):
            self.migrate(self.after)
        reviews = apps.get_model('gigs', 'Review').objects
        self.assertEqual(reviews.count(), 3)
        reviews.filter(rating=2).delete()  # let tearDown migrate forward
