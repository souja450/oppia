// Import your existing utilities if necessary
import { ColorUtils } from '../../utilities/utils/color_utils';
// Global console.log and console.error overrides
// Global overrides for console.log and console.error
const originalLog = console.log;
const originalError = console.error;

// Override console.log
console.log = (...args: any[]) => {
    const redLogs = args.map(arg => `\u001b[31m${arg}\u001b[0m`); // Wrap everything in red
    originalLog(...redLogs);
};

// Override console.error
console.error = (...args: any[]) => {
    const redErrors = args.map(arg => `\u001b[31m${arg}\u001b[0m`); // Wrap everything in red
    originalError(...redErrors);
};

describe('processLogsAndHighlightErrors', () => {
    test('process logs with FAIL', () => {
        expect(processLogsAndHighlightErrors("FAIL: Test failed")).toBe("\u001b[31mFAIL: Test failed\u001b[0m");
    });

    test('process logs with ERROR', () => {
        expect(processLogsAndHighlightErrors("ERROR: Something went wrong")).toBe("\u001b[31mERROR: Something went wrong\u001b[0m");
    });

    test('process logs with TimeoutError', () => {
        expect(processLogsAndHighlightErrors("TimeoutError: Operation timed out")).toBe("\u001b[31mTimeoutError: Operation timed out\u001b[0m");
    });

    test('process logs with WARN', () => {
        expect(processLogsAndHighlightErrors("WARN: Be cautious")).toBe("WARN: Be cautious");
    });

    test('process logs without error keywords', () => {
        expect(processLogsAndHighlightErrors("INFO: All is well")).toBe("\u001b[31mINFO: All is well\u001b[0m"); // Force even informational logs to be red
    });

    test('process multi-line logs', () => {
        const multiLineLog = `
        ERROR: First error line
        at someFile.js:12:34
        at anotherFile.js:56:78
        `;
        expect(processLogsAndHighlightErrors(multiLineLog)).toBe(
            `\u001b[31m\n        ERROR: First error line\n        at someFile.js:12:34\n        at anotherFile.js:56:78\n        \u001b[0m`
        );
    });
});


export function processLogsAndHighlightErrors(logs: string): string {
    // Wrap the entire log block in red ANSI codes
    return `\u001b[31m${logs}\u001b[0m`;
}

