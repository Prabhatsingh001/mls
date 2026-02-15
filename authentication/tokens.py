"""
Token generation utilities for secure user verification processes.

This module provides token generators for:
- Email verification during account activation
- Password reset verification

The tokens are time-sensitive and user-specific, incorporating user attributes
to ensure security and prevent token reuse across different actions.
"""

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from six import text_type


class TokenGenerator(PasswordResetTokenGenerator):
    """
    Custom token generator for email verification.

    Extends Django's PasswordResetTokenGenerator to create secure, time-sensitive
    tokens for email verification. The token includes the user's activation status
    to invalidate it after activation.
    """

    def _make_hash_value(self, user, timestamp):
        """
        Create a hash value for the verification token.

        Args:
            user: The user instance for whom the token is being generated
            timestamp: Current timestamp for token expiration

        Returns:
            String concatenation of user ID, timestamp, and activation status,
            ensuring the token becomes invalid after account activation.
        """
        return text_type(user.pk) + text_type(timestamp) + text_type(user.is_active)


# Token generator instance for email verification
account_activation_token = TokenGenerator()

# Token generator instance for password reset
# Uses Django's built-in generator as it handles all necessary security measures
password_reset_token = PasswordResetTokenGenerator()
