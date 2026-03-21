from django.test import TestCase, Client
from django.urls import reverse
from authentication.models import User, PhoneOTP


class RegisterViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("a:register")

    def test_register_view_get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("roles", response.context)
        self.assertTemplateUsed(response, "register.html")

    def test_password_mismatch(self):
        res = self.client.post(
            self.url,
            {
                "full_name": "Test User",
                "password": "pass123",
                "confirm_password": "wrong",
            },
        )

        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Passwords do not match.")

    def test_invalid_role(self):
        res = self.client.post(
            self.url,
            {
                "full_name": "Test",
                "password": "pass123",
                "confirm_password": "pass123",
                "role": "ADMIN",
            },
        )

        self.assertContains(res, "Invalid role selected.")

    def test_phone_required(self):
        res = self.client.post(
            self.url,
            {
                "full_name": "Test",
                "password": "pass123",
                "confirm_password": "pass123",
                "signup_method": "phone",
            },
        )

        self.assertContains(res, "Phone number is required for phone signup.")

    def test_phone_signup_success(self):
        res = self.client.post(
            self.url,
            {
                "full_name": "Test",
                "password": "pass123",
                "confirm_password": "pass123",
                "signup_method": "phone",
                "phone": "+911234567890",
            },
        )

        user = User.objects.get(phone_number="+911234567890")
        otp = PhoneOTP.objects.filter(user=user).first()

        self.assertIsNotNone(user)
        self.assertIsNotNone(otp)
        self.assertFalse(otp.is_used)  # type: ignore
        self.assertRedirects(
            res, reverse("a:verify-phone-otp", kwargs={"user_id": user.pk})
        )
        self.assertEqual(res.status_code, 302)

    def test_email_required(self):
        res = self.client.post(
            self.url,
            {
                "full_name": "Test",
                "password": "pass123",
                "confirm_password": "pass123",
                "signup_method": "email",
            },
        )

        self.assertContains(res, "Email is required for email signup.")

    def test_email_signup_success(self):
        res = self.client.post(
            self.url,
            {
                "full_name": "Test",
                "password": "pass123",
                "confirm_password": "pass123",
                "signup_method": "email",
                "email": "test@test.com",
            },
        )

        user = User.objects.get(email="test@test.com")

        self.assertIsNotNone(user)
        self.assertEqual(res.status_code, 302)
