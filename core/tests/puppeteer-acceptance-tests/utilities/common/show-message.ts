// Copyright 2024 The Oppia Authors. All Rights Reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS-IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { execSync } from 'child_process';

/**
 * Utility function to log messages with colorized output.
 */
export function showMessage(
  type: 'error' | 'warning' | 'success',
  message: string
): void {
  try {
    // Serialize the message to ensure proper escaping of quotes and special characters
    const serializedMessage = JSON.stringify(message);

    // Construct the Python command using single quotes to wrap the entire command
    // and inject the serialized message directly
    const command = `python -c 'from scripts.common import print_${type}_message; print_${type}_message(${serializedMessage})'`;

    // Log the command for debugging purposes (optional)
    console.log(`Executing command: ${command}`);

    // Execute the command
    execSync(command, { stdio: 'inherit' });
  } catch (error) {
    console.error('Failed to print message:', error);
  }
}




