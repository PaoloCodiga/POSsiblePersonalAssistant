import imaplib
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.policy import default
from email.utils import getaddresses, parsedate_to_datetime


class ImapMailboxAdapter:
    """IMAP reader that returns normalized metadata and text, never stores attachment files."""

    def _connect(self, mailbox, password):
        if mailbox.imap_ssl:
            client = imaplib.IMAP4_SSL(mailbox.imap_host, mailbox.imap_port)
        else:
            client = imaplib.IMAP4(mailbox.imap_host, mailbox.imap_port)
            if mailbox.imap_starttls:
                client.starttls()
        client.login(mailbox.username, password)
        return client

    @staticmethod
    def _uidvalidity(client):
        _status, values = client.response("UIDVALIDITY")
        if not values or not values[0]:
            raise RuntimeError("IMAP server did not provide UIDVALIDITY.")
        return values[0].decode("ascii") if isinstance(values[0], bytes) else str(values[0])

    def _select(self, client, mailbox):
        status, _data = client.select(mailbox.folder, readonly=True)
        if status != "OK":
            raise RuntimeError("Configured folder is unavailable.")
        return self._uidvalidity(client)

    def test_connection(self, mailbox, password):
        client = None
        try:
            client = self._connect(mailbox, password)
            self._select(client, mailbox)
        finally:
            self._logout(client)

    def current_position(self, mailbox, password):
        client = None
        try:
            client = self._connect(mailbox, password)
            uid_validity = self._select(client, mailbox)
            status, data = client.uid("search", None, "ALL")
            if status != "OK":
                raise RuntimeError("Unable to read IMAP UID list.")
            uids = [int(value) for value in (data[0] or b"").split()]
            return uid_validity, str(max(uids)) if uids else "0"
        finally:
            self._logout(client)

    def fetch_new(self, mailbox, password, after_uid):
        client = None
        try:
            client = self._connect(mailbox, password)
            uid_validity = self._select(client, mailbox)
            status, data = client.uid("search", None, "UID %s:*" % (int(after_uid) + 1))
            if status != "OK":
                raise RuntimeError("Unable to read new IMAP UIDs.")
            messages = []
            for uid in sorted(int(value) for value in (data[0] or b"").split()):
                status, fetched = client.uid("fetch", str(uid), "(RFC822)")
                if status != "OK" or not fetched or not fetched[0]:
                    raise RuntimeError("Unable to read IMAP message UID %s." % uid)
                messages.append((str(uid), self.parse_message(fetched[0][1], mailbox.folder)))
            return uid_validity, messages
        finally:
            self._logout(client)

    @staticmethod
    def _logout(client):
        if client:
            try:
                client.logout()
            except Exception:
                pass

    @staticmethod
    def _header(message, name):
        try:
            return str(make_header(decode_header(message.get(name, ""))))
        except Exception:
            return str(message.get(name, "") or "")

    @classmethod
    def _addresses(cls, message, name):
        return [{"name": display_name, "address": address} for display_name, address in getaddresses([message.get(name, "")]) if address]

    @staticmethod
    def _text(part):
        raw = part.get_payload(decode=True) or b""
        return raw.decode(part.get_content_charset() or "utf-8", errors="replace")

    @classmethod
    def parse_message(cls, raw, folder):
        message = BytesParser(policy=default).parsebytes(raw)
        plain, html, attachments = [], [], []
        for part in message.walk() if message.is_multipart() else [message]:
            if part.is_multipart():
                continue
            content_type, disposition, filename = part.get_content_type(), (part.get_content_disposition() or "").lower(), part.get_filename()
            if disposition == "attachment" or filename:
                payload = part.get_payload(decode=False) or ""
                attachments.append({"filename": str(filename or ""), "mime_type": content_type, "size": len(payload), "content_id": str(part.get("Content-ID") or "")})
            elif content_type == "text/plain":
                plain.append(cls._text(part))
            elif content_type == "text/html":
                html.append(cls._text(part))
        date_value = cls._header(message, "Date")
        try:
            sent_at = parsedate_to_datetime(date_value).isoformat() if date_value else False
        except (TypeError, ValueError):
            sent_at = False
        return {"message_id": cls._header(message, "Message-ID"), "in_reply_to": cls._header(message, "In-Reply-To"), "references": cls._header(message, "References"), "subject": cls._header(message, "Subject"), "from": cls._addresses(message, "From"), "to": cls._addresses(message, "To"), "cc": cls._addresses(message, "Cc"), "bcc": cls._addresses(message, "Bcc"), "sent_at": sent_at, "folder": folder, "text_body": "\n".join(plain).strip(), "html_body": "\n".join(html).strip(), "has_attachments": bool(attachments), "attachments": attachments}
