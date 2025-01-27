export class ColorUtils {
    /** It is the Utility class for applying ANSI color codes to text output. */
    static RESET: string = '\u001b[0m';
    static RED: string = '\u001b[31m';
    static GREEN: string = '\u001b[32m';
   

    

    static error(text: string): string {
        /** It styles the entire block of text as red and bold. */
        return `\u001b[31m${text}\u001b[0m`;
    }
    

    static success(text: string): string {
        /** It styles text as success (green and bold). */
        return `${ColorUtils.GREEN}${text}${ColorUtils.RESET}`;
    }
    
}

export function processLogsAndHighlightErrors(logs: string): string {
    /** To wraps the entire log block in red ANSI codes. */
    return `\u001b[31m${logs}\u001b[0m`; // Entire block is wrapped in red
}

/**
 * To enhance console.error to ensure all error blocks are highlighted.
 */
export function enhancedConsoleError(logs: string): void {
    const processedLogs = processLogsAndHighlightErrors(logs);
    console.error(processedLogs);
}
