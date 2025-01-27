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
 * @fileoverview Acceptance Test for creating and deleting draft blog posts.
 */

import {UserFactory} from '../../utilities/common/user-factory';
import testConstants from '../../utilities/common/test-constants';
import {BlogPostEditor} from '../../utilities/user/blog-post-editor';
import { ColorUtils, processLogsAndHighlightErrors } from '../../utilities/utils/color_utils';


const DEFAULT_SPEC_TIMEOUT_MSECS = testConstants.DEFAULT_SPEC_TIMEOUT_MSECS;
const ROLES = testConstants.Roles;

describe('Blog Editor', function () {
  let blogPostEditor: BlogPostEditor;

  beforeAll(
    async function () {
      try {
        console.log('Setting up Blog Editor user...');
        blogPostEditor = await UserFactory.createNewUser(
          'blogPostEditor',
          'blog_post_editor@example.com',
          [ROLES.BLOG_POST_EDITOR]
        );
        console.log(ColorUtils.success('Blog Editor user setup complete.'));
      } catch (error) {
        console.error(ColorUtils.error(`Failed to set up Blog Editor user: ${error}`));
        throw error; // Re-throw to let the test framework handle it.
      }
    },
    DEFAULT_SPEC_TIMEOUT_MSECS
  );

  it(
    ('should create and delete draft blog post'),
    async function () {
      try {
        console.log('Navigating to Blog Dashboard Page...');
        await blogPostEditor.navigateToBlogDashboardPage();
        console.log('Checking initial blog post count...');
        await blogPostEditor.expectNumberOfBlogPostsToBe(0);

        console.log('Creating a draft blog post...');
        await blogPostEditor.createDraftBlogPostWithTitle('Test Blog Post');

        console.log('Verifying draft blog post creation...');
        await blogPostEditor.navigateToBlogDashboardPage();
        await blogPostEditor.expectNumberOfBlogPostsToBe(1);
        await blogPostEditor.expectDraftBlogPostWithTitleToBePresent(
          'Test Blog Post'
        );

        console.log('Deleting the draft blog post...');
        await blogPostEditor.deleteDraftBlogPostWithTitle('Test Blog Post');
        console.log('Verifying draft blog post deletion...');
        await blogPostEditor.expectNumberOfBlogPostsToBe(0);

        console.log(ColorUtils.success('Draft blog post test completed successfully.'));
      } catch (error) {
        console.error(
          ColorUtils.error(
            `Error during draft blog post test: ${error.message || error}`
          )
        );
        throw error; // Re-throw to ensure test fails in the framework.
      }
    },
    DEFAULT_SPEC_TIMEOUT_MSECS
  );

  afterAll(
    async function () {
      try {
        console.log('Closing all browser instances...');
        await UserFactory.closeAllBrowsers();
        console.log(ColorUtils.success('Browser instances closed.'));
      } catch (error) {
        console.error(
          ColorUtils.error(`Error during cleanup: ${error.message || error}`)
        );
        throw error; // Re-throw to signal cleanup failure.
      }
    }
  );
});