import os
import sys
import csv
import shutil
import threading
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call

# Ensure the project root is on the path so automator can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import automator
from automator import get_contacts, send_messages


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_csv(path, rows, fieldnames=None):
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ── get_contacts() tests ───────────────────────────────────────────────────────

class TestGetContacts(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_get_contacts_csv(self):
        """Reads a CSV and returns the correct list of contact dicts."""
        path = os.path.join(self.tmpdir, "contacts.csv")
        _make_csv(path, [
            {"Name": "Alice", "Phone Number": "9876543210", "Message": "Hi"},
            {"Name": "Bob",   "Phone Number": "8123456789", "Message": "Hello"},
        ])
        contacts = get_contacts(path)
        self.assertEqual(len(contacts), 2)
        self.assertEqual(contacts[0]["name"], "Alice")
        self.assertEqual(contacts[0]["number"], "9876543210")
        self.assertEqual(contacts[0]["fields"]["Message"], "Hi")
        self.assertEqual(contacts[1]["name"], "Bob")

    def test_get_contacts_missing_required_columns(self):
        """Raises ValueError when 'Phone Number' column is absent."""
        path = os.path.join(self.tmpdir, "bad.csv")
        _make_csv(path, [{"Name": "Alice", "Email": "a@b.com"}])
        with self.assertRaises(ValueError) as ctx:
            get_contacts(path)
        self.assertIn("Phone Number", str(ctx.exception))

    def test_get_contacts_returns_raw_number(self):
        """get_contacts returns the number string unchanged (no country code added here)."""
        path = os.path.join(self.tmpdir, "contacts.csv")
        _make_csv(path, [{"Name": "Alice", "Phone Number": "9876543210"}])
        contacts = get_contacts(path)
        # Country-code prepending happens in send_messages, not get_contacts
        self.assertEqual(contacts[0]["number"], "9876543210")

    def test_get_contacts_unsupported_extension(self):
        """Raises ValueError for unsupported file extensions."""
        path = os.path.join(self.tmpdir, "file.json")
        with open(path, "w") as f:
            f.write("{}")
        with self.assertRaises(ValueError) as ctx:
            get_contacts(path)
        self.assertIn("Unsupported file format", str(ctx.exception))

    def test_get_contacts_file_not_found(self):
        """Raises FileNotFoundError when called with no args and no contacts file present."""
        with patch('os.path.exists', return_value=False):
            with self.assertRaises(FileNotFoundError):
                get_contacts()


# ── send_messages() tests ──────────────────────────────────────────────────────

class TestSendMessages(unittest.TestCase):

    def _make_contact(self, name="Test User", number="9999999999"):
        return {"name": name, "number": number, "fields": {"Name": name}}

    def test_stop_event_prevents_sending(self):
        """A pre-set stop event causes early exit without calling driver.get."""
        driver = MagicMock()
        log_calls = []
        stop = threading.Event()
        stop.set()

        send_messages(driver, [self._make_contact()], "Hello {Name}",
                      log_fn=log_calls.append, stop_event=stop)

        driver.get.assert_not_called()
        self.assertTrue(any("stopped" in m.lower() for m in log_calls),
                        f"Expected stop message in log, got: {log_calls}")

    def test_log_fn_called_on_timeout(self):
        """When WebDriverWait times out, log_fn is called with an error message."""
        from selenium.common.exceptions import TimeoutException
        driver = MagicMock()
        log_calls = []

        with patch("automator.WebDriverWait") as mock_wait:
            mock_wait.return_value.until.side_effect = TimeoutException("timeout")
            send_messages(driver, [self._make_contact()], "Hello {Name}",
                          log_fn=log_calls.append)

        combined = " ".join(log_calls)
        self.assertIn("send", combined.lower(),
                      f"Expected failure message in log, got: {log_calls}")

    def test_progress_fn_called_on_success(self):
        """progress_fn is called with (1, 1) after a successful send."""
        driver = MagicMock()
        progress_calls = []

        mock_btn = MagicMock()
        with patch("automator.WebDriverWait") as mock_wait:
            mock_wait.return_value.until.return_value = mock_btn
            with patch("automator.sleep"):
                send_messages(driver, [self._make_contact()], "Hello {Name}",
                              log_fn=lambda m: None,
                              progress_fn=lambda sent, total: progress_calls.append((sent, total)))

        self.assertEqual(progress_calls, [(1, 1)],
                         f"Expected progress_fn called with (1, 1), got: {progress_calls}")

    def test_country_code_added_for_10_digit_number(self):
        """10-digit Indian numbers get '91' prepended before the URL is built."""
        driver = MagicMock()
        urls_called = []

        def capture_get(url):
            urls_called.append(url)

        driver.get.side_effect = capture_get

        with patch("automator.WebDriverWait") as mock_wait:
            mock_wait.return_value.until.return_value = MagicMock()
            with patch("automator.sleep"):
                send_messages(driver, [self._make_contact(number="9876543210")],
                              "Hi", log_fn=lambda m: None)

        self.assertTrue(any("919876543210" in u for u in urls_called),
                        f"Expected '91' prefix in URL, got: {urls_called}")

    def test_invalid_number_skipped_with_warning(self):
        """Numbers that fail validation (non-digit chars) are skipped."""
        driver = MagicMock()
        log_calls = []
        contact = {"name": "Bad", "number": "not-a-number", "fields": {"Name": "Bad"}}
        send_messages(driver, [contact], "Hi", log_fn=log_calls.append)
        driver.get.assert_not_called()

    def test_already_prefixed_number_not_double_prefixed(self):
        """Numbers already 12 digits starting with 91 are not double-prefixed."""
        driver = MagicMock()
        urls = []
        driver.get.side_effect = urls.append
        with patch("automator.WebDriverWait") as mock_wait:
            mock_wait.return_value.until.return_value = MagicMock()
            with patch("automator.sleep"):
                contact = {"name": "Test", "number": "919876543210", "fields": {"Name": "Test"}}
                send_messages(driver, [contact], "Hi", log_fn=lambda m: None)
        self.assertTrue(any("919876543210" in u and "91919876543210" not in u for u in urls))


# ── Retry logic tests ──────────────────────────────────────────────────────────

class TestRetryLogic(unittest.TestCase):

    def test_retries_on_failure_then_succeeds(self):
        """_attempt_send is retried up to 3 times; succeeds on second attempt."""
        driver = MagicMock()
        log_calls = []
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 2:
                raise Exception("timeout")
            return MagicMock()  # success on 2nd call

        with patch("automator.WebDriverWait") as mock_wait:
            mock_wait.return_value.until.side_effect = side_effect
            with patch("automator.sleep"):
                contact = {"name": "Test", "number": "9999999999", "fields": {"Name": "Test"}}
                send_messages(driver, [contact], "Hello {Name}",
                              log_fn=log_calls.append)

        self.assertEqual(call_count[0], 2)

    def test_stops_retrying_after_3_failures(self):
        """After 3 failures, moves on without raising an exception."""
        driver = MagicMock()
        log_calls = []

        with patch("automator.WebDriverWait") as mock_wait:
            mock_wait.return_value.until.side_effect = Exception("always fails")
            with patch("automator.sleep"):
                contact = {"name": "Test", "number": "9999999999", "fields": {"Name": "Test"}}
                send_messages(driver, [contact], "Hello {Name}",
                              log_fn=log_calls.append)

        # Should have attempted 3 times
        self.assertEqual(mock_wait.return_value.until.call_count, 3)


if __name__ == "__main__":
    unittest.main()
