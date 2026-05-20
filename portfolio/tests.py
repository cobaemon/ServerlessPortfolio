"""
Regression tests for portfolio contact form routing and CSRF handling.
"""

import re

from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse


@override_settings(ALLOWED_HOSTS=["testserver"])
class ContactFormSecurityTests(SimpleTestCase):
    """
    Verify that the contact form posts to the registered route with CSRF enabled.
    """

    def setUp(self):
        """
        Create a CSRF-enforcing client for request/response security checks.
        """
        self.client = Client(enforce_csrf_checks=True)

    def test_contact_form_uses_named_route_and_contains_csrf_token(self):
        """
        The rendered contact form must submit to portfolio:contact and include CSRF.
        """
        response = self.client.get(reverse("portfolio:top"))
        html = response.content.decode("utf-8")
        form_html = self._extract_contact_form(html)

        self.assertEqual(response.status_code, 200)
        self.assertIn(f'action="{reverse("portfolio:contact")}"', form_html)
        self.assertIn('name="csrfmiddlewaretoken"', form_html)

    def test_contact_post_without_csrf_token_is_rejected(self):
        """
        A POST to the contact endpoint without a CSRF token must be forbidden.
        """
        response = self.client.post(reverse("portfolio:contact"), data=self._invalid_payload())

        self.assertEqual(response.status_code, 403)

    def test_contact_post_with_csrf_token_reaches_form_validation(self):
        """
        A POST with a valid CSRF token reaches the view and returns form errors.
        """
        get_response = self.client.get(reverse("portfolio:top"))
        token = self._extract_contact_form_csrf_token(get_response.content.decode("utf-8"))
        response = self.client.post(
            reverse("portfolio:contact"),
            data={
                **self._invalid_payload(),
                "csrfmiddlewaretoken": token,
            },
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(response.status_code, 400)

    def test_legacy_root_contact_url_is_not_registered(self):
        """
        The root /contact URL is not registered; the form must use /portfolio/contact.
        """
        response = self.client.post("/contact", data=self._invalid_payload())

        self.assertEqual(response.status_code, 404)

    def _invalid_payload(self):
        """
        Return valid required fields except phone number to avoid sending email.
        """
        return {
            "full_name": "Review User",
            "email": "review@example.com",
            "phone_number": "invalid-phone",
            "message": "Validation check",
        }

    def _extract_contact_form(self, html):
        """
        Extract the rendered contact form from the response HTML.
        """
        match = re.search(r'<form[^>]*id="contactForm"[^>]*>.*?</form>', html, re.S)
        self.assertIsNotNone(match)
        return match.group(0)

    def _extract_contact_form_csrf_token(self, html):
        """
        Extract the CSRF token value from the rendered contact form.
        """
        form_html = self._extract_contact_form(html)
        match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', form_html)
        self.assertIsNotNone(match)
        return match.group(1)
