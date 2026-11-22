"""Compatible local mail interface; read existing OS-keyring credentials only."""
import html
import re

import keyring
from imap_tools import MailBox

SERVICE = 'Research Organizing Skills'


def saved_password(username):
    return keyring.get_password(SERVICE, username)


def select_readonly(mailbox, folder):
    return mailbox.folder.set(folder, readonly=True)


def date_label(message):
    return message.date.isoformat()


def strip_html(value):
    value = re.sub(r'(?is)<(script|style)\b[^>]*>.*?</\1>', '', value or '')
    value = re.sub(r'(?i)<br\s*/?>|</(?:p|div|li)>', '\n', value)
    return html.unescape(re.sub(r'<[^>]+>', '', value)).strip()
