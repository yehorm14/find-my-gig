import io
import json
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from gigs.models import Band, MediaLink, Musician
from gigs.tests.test_views import ViewBaseTestCase


def png_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (2, 2), 'red').save(buf, format='PNG')
    return buf.getvalue()


class ProfileUpdateTests(ViewBaseTestCase):
    def setUp(self):
        self.url = reverse('gigs:update_profile')
        self.other_user = User.objects.create_user(username="othermusician", password="pass123")
        self.other_musician = Musician.objects.create(
            user=self.other_user, bio="Other bio", age=30, instruments="Drums", location="Leeds")
        self.other_link = MediaLink.objects.create(musician=self.other_musician, url="https://example.com/other")
        self.own_link = MediaLink.objects.create(musician=self.musician, url="https://example.com/own")

    def post_json(self, payload):
        return self.client.post(self.url, data=json.dumps(payload), content_type="application/json")

    def musician_payload(self, **overrides):
        payload = {'username': 'musicianuser', 'firstname': 'Mu', 'surname': 'Sician', 'about': 'New bio',
                   'age': '25', 'instruments': 'Bass', 'media_links': [], 'delete_media': []}
        payload.update(overrides)
        return payload

    def band_payload(self, **overrides):
        payload = {'username': 'banduser', 'firstname': 'B', 'surname': 'And', 'band_name': 'Renamed Band',
                   'about': 'New band bio', 'age': '', 'instruments': '', 'media_links': [], 'delete_media': []}
        payload.update(overrides)
        return payload

    def snapshot(self):
        self.musician_user.refresh_from_db()
        self.musician.refresh_from_db()
        return (self.musician_user.username, self.musician_user.first_name, self.musician_user.last_name,
                self.musician.bio, self.musician.age, self.musician.instruments,
                sorted(MediaLink.objects.filter(musician=self.musician).values_list('url', flat=True)))

    # --- valid edits ---

    def test_valid_musician_edit_saves_everything_and_keeps_existing_links(self):
        self.client.login(username="musicianuser", password="pass123")
        response = self.post_json(self.musician_payload(media_links=['https://example.com/new']))
        self.assertEqual(response.json(), {'success': True, 'media_links': [{'id': MediaLink.objects.get(url='https://example.com/new').id, 'url': 'https://example.com/new'}]})
        self.musician_user.refresh_from_db()
        self.musician.refresh_from_db()
        self.assertEqual(self.musician_user.first_name, 'Mu')
        self.assertEqual(self.musician.bio, 'New bio')
        self.assertEqual(self.musician.age, 25)
        self.assertEqual(self.musician.instruments, 'Bass')
        urls = set(self.musician.media_links.values_list('url', flat=True))
        self.assertEqual(urls, {'https://example.com/own', 'https://example.com/new'})

    def test_musician_edit_without_links_or_age_leaves_them_unchanged(self):
        self.client.login(username="musicianuser", password="pass123")
        response = self.post_json(self.musician_payload(age='', media_links=[]))
        self.assertTrue(response.json()['success'])
        self.musician.refresh_from_db()
        self.assertEqual(self.musician.age, 21)
        self.assertTrue(MediaLink.objects.filter(pk=self.own_link.pk).exists())

    def test_valid_band_edit(self):
        self.client.login(username="banduser", password="pass123")
        self.assertTrue(self.post_json(self.band_payload()).json()['success'])
        self.band.refresh_from_db()
        self.assertEqual(self.band.name, 'Renamed Band')
        self.assertEqual(self.band.bio, 'New band bio')

    def test_band_blank_name_keeps_existing_name(self):
        self.client.login(username="banduser", password="pass123")
        self.assertTrue(self.post_json(self.band_payload(band_name='')).json()['success'])
        self.band.refresh_from_db()
        self.assertEqual(self.band.name, 'Test Band')

    def test_keeping_own_username_is_not_a_conflict(self):
        self.client.login(username="musicianuser", password="pass123")
        self.assertTrue(self.post_json(self.musician_payload()).json()['success'])

    # --- pictures (multipart) ---

    def test_multipart_picture_upload_and_unchanged_picture(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        with override_settings(MEDIA_ROOT=media):
            self.client.login(username="musicianuser", password="pass123")
            data = {k: v for k, v in self.musician_payload().items() if k not in ('media_links', 'delete_media')}
            data['media_links'] = json.dumps(['https://example.com/pic'])
            data['delete_media'] = json.dumps([])
            data['profile_picture'] = SimpleUploadedFile('p.png', png_bytes(), content_type='image/png')
            self.assertTrue(self.client.post(self.url, data).json()['success'])
            self.musician.refresh_from_db()
            picture = self.musician.profile_picture.name
            self.assertTrue(picture)

            # A later edit without a picture keeps the stored one.
            data.pop('profile_picture')
            self.assertTrue(self.client.post(self.url, data).json()['success'])
            self.musician.refresh_from_db()
            self.assertEqual(self.musician.profile_picture.name, picture)

    def test_invalid_picture_changes_nothing(self):
        self.client.login(username="musicianuser", password="pass123")
        before = self.snapshot()
        data = {k: v for k, v in self.musician_payload(about='Changed').items() if k not in ('media_links', 'delete_media')}
        data['profile_picture'] = SimpleUploadedFile('p.png', b'not an image', content_type='image/png')
        body = self.client.post(self.url, data).json()
        self.assertFalse(body['success'])
        self.assertIn('profile_picture', body['errors'])
        self.assertEqual(self.snapshot(), before)

    # --- invalid edits change nothing ---

    def test_duplicate_username_returns_field_error_and_changes_nothing(self):
        self.client.login(username="musicianuser", password="pass123")
        before = self.snapshot()
        body = self.post_json(self.musician_payload(username='banduser', about='Changed',
                                                    media_links=['https://example.com/new'])).json()
        self.assertEqual(body['success'], False)
        self.assertEqual(body['error'], 'username_taken')
        self.assertIn('username', body['errors'])
        self.assertEqual(self.snapshot(), before)

    def test_invalid_profile_field_does_not_save_account_fields(self):
        self.client.login(username="musicianuser", password="pass123")
        before = self.snapshot()
        body = self.post_json(self.musician_payload(username='renamed', firstname='Changed', age='abc',
                                                    media_links=['https://example.com/new'])).json()
        self.assertEqual(body['error'], 'invalid')
        self.assertIn('age', body['errors'])
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(User.objects.filter(username='renamed').exists())

    def test_invalid_link_changes_nothing(self):
        self.client.login(username="musicianuser", password="pass123")
        before = self.snapshot()
        body = self.post_json(self.musician_payload(about='Changed', media_links=['not a url'],
                                                    delete_media=[self.own_link.pk])).json()
        self.assertFalse(body['success'])
        self.assertIn('media_links', body['errors'])
        self.assertEqual(self.snapshot(), before)

    def test_missing_required_fields_report_each_field(self):
        self.client.login(username="musicianuser", password="pass123")
        body = self.post_json({'username': '', 'about': '', 'instruments': ''}).json()
        self.assertFalse(body['success'])
        self.assertTrue({'username', 'about', 'instruments'} <= set(body['errors']))

    def test_invalid_band_edit_changes_nothing(self):
        self.client.login(username="banduser", password="pass123")
        body = self.post_json(self.band_payload(username='newname', band_name='x' * 51)).json()
        self.assertFalse(body['success'])
        self.assertIn('band_name', body['errors'])
        self.band.refresh_from_db()
        self.band_user.refresh_from_db()
        self.assertEqual(self.band.name, 'Test Band')
        self.assertEqual(self.band_user.username, 'banduser')

    def test_malformed_json_body(self):
        self.client.login(username="musicianuser", password="pass123")
        response = self.client.post(self.url, data="{nope", content_type="application/json")
        self.assertEqual(response.json(), {'success': False, 'error': 'invalid_json'})

    def test_user_without_profile_is_rejected_without_changes(self):
        plain = User.objects.create_user(username="plain", password="pass123")
        self.client.login(username="plain", password="pass123")
        body = self.post_json(self.musician_payload(username='plain2')).json()
        self.assertEqual(body['error'], 'no_profile')
        plain.refresh_from_db()
        self.assertEqual(plain.username, 'plain')

    # --- scoping and atomicity ---

    def test_delete_media_only_affects_own_links(self):
        self.client.login(username="musicianuser", password="pass123")
        self.assertTrue(self.post_json(self.musician_payload(
            delete_media=[self.own_link.pk, self.other_link.pk, 'pending-1'])).json()['success'])
        self.assertFalse(MediaLink.objects.filter(pk=self.own_link.pk).exists())
        self.assertTrue(MediaLink.objects.filter(pk=self.other_link.pk).exists())

    def test_edit_does_not_touch_other_profiles(self):
        self.client.login(username="musicianuser", password="pass123")
        self.post_json(self.musician_payload(media_links=['https://example.com/new']))
        self.other_user.refresh_from_db()
        self.other_musician.refresh_from_db()
        self.assertEqual((self.other_user.username, self.other_musician.bio, self.other_musician.instruments),
                         ('othermusician', 'Other bio', 'Drums'))
        self.assertEqual(list(self.other_musician.media_links.values_list('url', flat=True)),
                         ['https://example.com/other'])

    def test_band_edit_does_not_touch_other_bands_or_musicians(self):
        self.client.login(username="banduser", password="pass123")
        self.post_json(self.band_payload())
        self.musician.refresh_from_db()
        self.assertEqual(self.musician.bio, 'Musician bio')

    def test_failure_while_saving_rolls_back_every_write(self):
        from unittest import mock
        self.client.login(username="musicianuser", password="pass123")
        before = self.snapshot()
        with mock.patch('gigs.views.MediaLink.objects.create', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                self.post_json(self.musician_payload(username='renamed', about='Changed',
                                                     media_links=['https://example.com/new'],
                                                     delete_media=[self.own_link.pk]))
        self.assertEqual(self.snapshot(), before)

    def test_requires_login(self):
        response = self.post_json(self.musician_payload())
        self.assertEqual(response.status_code, 302)
