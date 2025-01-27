from scripts.utils.color_utils import process_logs_and_highlight_errors

log_lines = [
    "INFO: Everything is fine",
    "ERROR: Something went wrong",
    "FAIL: Test case failed",
    "TimeoutError: Operation timed out"
]

for log in log_lines:
    highlighted_log = process_logs_and_highlight_errors(log)
    print(highlighted_log)

