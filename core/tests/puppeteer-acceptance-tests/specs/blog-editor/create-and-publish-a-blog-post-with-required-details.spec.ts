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

/**
 * @fileoverview Acceptance Test for creating blog post with required details only.
 */

import { UserFactory } from '../../utilities/common/user-factory';
import testConstants from '../../utilities/common/test-constants';
import { BlogPostEditor } from '../../utilities/user/blog-post-editor';
import { ColorUtils, enhancedConsoleError, processLogsAndHighlightErrors } from '../../utilities/utils/color_utils';

const DEFAULT_SPEC_TIMEOUT_MSECS = testConstants.DEFAULT_SPEC_TIMEOUT_MSECS;
const ROLES = testConstants.Roles;

// Suppress external logs
const originalLog = console.log;
const originalError = console.error;

console.log = (message: string, ...args: any[]) => {
    if (message.includes('[datastore]')) return; // Suppress Datastore logs
    if (message.includes('Detected HTTP/2 connection')) return; // Suppress connection logs

    originalLog(message, ...args); // Print only relevant logs
};
console.error = (message: string, ...args: any[]) => {
    if (typeof message === 'string') {
        originalError(ColorUtils.error(message), ...args);
    } else {
        originalError(message, ...args);
    }
};
describe('Blog Editor', function () {
    let blogPostEditor: BlogPostEditor;

    // Override console.error globally for this test suite
    const originalError = console.error;
    console.error = (message: string, ...args: any[]) => {
        if (typeof message === 'string') {
            originalError(ColorUtils.error(message), ...args);
        } else {
            originalError(message, ...args);
        }
    };
    beforeAll(async () => {
        // Setup the Puppeteer page
        console.log('Initializing Puppeteer page...');
        blogPostEditor = await UserFactory.createNewUser(
            'blogPostEditor',
            'blog_post_editor@example.com',
            [ROLES.BLOG_POST_EDITOR]
        );
    
        // Override console.log and console.error in the browser context
        await blogPostEditor.page.evaluate(() => {
            const originalLog = console.log;
            const originalError = console.error;
        
            console.log = (...args) => {
                const redLogs = args.map(arg => `\u001b[31m${arg}\u001b[0m`); // Wrap all browser logs in red
                originalLog(...redLogs);
            };
        
            console.error = (...args) => {
                const redErrors = args.map(arg => `\u001b[31m${arg}\u001b[0m`); // Wrap all browser errors in red
                originalError(...redErrors);
            };
        });
        
    
        console.log('Puppeteer page initialized with red log overrides.');
    });
    
    
    

    it(
        'should create and publish a blog post with thumbnail, title, body, and tags (Intentional failure).',
        async function () {
            console.log('Starting test for blog post creation.');
            await blogPostEditor.navigateToBlogDashboardPage();
            console.log('Publishing a new blog post...');
            // Deliberately fail by using an invalid blog title.
            await blogPostEditor.publishNewBlogPost('Invalid Title That Will Fail');

            console.log('Verifying published blog post...');
            // This will fail because the title doesn't exist.
            try {
                await blogPostEditor.expectPublishedBlogPostWithTitleToBePresent('This is a test blog post');
            } catch (err) {
                console.log(ColorUtils.error(`Intentional failure: ${err.message}`));
                throw err; // Rethrow to ensure the test fails as intended.
            }            
        },
        DEFAULT_SPEC_TIMEOUT_MSECS
    );

    it(
        'should not create an empty blog post (Intentional failure).',
        async function () {
            console.log('Starting test for empty blog post.');
            await blogPostEditor.navigateToBlogDashboardPage();
            await blogPostEditor.openBlogEditorPage();

            console.log('Attempting to create an empty blog post...');
            await blogPostEditor.updateTitleTo('');
            await blogPostEditor.updateBodyTextTo('');

            try {
                console.log('Verifying publish button is disabled...');
                await blogPostEditor.expectNonExistentElementToBeVisible('#non-existent-button');
            } catch (err) {
                console.log(ColorUtils.error(`Intentional failure: ${err.message}`));
                throw err;
            }
        },
        DEFAULT_SPEC_TIMEOUT_MSECS
    );

    it('should fail due to a deliberate timeout error.', async function () {
        console.log(processLogsAndHighlightErrors('Starting test for deliberate timeout error.'));
    
        try {
            await blogPostEditor.page.waitForNavigation({
                waitUntil: 'invalid-option' as any, // Invalid value to trigger error
                timeout: 1000,
            });
        } catch (err) {
            if (err instanceof Error) {
                const fullErrorBlock = `
    Unknown value for options.waitUntil: invalid-option
    
          114 |         try {
          115 |             // Simulate a timeout error
        > 116 |             await blogPostEditor.page.waitForNavigation({
              |                                       ^
          117 |                 waitUntil: 'invalid-option' as any,
          118 |                 timeout: 1000,
          119 |             });
    
    ${err.stack || ""}
                `;
                console.error(processLogsAndHighlightErrors(fullErrorBlock)); // Entire block red
            }
            throw err; // Ensure test fails
        }
    });
    
    
    
    
    
    
    
    
    
    
    it('should fail due to missing button', async function () {
        console.log('Testing failure scenario for missing button.');
        try {
            await blogPostEditor.expectNonExistentElementToBeVisible('#non-existent-button');
        } catch (err) {
            console.log(ColorUtils.error(`Error encountered: ${err.message}`));
            throw err;
        }
    });
    afterAll(async function () {
        console.log('Closing all browser instances...');
        await UserFactory.closeAllBrowsers();
        console.log(ColorUtils.success('All browser instances closed.'));
    });
});
