import re

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse


class AuthFlowTests(TestCase):
    """Login, logout and password reset: framework behaviour that changes between Django releases."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="flowuser", email="flow@example.com", password="old-pass-123")

    def test_login_and_logout(self):
        response = self.client.post(reverse('gigs:login'), {'username': 'flowuser', 'password': 'old-pass-123'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)

        # Django 5 removed GET logout; the navbar posts a form.
        self.assertEqual(self.client.get(reverse('gigs:logout')).status_code, 405)
        self.client.post(reverse('gigs:logout'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_password_reset_end_to_end(self):
        response = self.client.post(reverse('gigs:password_reset'), {'email': 'flow@example.com'})
        self.assertRedirects(response, reverse('gigs:password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)

        link = re.search(r'https?://[^/\s]+(/[^\s]*reset/[^\s]+)', mail.outbox[0].body).group(1)
        response = self.client.get(link, follow=True)
        self.assertEqual(response.status_code, 200)
        confirm_url = response.redirect_chain[-1][0] if response.redirect_chain else link

        response = self.client.post(confirm_url, {'new_password1': 'brand-new-pass-456',
                                                  'new_password2': 'brand-new-pass-456'})
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('brand-new-pass-456'))
