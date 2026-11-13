"""Username and password accounts stored by this app."""
from .base import PasswordProvider


class LocalProvider(PasswordProvider):
    id = 'local'
    label = 'Username and password'

    def __init__(self, users):
        self.users = users

    def authenticate(self, username, password):
        return self.users.verify(username, password)
