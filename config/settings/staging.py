"""
Django settings for the AWS staging environment.

This module intentionally mirrors production security requirements while using
staging-scoped AWS values supplied through Lambda environment variables.
"""

from .prod import *

ENV = "staging"
