from django.test import TestCase
from django.test.utils import override_settings

import mock
from django.urls import reverse
from rest_framework.reverse import reverse as drf_reverse

from .auth.backends import CombinedAuthBackend
from .models import User


def mock_requests_get(url, headers=None):
    response = mock.Mock(content=open('docs/src/imgs/logo-dark.png', 'rb').read())
    return response


class CombinedAuthBackendTest(TestCase):
    def setUp(self):
        self.backend = CombinedAuthBackend()
        self.username = 'jdoe'
        self.email = 'jdoe@example.com'
        self.password = 'password'
        User.objects.create_user(username=self.username, email=self.email, password=self.password)

    def test_authenticate_username(self):
        self.assertTrue(self.backend.authenticate(username=self.username, password=self.password))

    def test_authenticate_email(self):
        self.assertTrue(self.backend.authenticate(username=self.email, password=self.password))

    def test_authenticate_wrong_password(self):
        self.assertIsNone(self.backend.authenticate(username=self.username, password='wrong-password'))

    def test_authenticate_unknown_user(self):
        self.assertIsNone(self.backend.authenticate(username='wrong-username', password='wrong-password'))


class CreateUserTest(TestCase):
    def test_create_post(self):
        data = {
            'username': 'jdoe',
            'email': 'jdoe@example.com',
            'password': 'password',
            'password_repeat': 'password',
        }
        response = self.client.post(
            reverse('users:user-list'),
            data=data,
        )
        self.assertEqual(response.status_code, 201)

    @override_settings(ALLOW_NEW_REGISTRATIONS=False)
    def test_create_post_not_allowed(self):
        data = {
            'username': 'jdoe',
            'email': 'jdoe@example.com',
            'password': 'password',
            'password_repeat': 'password',

        }
        response = self.client.post(
            reverse('users:user-list'),
            data=data,
        )
        self.assertEqual(response.status_code, 401)


class LogoutViewTest(TestCase):
    def setUp(self):
        User.objects.create_user(username='jdoe', email='jdoe@example.com', password='password')
        self.client.login(username='jdoe', email='jdoe@example.com', password='password')

    def test_logout_view(self):
        response = self.client.get(reverse('users:logout'))
        self.assertEqual(response.status_code, 302)


class ProfileViewTest(TestCase):
    def setUp(self):
        self.first_user = User.objects.create_user(username='jdoe', email='jdoe@example.com', password='password')
        self.second_user = User.objects.create_user(username='judy', email='judy@example.com', password='password')
        self.client.login(username='jdoe', email='jdoe@example.com', password='password')

    def test_should_have_access_to_token(self):
        from rest_framework.authtoken.models import Token
        url = drf_reverse('users:user-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['token'], Token.objects.get(user=self.first_user).key)
        self.assertEqual(response.data[0]['email'], self.first_user.email)

    def test_public_profile_should_not_expose_token_or_email(self):
        url = drf_reverse('users:public-user-list')
        for user in (self.first_user, self.second_user):
            response = self.client.get(f"{url}?username={user.username}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data[0]['username'], user.username)
            self.assertNotIn('token', response.data[0])
            self.assertNotIn('email', response.data[0])

    def test_public_profile_should_not_expose_email_to_anonymous(self):
        self.client.logout()
        url = drf_reverse('users:public-user-list')
        response = self.client.get(f"{url}?username={self.second_user.username}")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('email', response.data[0])
