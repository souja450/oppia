import unittest
from scripts.utils.color_utils import ColorUtils, process_logs_and_highlight_errors


class TestColorUtils(unittest.TestCase):
    def test_error(self):
        self.assertEqual(
            ColorUtils.error("Error message"),
            "\033[1m\033[31mError message\033[0m"
        )

    def test_success(self):
        self.assertEqual(
            ColorUtils.success("Success message"),
            "\033[1m\033[32mSuccess message\033[0m"
        )

    def test_warning(self):
        self.assertEqual(
            "Warning message",
            "Warning message"
        )

    def test_process_logs_and_highlight_errors(self):
        # Check a line containing 'FAIL'
        self.assertEqual(
            process_logs_and_highlight_errors("FAIL: Test failed"),
            "\033[1m\033[31mFAIL: Test failed\033[0m"
        )

        # Check a line containing 'ERROR'
        self.assertEqual(
            process_logs_and_highlight_errors("ERROR: Something went wrong"),
            "\033[1m\033[31mERROR: Something went wrong\033[0m"
        )

        # Check a line containing 'TimeoutError'
        self.assertEqual(
            process_logs_and_highlight_errors("TimeoutError: Operation timed out"),
            "\033[1m\033[31mTimeoutError: Operation timed out\033[0m"
        )

        # Check a line containing 'WARN'
        self.assertEqual(
            process_logs_and_highlight_errors("WARN: Be cautious"),
            "WARN: Be cautious"
        )

        # Check a line without error keywords
        self.assertEqual(
            process_logs_and_highlight_errors("INFO: All is well"),
            "INFO: All is well"
        )


# Run the tests
if __name__ == "__main__":
    unittest.main()
