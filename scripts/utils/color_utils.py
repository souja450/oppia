class ColorUtils:
    """Utility class for applying ANSI color codes to text output."""
    RESET = '\033[0m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    BOLD = "\033[1m"




    @staticmethod
    def info(text: str) -> str:
        
        return text
        
    @staticmethod
    def colorize(text: str, color: str, bold: bool = False) -> str:
        """Applies color and optional bold styling to the given text."""
        style = f"{ColorUtils.BOLD}" if bold else ""
        return f"{style}{color}{text}{ColorUtils.RESET}"

    @staticmethod
    def error(text: str) -> str:
        """Styles text as an error (red and bold)."""
        return ColorUtils.colorize(text, color=ColorUtils.RED, bold=True)

    @staticmethod
    def success(text: str) -> str:
        """Styles text as success (green and bold)."""
        return ColorUtils.colorize(text, color=ColorUtils.GREEN, bold=True)

    @staticmethod
    def warning(text: str) -> str:
        
        return text


def process_logs_and_highlight_errors(log: str) -> str:
    """Processes logs and highlights errors or warnings."""
    error_keywords = ["ERROR", "FAIL", "TimeoutError", "Traceback"]
    warning_keywords = ["WARN"]

    if any(keyword in log for keyword in error_keywords):
        return ColorUtils.error(log)
    if any(keyword in log for keyword in warning_keywords):
        return ColorUtils.warning(log)
    return log





