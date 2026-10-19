from rest_framework_simplejwt.tokens import AccessToken

from .base import PASSWORD, BaseAPITestCase


class AuthAPITests(BaseAPITestCase):

    def test_register_defaults_to_participant(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            {"username": "newbie", "password": "Sup3rSecret!x", "full_name": "New Bie"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["role"], "participant")

    def test_register_as_organizer(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            {"username": "host", "password": "Sup3rSecret!x", "role": "organizer"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["role"], "organizer")

    def test_register_duplicate_username_rejected(self):
        self.create_user("taken")
        response = self.client.post(
            "/api/v1/auth/register/",
            {"username": "taken", "password": "Sup3rSecret!x"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_register_short_password_rejected(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            {"username": "weak", "password": "short"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_register_invalid_role_rejected(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            {"username": "weird", "password": "Sup3rSecret!x", "role": "admin"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_token_obtain_returns_user_and_role_claim(self):
        user = self.create_user("rider", role="participant")
        response = self.client.post(
            "/api/v1/auth/token/", {"username": "rider", "password": PASSWORD}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["username"], "rider")
        self.assertEqual(response.data["user"]["role"], "participant")

        access = AccessToken(response.data["access"])
        self.assertEqual(access.payload["role"], "participant")
        self.assertEqual(access.payload["username"], user.username)

    def test_token_refresh_and_verify(self):
        self.create_user("rider")
        obtained = self.client.post(
            "/api/v1/auth/token/", {"username": "rider", "password": PASSWORD}, format="json"
        )
        refresh, access = obtained.data["refresh"], obtained.data["access"]

        refreshed = self.client.post(
            "/api/v1/auth/token/refresh/", {"refresh": refresh}, format="json"
        )
        self.assertEqual(refreshed.status_code, 200)
        self.assertIn("access", refreshed.data)

        verified = self.client.post(
            "/api/v1/auth/token/verify/", {"token": access}, format="json"
        )
        self.assertEqual(verified.status_code, 200)

        broken = self.client.post(
            "/api/v1/auth/token/verify/", {"token": access + "x"}, format="json"
        )
        self.assertEqual(broken.status_code, 401)

    def test_token_wrong_password_401(self):
        self.create_user("rider")
        response = self.client.post(
            "/api/v1/auth/token/", {"username": "rider", "password": "nope-nope-nope"}, format="json"
        )
        self.assertEqual(response.status_code, 401)

    def test_me_requires_authentication(self):
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 401)

    def test_me_returns_role_and_profile(self):
        user = self.create_user("rider", role="organizer")
        self.authenticate(user)
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["role"], "organizer")
        self.assertIn("profile", response.data)
