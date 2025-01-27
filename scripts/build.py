# Copyright 2014 The Oppia Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Build file for production version of Oppia. Minifies JS and CSS."""

from __future__ import annotations

import argparse
import collections
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from scripts.utils.color_utils import ColorUtils  # Importing ColorUtils
from core import feconf
from core import utils
from scripts import common
import rcssmin
from typing import (
    Deque, Dict, List, Optional, Sequence, TextIO, Tuple, TypedDict
)

if not feconf.OPPIA_IS_DOCKERIZED:
    from scripts import install_python_dev_dependencies
    from scripts import install_third_party_libs
    from scripts import servers

ASSETS_DEV_DIR = os.path.join('assets', '')
ASSETS_OUT_DIR = os.path.join('build', 'assets', '')

THIRD_PARTY_STATIC_DIR = os.path.join('third_party', 'static')
THIRD_PARTY_GENERATED_DEV_DIR = os.path.join('third_party', 'generated', '')
THIRD_PARTY_GENERATED_OUT_DIR = os.path.join(
    'build', 'third_party', 'generated', '')

THIRD_PARTY_JS_RELATIVE_FILEPATH = os.path.join('js', 'third_party.js')
MINIFIED_THIRD_PARTY_JS_RELATIVE_FILEPATH = os.path.join(
    'js', 'third_party.min.js')

THIRD_PARTY_CSS_RELATIVE_FILEPATH = os.path.join('css', 'third_party.css')
MINIFIED_THIRD_PARTY_CSS_RELATIVE_FILEPATH = os.path.join(
    'css', 'third_party.min.css')

WEBFONTS_RELATIVE_DIRECTORY_PATH = os.path.join('webfonts', '')

EXTENSIONS_DIRNAMES_TO_DIRPATHS = {
    'dev_dir': os.path.join('extensions', ''),
    'staging_dir': os.path.join('backend_prod_files', 'extensions', ''),
    'out_dir': os.path.join('build', 'extensions', '')
}
TEMPLATES_DEV_DIR = os.path.join('templates', '')
TEMPLATES_CORE_DIRNAMES_TO_DIRPATHS = {
    'dev_dir': os.path.join('core', 'templates', ''),
    'staging_dir': os.path.join('backend_prod_files', 'templates', ''),
    'out_dir': os.path.join('build', 'templates', '')
}
WEBPACK_DIRNAMES_TO_DIRPATHS = {
    'staging_dir': os.path.join('backend_prod_files', 'webpack_bundles', ''),
    'out_dir': os.path.join('build', 'webpack_bundles', '')
}

# This json file contains a json object. The object's keys are file paths and
# the values are corresponded hash value. The paths need to be in posix style,
# as it is interpreted by the `url-interpolation` service, which which
# interprets the paths in this file as URLs.
HASHES_JSON_FILENAME = 'hashes.json'
HASHES_JSON_FILEPATH = os.path.join('assets', HASHES_JSON_FILENAME)
DEPENDENCIES_FILE_PATH = os.path.join('dependencies.json')

REMOVE_WS = re.compile(r'\s{2,}').sub

PARENT_DIR = os.path.abspath(os.path.join(os.getcwd(), os.pardir))
UGLIFY_FILE = os.path.join('node_modules', 'uglify-js', 'bin', 'uglifyjs')
WEBPACK_FILE = os.path.join('node_modules', 'webpack', 'bin', 'webpack.js')
WEBPACK_DEV_CONFIG = 'webpack.dev.config.ts'
WEBPACK_DEV_SOURCE_MAPS_CONFIG = 'webpack.dev.sourcemap.config.ts'
WEBPACK_PROD_CONFIG = 'webpack.prod.config.ts'
WEBPACK_PROD_SOURCE_MAPS_CONFIG = 'webpack.prod.sourcemap.config.ts'

# Files with these extensions shouldn't be moved to build directory.
FILE_EXTENSIONS_TO_IGNORE = ('.py', '.pyc', '.stylelintrc', '.ts', '.gitkeep')
# Files with these name patterns shouldn't be moved to build directory, and will
# not be served in production. (This includes webdriverio.js
# files in /extensions.)
JS_FILENAME_SUFFIXES_TO_IGNORE = ('Spec.js', 'webdriverio.js')
JS_FILENAME_SUFFIXES_NOT_TO_MINIFY = ('.bundle.js',)
GENERAL_FILENAMES_TO_IGNORE = ('.pyc', '.stylelintrc', '.DS_Store')

JS_FILEPATHS_NOT_TO_BUILD = (
    os.path.join(
        'core', 'templates', 'expressions', 'parser.js'),
    os.path.join('extensions', 'ckeditor_plugins', 'pre', 'plugin.js')
)

# These filepaths shouldn't be renamed (i.e. the filepath shouldn't contain
# hash).
# This is because these files don't need cache invalidation, are referenced
# from third party files or should not be moved to the build directory.
# Statically served pages from app.yaml should be here to since they don't
# need cache invalidation.
FILEPATHS_NOT_TO_RENAME = (
    '*.py',
    'third_party/generated/js/third_party.min.js.map',
    'third_party/generated/webfonts/*',
    '*.bundle.js',
    '*.bundle.js.map',
    'webpack_bundles/*',
)

# These are the env vars that need to be removed from app.yaml when we are
# deploying to production.
ENV_VARS_TO_REMOVE_FROM_DEPLOYED_APP_YAML = (
    'FIREBASE_AUTH_EMULATOR_HOST',
    'DATASTORE_DATASET',
    'DATASTORE_EMULATOR_HOST',
    'DATASTORE_EMULATOR_HOST_PATH',
    'DATASTORE_HOST',
    'DATASTORE_PROJECT_ID',
    'DATASTORE_USE_PROJECT_ID_AS_APP_ID'
)

# Hashes for files with these paths should be provided to the frontend in
# JS hashes object.
FILEPATHS_PROVIDED_TO_FRONTEND = (
    'images/*', 'videos/*', 'i18n/*', '*.component.html',
    '*_directive.html', '*.directive.html', 'audio/*',
    '*.template.html', '*.png', '*.json', '*.webp')

HASH_BLOCK_SIZE = 2**20

APP_DEV_YAML_FILEPATH = (
    'app_dev_docker.yaml' if feconf.OPPIA_IS_DOCKERIZED else 'app_dev.yaml'
)

APP_YAML_FILEPATH = 'app.yaml'

MAX_OLD_SPACE_SIZE_FOR_WEBPACK_BUILD = 8192

_PARSER = argparse.ArgumentParser(
    description="""
Creates a third-party directory where all the JS and CSS dependencies are
built and stored. Depending on the options passed to the script, might also
minify third-party libraries and/or generate a build directory.
""")

_PARSER.add_argument(
    '--prod_env', action='store_true', default=False, dest='prod_env')
_PARSER.add_argument(
    '--deploy_mode', action='store_true', default=False, dest='deploy_mode')
_PARSER.add_argument(
    '--minify_third_party_libs_only', action='store_true', default=False,
    dest='minify_third_party_libs_only')
_PARSER.add_argument(
    '--maintenance_mode',
    action='store_true',
    default=False,
    dest='maintenance_mode',
    help=(
        'Enable maintenance mode, '
        'meaning that only super admins can access the site.'
    )
)
_PARSER.add_argument(
    '--source_maps',
    action='store_true',
    default=False,
    dest='source_maps',
    help='Build webpack with source maps.')


class DependencyBundleDict(TypedDict):
    """Dictionary that represents dependency bundle."""

    js: List[str]
    css: List[str]
    fontsPath: str


def run_webpack_compilation(source_maps: bool = False) -> None:
    """Runs webpack compilation.

    Args:
        source_maps: bool. Whether to compile with source maps.
    """
    max_tries = 5
    webpack_bundles_dir_name = 'webpack_bundles'

    for _ in range(max_tries):
        try:
            managed_webpack_compiler = (
                servers.managed_webpack_compiler(use_source_maps=source_maps))
            with managed_webpack_compiler as proc:
                proc.wait()
        except subprocess.CalledProcessError as error:
            print(error.output)
            sys.exit(error.returncode)
        if os.path.isdir(webpack_bundles_dir_name):
            break
    else:
        # We didn't break out of the loop, meaning all attempts have failed.
        print(ColorUtils.error("Failed to complete webpack compilation, exiting..."))
        sys.exit(1)


def build_js_files(dev_mode: bool, source_maps: bool = False) -> None:
    """Build the javascript files.

    Args:
        dev_mode: bool. Represents whether to run the related commands in dev
            mode.
        source_maps: bool. Represents whether to use source maps while
            building webpack.
    """
    if not dev_mode:
        print(ColorUtils.success("Generating files for production mode..."))

        build_args = ['--prod_env']
        if source_maps:
            build_args.append('--source_maps')
        main(args=build_args)

    else:
        main(args=[])
        common.run_ng_compilation()
        if not feconf.OPPIA_IS_DOCKERIZED:
            run_webpack_compilation(source_maps=source_maps)


def generate_app_yaml(deploy_mode: bool = False) -> None:
    """Generate app.yaml from app_dev.yaml.

    Args:
        deploy_mode: bool. Whether the script is being called from deploy
            script.

    Raises:
        Exception. Environment variable to be removed does not exist.
    """
    content = '# THIS FILE IS AUTOGENERATED, DO NOT MODIFY\n'
    with utils.open_file(APP_DEV_YAML_FILEPATH, 'r') as yaml_file:
        content += yaml_file.read()

    if deploy_mode:
        # The version: default line is required to run jobs on a local server (
        # both in prod & non-prod env). This line is not required when app.yaml
        # is generated during deployment. So, we remove this if the build
        # process is being run from the deploy script.
        content = content.replace('version: default', '')
        # The FIREBASE_AUTH_EMULATOR_HOST environment variable is only needed to
        # test locally, and MUST NOT be included in the deployed file.
        for env_variable in ENV_VARS_TO_REMOVE_FROM_DEPLOYED_APP_YAML:
            if env_variable not in content:
                raise Exception(
                    'Environment variable \'%s\' to be '
                    'removed does not exist.' % env_variable
                )
            content = re.sub('  %s: ".*"\n' % env_variable, '', content)
    if os.path.isfile(APP_YAML_FILEPATH):
        os.remove(APP_YAML_FILEPATH)
    with utils.open_file(APP_YAML_FILEPATH, 'w+') as prod_yaml_file:
        prod_yaml_file.write(content)


def _minify_css(source_path: str, target_path: str) -> None:
    """Runs the given file through a minifier and outputs it to target_path.

    Args:
        source_path: str. Absolute path to file to be minified.
        target_path: str. Absolute path to location where to copy
            the minified file.
    """
    source_path = os.path.relpath(source_path)
    target_path = os.path.relpath(target_path)
    with utils.open_file(source_path, 'r') as source_file:
        with utils.open_file(target_path, 'w') as target_file:
            target_file.write(rcssmin.cssmin(source_file.read()))


def write_to_file_stream(file_stream: TextIO, content: str) -> None:
    """Write to a file object using provided content.

    Args:
        file_stream: file. A stream handling object to do write operation on.
        content: str. String content to write to file object.
    """
    file_stream.write(str(content))


def _join_files(
    source_paths: List[str], target_file_stream: TextIO
) -> None:
    """Writes multiple files into one file.

    Args:
        source_paths: list(str). Paths to files to join together.
        target_file_stream: file. A stream object of target file.
    """
    for source_path in source_paths:
        with utils.open_file(source_path, 'r') as source_file:
            write_to_file_stream(target_file_stream, source_file.read())


def _minify_and_create_sourcemap(
    source_path: str, target_file_path: str
) -> None:
    """Minifies and generates source map for a JS file. This function is only
    meant to be used with third_party.min.js.

    Args:
        source_path: str. Path to JS file to minify.
        target_file_path: str. Path to location of the minified file.
    """
    print(ColorUtils.success("Minifying and creating sourcemap for %s" % source_path))
    source_map_properties = 'includeSources,url=\'third_party.min.js.map\''
    # TODO(#18260): Change this when we permanently move to
    # the Dockerized Setup.
    if feconf.OPPIA_IS_DOCKERIZED:
        subprocess.check_call(
            'node /app/oppia/node_modules/uglify-js/bin/uglifyjs'
            ' /app/oppia/third_party/generated/js/third_party.js'
            ' -c -m --source-map includeSources,url=\'third_party.min.js.map\''
            ' -o /app/oppia/third_party/generated/js/third_party.min.js',
            shell=True
        )
    else:
        cmd = '%s %s %s -c -m --source-map %s -o %s ' % (
            common.NODE_BIN_PATH, UGLIFY_FILE, source_path,
            source_map_properties, target_file_path)
        subprocess.check_call(cmd, shell=True)


def _generate_copy_tasks_for_fonts(
    source_paths: List[str], target_path: str
) -> Deque[threading.Thread]:
    """Queue up a copy task for each font file.

    Args:
        source_paths: list(str). Paths to fonts.
        target_path: str. Path where the fonts should be copied.

    Returns:
        deque(Thread). A deque that contains all copy tasks queued to be
        processed.
    """
    copy_tasks: Deque[threading.Thread] = collections.deque()
    for font_path in source_paths:
        copy_task = threading.Thread(
            target=shutil.copy,
            args=(font_path, target_path,))
        copy_tasks.append(copy_task)
    return copy_tasks


def _insert_hash(filepath: str, file_hash: str) -> str:
    """Inserts hash into filepath before the file extension.

    Args:
        filepath: str. Path where the hash should be inserted.
        file_hash: str. Hash to be inserted into the path.

    Returns:
        str. Filepath with hash inserted.
    """
    filepath, file_extension = os.path.splitext(filepath)
    return '%s.%s%s' % (filepath, file_hash, file_extension)


def safe_delete_directory_tree(directory_path: str) -> None:
    """Recursively delete a directory tree. If directory tree does not exist,
    create the directories first then delete the directory tree.

    Args:
        directory_path: str. Directory path to be deleted.
    """
    common.ensure_directory_exists(directory_path)
    shutil.rmtree(directory_path)


def _ensure_files_exist(filepaths: List[str]) -> None:
    """Ensures that files exist at the given filepaths.

    Args:
        filepaths: list(str). Paths to files that we want to ensure exist.

    Raises:
        OSError. One or more of the files does not exist.
    """
    for filepath in filepaths:
        if not os.path.isfile(filepath):
            raise OSError('File %s does not exist.' % filepath)


def safe_copy_file(source_filepath: str, target_filepath: str) -> None:
    """Copy a file (no metadata) after ensuring the file exists at the given
    source filepath.
    NOTE: shutil.copyfile does not accept directory path as arguments.

    Args:
        source_filepath: str. Path to source file that we want to copy from.
        target_filepath: str. Path to target file that we want to copy to.
    """
    _ensure_files_exist([source_filepath])
    shutil.copyfile(source_filepath, target_filepath)


def safe_delete_file(filepath: str) -> None:
    """Delete a file after ensuring the provided file actually exists.

    Args:
        filepath: str. Filepath to be deleted.
    """
    _ensure_files_exist([filepath])
    os.remove(filepath)


def get_file_count(directory_path: str) -> int:
    """Count total number of file in the given directory, ignoring any files
    with extensions in FILE_EXTENSIONS_TO_IGNORE or files that should not be
    built.

    Args:
        directory_path: str. Directory to be walked.

    Returns:
        int. Total number of files minus ignored files.
    """
    total_file_count = 0
    for root, _, filenames in os.walk(directory_path):
        for filename in filenames:
            # Ignore files with certain extensions.
            filepath = os.path.join(root, filename)
            if should_file_be_built(filepath) and not any(
                    filename.endswith(p) for p in FILE_EXTENSIONS_TO_IGNORE):
                total_file_count += 1
    return total_file_count


def _compare_file_count(
    first_dir_list: List[str], second_dir_list: List[str]
) -> None:
    """Ensure that the total count of files in all directories in the first
    list matches the count of files in all the directories in the second list.

    Args:
        first_dir_list: list(str). List of directories to compare.
        second_dir_list: list(str). List of directories to compare.

    Raises:
        ValueError. The source directory list does not have the same file
            count as the target directory list.
    """

    file_counts = [0, 0]
    for first_dir_path in first_dir_list:
        file_counts[0] += get_file_count(first_dir_path)
    for second_dir_path in second_dir_list:
        file_counts[1] += get_file_count(second_dir_path)
    if file_counts[0] != file_counts[1]:
        print('Comparing %s vs %s' % (first_dir_list, second_dir_list))
    raise ValueError(
        ColorUtils.error(
            "%s files in first dir list != %s files in second dir list" % (
                file_counts[0], file_counts[1]
            )
        )
    )


def process_html(
    source_file_stream: TextIO, target_file_stream: TextIO
) -> None:
    """Remove whitespaces and add hashes to filepaths in the HTML file stream
    object.

    Args:
        source_file_stream: file. The stream object of the HTML file to be
            read from.
        target_file_stream: file. The stream object to write the minified HTML
            file to.
    """
    write_to_file_stream(
        target_file_stream, REMOVE_WS(' ', source_file_stream.read()))


def get_dependency_directory(dependency: Dict[str, str]) -> str:
    """Get dependency directory from dependency dictionary.

    Args:
        dependency: dict(str, str). Dictionary representing single dependency
            from dependencies.json.

    Returns:
        str. Dependency directory.
    """
    if 'targetDir' in dependency:
        dependency_dir = dependency['targetDir']
    else:
        dependency_dir = dependency['targetDirPrefix'] + dependency['version']
    return os.path.join(THIRD_PARTY_STATIC_DIR, dependency_dir)


def get_css_filepaths(
    dependency_bundle: DependencyBundleDict, dependency_dir: str
) -> List[str]:
    """Gets dependency css filepaths.

    Args:
        dependency_bundle: dict(str, list(str) | str). The dict has three keys:
            - 'js': List of paths to js files that need to be copied.
            - 'css': List of paths to css files that need to be copied.
            - 'fontsPath': Path to folder containing fonts that need to be
                copied.
        dependency_dir: str. Path to directory where the files that need to
            be copied are located.

    Returns:
        list(str). List of paths to css files that need to be copied.
    """
    css_files = dependency_bundle.get('css', [])
    return [os.path.join(dependency_dir, css_file) for css_file in css_files]


def get_js_filepaths(
    dependency_bundle: DependencyBundleDict, dependency_dir: str
) -> List[str]:
    """Gets dependency js filepaths.

    Args:
        dependency_bundle: dict(str, list(str) | str). The dict has three keys:
            - 'js': List of paths to js files that need to be copied.
            - 'css': List of paths to css files that need to be copied.
            - 'fontsPath': Path to folder containing fonts that need to be
                copied.
        dependency_dir: str. Path to directory where the files that need to
            be copied are located.

    Returns:
        list(str). List of paths to js files that need to be copied.
    """
    js_files = dependency_bundle.get('js', [])
    return [os.path.join(dependency_dir, js_file) for js_file in js_files]


def get_font_filepaths(
    dependency_bundle: DependencyBundleDict, dependency_dir: str
) -> List[str]:
    """Gets dependency font filepaths.

    Args:
        dependency_bundle: dict(str, list(str) | str). The dict has three keys:
            - 'js': List of paths to js files that need to be copied.
            - 'css': List of paths to css files that need to be copied.
            - 'fontsPath': Path to folder containing fonts that need to be
                copied.
        dependency_dir: str. Path to directory where the files that need to
            be copied are located.

    Returns:
        list(str). List of paths to font files that need to be copied.
    """
    if 'fontsPath' not in dependency_bundle:
        # Skip dependency bundles in dependencies.json that do not have
        # fontsPath property.
        return []
    fonts_path = dependency_bundle['fontsPath']
    # Obtain directory path to /font inside dependency folder.
    # E.g. third_party/static/bootstrap-3.3.4/fonts/.
    font_dir = os.path.join(dependency_dir, fonts_path)
    font_filepaths = []
    # Walk the directory and add all font files to list.
    for root, _, filenames in os.walk(font_dir):
        for filename in filenames:
            font_filepaths.append(os.path.join(root, filename))
    return font_filepaths


def get_dependencies_filepaths() -> Dict[str, List[str]]:
    """Extracts dependencies filepaths from dependencies.json file into
    a dictionary.

    Returns:
        dict(str, list(str)). A dict mapping file types to lists of filepaths.
        The dict has three keys: 'js', 'css' and 'fonts'. Each of the
        corresponding values is a full list of dependency file paths of the
        given type.
    """
    filepaths: Dict[str, List[str]] = {
        'js': [],
        'css': [],
        'fonts': []
    }
    with utils.open_file(DEPENDENCIES_FILE_PATH, 'r') as json_file:
        dependencies_json = json.loads(
            json_file.read(), object_pairs_hook=collections.OrderedDict)
    frontend_dependencies = dependencies_json['frontendDependencies']
    for dependency in frontend_dependencies.values():
        if 'bundle' in dependency:
            dependency_dir = get_dependency_directory(dependency)
            filepaths['css'].extend(
                get_css_filepaths(dependency['bundle'], dependency_dir))
            filepaths['js'].extend(
                get_js_filepaths(dependency['bundle'], dependency_dir))
            filepaths['fonts'].extend(
                get_font_filepaths(dependency['bundle'], dependency_dir))

    _ensure_files_exist(filepaths['js'])
    _ensure_files_exist(filepaths['css'])
    _ensure_files_exist(filepaths['fonts'])
    return filepaths


def minify_third_party_libs(third_party_directory_path: str) -> None:
    """Minify third_party.js and third_party.css and remove un-minified
    files.
    """
    third_party_js_filepath = os.path.join(
        third_party_directory_path, THIRD_PARTY_JS_RELATIVE_FILEPATH)
    third_party_css_filepath = os.path.join(
        third_party_directory_path, THIRD_PARTY_CSS_RELATIVE_FILEPATH)

    minified_third_party_js_filepath = os.path.join(
        third_party_directory_path, MINIFIED_THIRD_PARTY_JS_RELATIVE_FILEPATH)
    minified_third_party_css_filepath = os.path.join(
        third_party_directory_path, MINIFIED_THIRD_PARTY_CSS_RELATIVE_FILEPATH)

    _minify_and_create_sourcemap(
        third_party_js_filepath, minified_third_party_js_filepath)
    _minify_css(third_party_css_filepath, minified_third_party_css_filepath)
    # Clean up un-minified third_party.js and third_party.css.
    safe_delete_file(third_party_js_filepath)
    safe_delete_file(third_party_css_filepath)


def build_third_party_libs(third_party_directory_path: str) -> None:
    """Joins all third party css files into single css file and js files into
    single js file. Copies both files and all fonts into third party folder.
    """
    print(ColorUtils.success('Building third party libs at %s' % third_party_directory_path))

    third_party_js_filepath = os.path.join(
        third_party_directory_path, THIRD_PARTY_JS_RELATIVE_FILEPATH)
    third_party_css_filepath = os.path.join(
        third_party_directory_path, THIRD_PARTY_CSS_RELATIVE_FILEPATH)
    webfonts_dir = os.path.join(
        third_party_directory_path, WEBFONTS_RELATIVE_DIRECTORY_PATH)

    dependency_filepaths = get_dependencies_filepaths()

    # Ensure JS file is created
    common.ensure_directory_exists(os.path.dirname(third_party_js_filepath))
    with utils.open_file(
        third_party_js_filepath, 'w+') as third_party_js_file:
        print(ColorUtils.info(f'Joining JS dependencies into {third_party_js_filepath}'))
        _join_files(dependency_filepaths['js'], third_party_js_file)

    # Ensure CSS file is created
    common.ensure_directory_exists(os.path.dirname(third_party_css_filepath))
    with utils.open_file(
        third_party_css_filepath, 'w+') as third_party_css_file:
        print(ColorUtils.info(f'Joining CSS dependencies into {third_party_css_filepath}'))
        _join_files(dependency_filepaths['css'], third_party_css_file)

    # Ensure fonts directory is prepared
    common.ensure_directory_exists(webfonts_dir)
    print(ColorUtils.info(f'Copying font dependencies to {webfonts_dir}'))
    _execute_tasks(
        _generate_copy_tasks_for_fonts(
            dependency_filepaths['fonts'], webfonts_dir))

    print(ColorUtils.success('Third party libraries built successfully.'))



def build_using_ng() -> None:
    """Execute angular build process. This runs the angular compiler and
    generates an ahead-of-time compiled bundle. This bundle can be found in the
    dist/oppia-angular-prod folder.
    """
    print(ColorUtils.info('Building using Angular CLI...'))
    managed_ng_build_process = servers.managed_ng_build(
        use_prod_env=True, watch_mode=False)
    with managed_ng_build_process as p:
        p.wait()
    if get_file_count('dist/oppia-angular-prod') > 0:
        print(ColorUtils.success('Angular build completed successfully.'))
    else:
        raise AssertionError(
            ColorUtils.error('Angular generated bundle should be non-empty.')
        )


def build_using_webpack(config_path: str) -> None:
    """Execute webpack build process. This takes all TypeScript files we have in
    /templates and generates JS bundles according to the require() imports
    and also compiles HTML pages into the /backend_prod_files/webpack_bundles
    folder. The files are later copied into /build/webpack_bundles.

    Args:
        config_path: str. Webpack config to be used for building.
    """
    print(ColorUtils.info('Building using Webpack...'))
    managed_webpack_compiler = servers.managed_webpack_compiler(
        config_path=config_path,
        max_old_space_size=MAX_OLD_SPACE_SIZE_FOR_WEBPACK_BUILD)
    with managed_webpack_compiler as p:
        p.wait()
    if get_file_count('backend_prod_files/webpack_bundles/') > 0:
        print(ColorUtils.success('Webpack build completed successfully.'))
    else:
        raise AssertionError(
            ColorUtils.error('Webpack bundles should be non-empty.')
        )

def hash_should_be_inserted(filepath: str) -> bool:
    """Returns if the file should be renamed to include hash in
    the path.

    Args:
        filepath: str. Path relative to directory we are currently building.

    Returns:
        bool. True if filepath should contain hash else False.
    """
    return not any(
        fnmatch.fnmatch(filepath, pattern) for pattern
        in FILEPATHS_NOT_TO_RENAME)


def should_file_be_built(filepath: str) -> bool:
    """Determines if the file should be built.
        - JS files: Returns False if filepath matches with pattern in
        JS_FILENAME_SUFFIXES_TO_IGNORE or is in JS_FILEPATHS_NOT_TO_BUILD,
        else returns True.
        - Python files: Returns False if filepath ends with _test.py, else
        returns True
        - TS files: Returns False.
        - Other files: Returns False if filepath matches with pattern in
        GENERAL_FILENAMES_TO_IGNORE, else returns True.

    Args:
        filepath: str. Path relative to file we are currently building.

    Returns:
        bool. True if filepath should be built, else False.
    """
    if filepath.endswith('.js'):
        return all(
            not filepath.endswith(p) for p in JS_FILENAME_SUFFIXES_TO_IGNORE)
    elif filepath.endswith('_test.py'):
        return False
    elif filepath.endswith('.ts'):
        return False
    else:
        return not any(
            filepath.endswith(p) for p in GENERAL_FILENAMES_TO_IGNORE)


def generate_copy_tasks_to_copy_from_source_to_target(
    source: str, target: str, file_hashes: Dict[str, str]
) -> Deque[threading.Thread]:
    """Generate copy task for each file in source directory, excluding files
    with extensions in FILE_EXTENSIONS_TO_IGNORE. Insert hash from hash dict
    into the destination filename.

    Args:
        source: str. Path relative to /oppia directory of directory
            containing files and directories to be copied.
        target: str. Path relative to /oppia directory of directory where
            to copy the files and directories.
        file_hashes: dict(str, str). Dictionary with filepaths as keys and
            hashes of file content as values.

    Returns:
        deque(Thread). A deque that contains all copy tasks queued
        to be processed.
    """
    print(ColorUtils.info('Processing %s' % os.path.join(os.getcwd(), source)))
    print(ColorUtils.info('Copying into %s' % os.path.join(os.getcwd(), target)))

    copy_tasks: Deque[threading.Thread] = collections.deque()
    for root, dirnames, filenames in os.walk(os.path.join(os.getcwd(), source)):
        for directory in dirnames:
            print(ColorUtils.success('Copying %s' % os.path.join(root, directory)))
        for filename in filenames:
            source_path = os.path.join(root, filename)
            # Python files should not be copied to final build directory.
            if not any(
                    source_path.endswith(p) for p in FILE_EXTENSIONS_TO_IGNORE):
                target_path = source_path
                relative_path = os.path.relpath(source_path, start=source)
                if (hash_should_be_inserted(source + relative_path) and
                        relative_path in file_hashes):
                    relative_path = (
                        _insert_hash(relative_path, file_hashes[relative_path]))

                target_path = os.path.join(os.getcwd(), target, relative_path)
                common.ensure_directory_exists(os.path.dirname(target_path))
                copy_task = threading.Thread(
                    target=safe_copy_file,
                    args=(source_path, target_path,))
                copy_tasks.append(copy_task)
                print(ColorUtils.success(f"Queued task for {source_path} -> {target_path}"))

    if not copy_tasks:
        print(ColorUtils.error("No valid files to copy."))
    return copy_tasks


def is_file_hash_provided_to_frontend(filepath: str) -> bool:
    """Returns if the hash for the filepath should be provided to the frontend.

    Args:
        filepath: str. Relative path to the file.

    Returns:
        bool. True if file hash should be provided to the frontend else False.
    """
    return any(
        fnmatch.fnmatch(filepath, pattern) for pattern
        in FILEPATHS_PROVIDED_TO_FRONTEND)


def generate_md5_hash(filepath: str) -> str:
    """Returns md5 hash of file.

    Args:
        filepath: str. Absolute path to the file.

    Returns:
        str. Hexadecimal hash of specified file.
    """
    m = hashlib.md5()
    with utils.open_file(filepath, 'rb', encoding=None) as f:
        while True:
            buf = f.read(HASH_BLOCK_SIZE)
            if not buf:
                break
            m.update(buf)
    return m.hexdigest()


def get_filepaths_by_extensions(
    source_dir: str, file_extensions: Tuple[str, ...]
) -> List[str]:
    """Return list of filepaths in a directory with certain extensions,
    excluding filepaths that should not be built.

    Args:
        source_dir: str. Root directory to be walked.
        file_extensions: tuple(str). Tuple of file extensions.

    Returns:
        list(str). List of filepaths with specified extensions.
    """
    filepaths = []
    for root, _, filenames in os.walk(source_dir):
        for filename in filenames:
            filepath = os.path.join(root, filename)
            relative_filepath = os.path.relpath(filepath, start=source_dir)
            if should_file_be_built(filepath) and any(
                    filename.endswith(p) for p in file_extensions):
                filepaths.append(relative_filepath)
    return filepaths


def get_file_hashes(directory_path: str) -> Dict[str, str]:
    """Returns hashes of all files in directory tree, excluding files with
    extensions in FILE_EXTENSIONS_TO_IGNORE or files that should not be built.

    Args:
        directory_path: str. Root directory of the tree.

    Returns:
        dict(str, str). Dictionary with keys specifying file paths and values
        specifying file hashes.
    """
    file_hashes = {}

    print(ColorUtils.info(
        'Computing hashes for files in %s'
        % os.path.join(os.getcwd(), directory_path)))

    for root, _, filenames in os.walk(
            os.path.join(os.getcwd(), directory_path)):
        for filename in filenames:
            filepath = os.path.join(root, filename)
            if should_file_be_built(filepath) and not any(
                    filename.endswith(p) for p in FILE_EXTENSIONS_TO_IGNORE):
                complete_filepath = os.path.join(root, filename)
                relative_filepath = os.path.relpath(
                    complete_filepath, start=directory_path)
                file_hashes[relative_filepath] = generate_md5_hash(
                    complete_filepath)
                print(ColorUtils.success(
                    f"Hash computed for {relative_filepath}: {file_hashes[relative_filepath]}"))

    if not file_hashes:
        print(ColorUtils.error("No valid files to hash."))

    return file_hashes


def filter_hashes(file_hashes: Dict[str, str]) -> Dict[str, str]:
    """Filters hashes that should be provided to the frontend
    and prefixes "/" in front of the keys.

    Args:
        file_hashes: dict(str, str). Dictionary with filepaths as keys and
            hashes of file content as values.

    Returns:
        dict(str, str). Filtered dictionary of only filepaths that should be
        provided to the frontend.
    """
    filtered_hashes = {}
    for filepath, file_hash in file_hashes.items():
        if is_file_hash_provided_to_frontend(filepath):
            filtered_hashes['/' + filepath] = file_hash
    return filtered_hashes


def save_hashes_to_file(file_hashes: Dict[str, str]) -> None:
    """Return JS code that loads hashes needed for frontend into variable.

    Args:
        file_hashes: dict(str, str). Dictionary with filepaths as keys and
            hashes of file content as values.
    """
    # Only some of the hashes are needed in the frontend.
    filtered_hashes = filter_hashes(file_hashes)

    common.ensure_directory_exists(os.path.dirname(HASHES_JSON_FILEPATH))
    with utils.open_file(HASHES_JSON_FILEPATH, 'w+') as hashes_json_file:
        hashes_json_file.write(
            str(json.dumps(filtered_hashes, ensure_ascii=False)))
        hashes_json_file.write('\n')


def minify_func(source_path: str, target_path: str, filename: str) -> None:
    """Call the appropriate functions to handle different types of file
    formats:
        - HTML files: Remove whitespaces, interpolates paths in HTML to include
        hashes in source directory and save edited file at target directory.
        - CSS or JS files: Minify and save at target directory.
        - Other files: Copy the file from source directory to target directory.
    """
    skip_minify = any(
        filename.endswith(p) for p in JS_FILENAME_SUFFIXES_NOT_TO_MINIFY)
    if filename.endswith('.html'):
        print(ColorUtils.info(f'Building HTML file: {source_path}'))
        with utils.open_file(source_path, 'r+') as source_html_file:
            with utils.open_file(target_path, 'w+') as minified_html_file:
                process_html(source_html_file, minified_html_file)
    elif filename.endswith('.css') and not skip_minify:
        print(ColorUtils.info(f'Minifying CSS file: {source_path}'))
        _minify_css(source_path, target_path)
    else:
        print(ColorUtils.info(f'Copying file: {source_path}'))
        safe_copy_file(source_path, target_path)


def _execute_tasks(
    tasks: Deque[threading.Thread], batch_size: int = 24
) -> None:
    """Starts all tasks and checks the results.

    Runs no more than 'batch_size' tasks at a time.
    """
    remaining_tasks = collections.deque(tasks)
    currently_running_tasks: List[threading.Thread] = []

    while remaining_tasks or currently_running_tasks:
        if currently_running_tasks:
            for task in collections.deque(currently_running_tasks):
                if not task.is_alive():
                    currently_running_tasks.remove(task)
        while remaining_tasks and len(currently_running_tasks) < batch_size:
            task = remaining_tasks.popleft()
            currently_running_tasks.append(task)
            try:
                task.start()
            except RuntimeError as e:
                print(ColorUtils.error('Failed to start a thread.'))
                raise OSError(
                    'Threads can only be started once.') from e


def generate_build_tasks_to_build_all_files_in_directory(
    source: str, target: str
) -> Deque[threading.Thread]:
    """This function queues up tasks to build all files in a directory,
    excluding files that should not be built.

    Args:
        source: str. Path relative to /oppia of directory containing source
            files and directories to be built.
        target: str. Path relative to /oppia of directory where the built files
            and directories will be saved to.

    Returns:
        deque(Thread). A deque that contains all build tasks queued
        to be processed.
    """
    print(ColorUtils.info(f'Processing source directory: {os.path.join(os.getcwd(), source)}'))
    print(ColorUtils.info(f'Generating into target directory: {os.path.join(os.getcwd(), target)}'))
    build_tasks: Deque[threading.Thread] = collections.deque()

    for root, dirnames, filenames in os.walk(os.path.join(os.getcwd(), source)):
        for directory in dirnames:
            print(ColorUtils.success(f'Building directory: {os.path.join(root, directory)}'))
        for filename in filenames:
            source_path = os.path.join(root, filename)
            target_path = source_path.replace(source, target)
            common.ensure_directory_exists(os.path.dirname(target_path))
            if should_file_be_built(source_path):
                task = threading.Thread(
                    target=minify_func,
                    args=(source_path, target_path, filename,))
                build_tasks.append(task)
    return build_tasks


def generate_build_tasks_to_build_files_from_filepaths(
    source_path: str, target_path: str, filepaths: List[str]
) -> Deque[threading.Thread]:
    """This function queues up build tasks to build files from a list of
    filepaths, excluding files that should not be built.

    Args:
        source_path: str. Path relative to /oppia directory of directory
            containing files and directories to be copied.
        target_path: str. Path relative to /oppia directory of directory where
            to copy the files and directories.
        filepaths: list(str). List of filepaths to be built.

    Returns:
        deque(Thread). A deque that contains all build tasks queued
        to be processed.
    """
    build_tasks: collections.deque[threading.Thread] = collections.deque()
    for filepath in filepaths:
        source_file_path = os.path.join(source_path, filepath)
        target_file_path = os.path.join(target_path, filepath)
        common.ensure_directory_exists(os.path.dirname(target_file_path))
        if should_file_be_built(source_file_path):
            task = threading.Thread(
                target=minify_func,
                args=(
                    source_file_path, target_file_path, filepath,))
            build_tasks.append(task)
    return build_tasks


def generate_delete_tasks_to_remove_deleted_files(
    source_dir_hashes: Dict[str, str], staging_directory: str
) -> Deque[threading.Thread]:
    """This function walks the staging directory and queues up deletion tasks to
    remove files that are not in the hash dict i.e. remaining files in staging
    directory that have since been deleted from source directory. Files with
    extensions in FILE_EXTENSIONS_TO_IGNORE will be excluded.

    Args:
        source_dir_hashes: dict(str, str). Dictionary with filepaths as keys and
            hashes of file content as values.
        staging_directory: str. Path relative to /oppia directory of directory
            containing files and directories to be walked.

    Returns:
        deque(Thread). A deque that contains all delete tasks
        queued to be processed.
    """
    print(ColorUtils.info(f'Scanning directory {staging_directory} to remove deleted files'))
    delete_tasks: Deque[threading.Thread] = collections.deque()
    for root, _, filenames in os.walk(
            os.path.join(os.getcwd(), staging_directory)):
        for filename in filenames:
            target_path = os.path.join(root, filename)
            if not any(
                    target_path.endswith(p) for p in FILE_EXTENSIONS_TO_IGNORE):
                relative_path = os.path.relpath(
                    target_path, start=staging_directory)
                if relative_path not in source_dir_hashes:
                    print(ColorUtils.warning(
                        f'File not found in source hashes, deleting: {target_path}'))
                    task = threading.Thread(
                        target=safe_delete_file, args=(target_path,))
                    delete_tasks.append(task)
    return delete_tasks

def get_recently_changed_filenames(
    source_dir_hashes: Dict[str, str], out_dir: str
) -> List[str]:
    """Compare hashes of source files and built files. Return a list of
    filenames that were recently changed. Skips files that are not supposed to
    be built or already built."""
    recently_changed_filenames = []
    file_extensions_not_to_track = ('.html', '.py',)
    for filename, md5_hash in source_dir_hashes.items():
        if should_file_be_built(filename) and not any(
                filename.endswith(ext) for ext in file_extensions_not_to_track):
            final_filepath = _insert_hash(
                os.path.join(out_dir, filename), md5_hash)
            if not os.path.isfile(final_filepath):
                recently_changed_filenames.append(filename)

    if recently_changed_filenames:
        print(ColorUtils.warning(
            f"The following files will be rebuilt due to recent changes: {recently_changed_filenames}"))
    else:
        print(ColorUtils.success("No recently changed files detected."))
    return recently_changed_filenames


def generate_build_tasks_to_build_directory(
    dirnames_dict: Dict[str, str]
) -> Deque[threading.Thread]:
    """Queues up build tasks for all files in source directory or selectively
    queues up tasks for recently changed files."""
    source_dir = dirnames_dict['dev_dir']
    staging_dir = dirnames_dict['staging_dir']
    out_dir = dirnames_dict['out_dir']
    build_tasks: Deque[threading.Thread] = collections.deque()

    if not os.path.isdir(staging_dir):
        print(ColorUtils.info(f"Creating new staging directory: {staging_dir}"))
        common.ensure_directory_exists(staging_dir)
        build_tasks += generate_build_tasks_to_build_all_files_in_directory(
            source_dir, staging_dir)
    else:
        print(ColorUtils.info(
            f"Staging directory exists, rebuilding all .html and .py files in {source_dir}"))
        filenames_to_always_rebuild = get_filepaths_by_extensions(
            source_dir, ('.html', '.py',))
        build_tasks += generate_build_tasks_to_build_files_from_filepaths(
            source_dir, staging_dir, filenames_to_always_rebuild)

        dev_dir_hashes = get_file_hashes(source_dir)
        source_hashes = dev_dir_hashes.copy()
        _execute_tasks(generate_delete_tasks_to_remove_deleted_files(
            source_hashes, staging_dir))

        print(ColorUtils.info(
            f"Checking for changed files between {source_dir} and {out_dir}"))
        recently_changed_filenames = get_recently_changed_filenames(
            dev_dir_hashes, out_dir)
        if recently_changed_filenames:
            print(ColorUtils.warning(
                f"Rebuilding recently changed files in {source_dir}"))
            build_tasks += generate_build_tasks_to_build_files_from_filepaths(
                source_dir, staging_dir, recently_changed_filenames)
        else:
            print(ColorUtils.success("No changes detected. Using previously built files."))
    return build_tasks
    
def _verify_filepath_hash(
    relative_filepath: str, file_hashes: Dict[str, str]
) -> None:
    """Ensure that hashes in filepaths match with the hash entries in the hash dict.

    Args:
        relative_filepath: str. Filepath that is relative from /build.
        file_hashes: dict(str, str). Dictionary with filepaths as keys and
            hashes of file content as values.

    Raises:
        ValueError. The hash dict is empty.
        ValueError. Filepath has less than 2 partitions after splitting by '.'
            delimiter.
        ValueError. The filename does not contain hash.
        KeyError. The filename's hash cannot be found in the hash dict.
    """
    # Final filepath example:
    # pages/base.240933e7564bd72a4dde42ee23260c5f.html.
    if not file_hashes:
        raise ValueError(ColorUtils.error('Hash dictionary is empty.'))

    filename_partitions = relative_filepath.split('.')
    if len(filename_partitions) < 2:
        raise ValueError(
            ColorUtils.error(
                'Filepath "%s" has less than 2 partitions after splitting by "."'
                % relative_filepath
            )
        )

    hash_string_from_filename = filename_partitions[-2]
    # Ensure hash string obtained from filename follows MD5 hash format.
    if not re.search(r'([a-fA-F\d]{32})', relative_filepath):
        if relative_filepath not in file_hashes:
            return
        raise ValueError(
            ColorUtils.error(
                'Filename "%s" is expected to contain a valid MD5 hash.'
                % relative_filepath
            )
        )

    if hash_string_from_filename not in file_hashes.values():
        raise KeyError(
            ColorUtils.error(
                'Hash from file "%s" does not match any hash in the hash dictionary.'
                % relative_filepath
            )
        )

    print(ColorUtils.success('Filepath "%s" has a valid hash.' % relative_filepath))


def _verify_hashes(
    output_dirnames: List[str], file_hashes: Dict[str, str]
) -> None:
    """Verify a few metrics after build process finishes:
        1) The hashes in filenames belong to the hash dict.
        2) hashes.json, third_party.min.css, and third_party.min.js are built and
        hashes are inserted.

    Args:
        output_dirnames: list(str). List of directory paths that contain
            built files.
        file_hashes: dict(str, str). Dictionary with filepaths as keys and
            hashes of file content as values.
    """
    print(ColorUtils.info("Starting hash verification..."))

    # Ensure hashed file names match the current hash dict.
    for built_dir in output_dirnames:
        print(ColorUtils.info(f"Verifying files in directory: {built_dir}"))
        for root, _, filenames in os.walk(built_dir):
            for filename in filenames:
                parent_dir = os.path.basename(root)
                converted_filepath = os.path.join(
                    THIRD_PARTY_GENERATED_DEV_DIR, parent_dir, filename)
                if hash_should_be_inserted(converted_filepath):
                    # Obtain the same filepath format as the hash dict's key.
                    relative_filepath = os.path.relpath(
                        os.path.join(root, filename), start=built_dir)
                    print(ColorUtils.info(f"Verifying hash for: {relative_filepath}"))
                    try:
                        _verify_filepath_hash(relative_filepath, file_hashes)
                        print(ColorUtils.success(f"Hash verified for: {relative_filepath}"))
                    except KeyError as e:
                        print(ColorUtils.error(f"Hash verification failed for {relative_filepath}: {e}"))
                        raise

    print(ColorUtils.info("Verifying special hashed files..."))

    hash_final_filename = _insert_hash(
        HASHES_JSON_FILENAME, file_hashes[HASHES_JSON_FILENAME])
    third_party_js_final_filename = _insert_hash(
        MINIFIED_THIRD_PARTY_JS_RELATIVE_FILEPATH,
        file_hashes[MINIFIED_THIRD_PARTY_JS_RELATIVE_FILEPATH])
    third_party_css_final_filename = _insert_hash(
        MINIFIED_THIRD_PARTY_CSS_RELATIVE_FILEPATH,
        file_hashes[MINIFIED_THIRD_PARTY_CSS_RELATIVE_FILEPATH])

    try:
        _ensure_files_exist([
            os.path.join(ASSETS_OUT_DIR, hash_final_filename),
            os.path.join(
                THIRD_PARTY_GENERATED_OUT_DIR, third_party_js_final_filename),
            os.path.join(
                THIRD_PARTY_GENERATED_OUT_DIR, third_party_css_final_filename)])
        print(ColorUtils.success("All special hashed files verified successfully."))
    except FileNotFoundError as e:
        print(ColorUtils.error(f"File not found during verification: {e}"))
        raise

    print(ColorUtils.success("Hash verification completed successfully."))


def generate_hashes() -> Dict[str, str]:
    """Generates and returns hashes for files."""
    print(ColorUtils.info("Generating hashes for files."))
    hashes = {}
    hash_dirs = [
        ASSETS_DEV_DIR, EXTENSIONS_DIRNAMES_TO_DIRPATHS['dev_dir'],
        TEMPLATES_CORE_DIRNAMES_TO_DIRPATHS['dev_dir'],
        THIRD_PARTY_GENERATED_DEV_DIR
    ]
    for hash_dir in hash_dirs:
        hashes.update(get_file_hashes(hash_dir))

    save_hashes_to_file(hashes)
    hashes.update(
        {HASHES_JSON_FILENAME: generate_md5_hash(HASHES_JSON_FILEPATH)})
    _ensure_files_exist([HASHES_JSON_FILEPATH])
    print(ColorUtils.success("Hashes generated successfully."))
    return hashes


def generate_build_directory(hashes: Dict[str, str]) -> None:
    """Generates the production build directory."""
    print(ColorUtils.info("Building Oppia in production mode..."))

    build_tasks = collections.deque()
    copy_tasks = collections.deque()

    # Extensions and templates build tasks
    build_tasks += generate_build_tasks_to_build_directory(
        EXTENSIONS_DIRNAMES_TO_DIRPATHS)
    build_tasks += generate_build_tasks_to_build_directory(
        TEMPLATES_CORE_DIRNAMES_TO_DIRPATHS)
    _execute_tasks(build_tasks)

    # Copy tasks
    copy_input_dirs = [
        ASSETS_DEV_DIR, EXTENSIONS_DIRNAMES_TO_DIRPATHS['staging_dir'],
        TEMPLATES_CORE_DIRNAMES_TO_DIRPATHS['staging_dir'],
        THIRD_PARTY_GENERATED_DEV_DIR,
        WEBPACK_DIRNAMES_TO_DIRPATHS['staging_dir']]
    copy_output_dirs = [
        ASSETS_OUT_DIR, EXTENSIONS_DIRNAMES_TO_DIRPATHS['out_dir'],
        TEMPLATES_CORE_DIRNAMES_TO_DIRPATHS['out_dir'],
        THIRD_PARTY_GENERATED_OUT_DIR, WEBPACK_DIRNAMES_TO_DIRPATHS['out_dir']]
    for input_dir, output_dir in zip(copy_input_dirs, copy_output_dirs):
        safe_delete_directory_tree(output_dir)
        copy_tasks += generate_copy_tasks_to_copy_from_source_to_target(
            input_dir, output_dir, hashes)
    _execute_tasks(copy_tasks)

    _verify_hashes(copy_output_dirs, hashes)
    print(ColorUtils.success("Build completed successfully."))


def generate_python_package() -> None:
    """Generates Python package using setup.py."""
    try:
        print(ColorUtils.info('Removing dev dependencies...'))
        install_python_dev_dependencies.main(['--uninstall'])
        print(ColorUtils.info('Building Oppia package...'))
        subprocess.check_call('python setup.py -q sdist -d build', shell=True)
        print(ColorUtils.success('Oppia package build completed successfully.'))
    except subprocess.CalledProcessError as e:
        print(ColorUtils.error(f"Failed to build Oppia package: {e}"))
        raise
    finally:
        print(ColorUtils.info('Reinstalling dev dependencies...'))
        install_python_dev_dependencies.install_installation_tools()
        install_third_party_libs.main()
        print(ColorUtils.success('Dev dependencies reinstalled successfully.'))


def clean() -> None:
    """Cleans up existing build directories."""
    print(ColorUtils.info('Cleaning up existing build directories...'))
    safe_delete_directory_tree('build/')
    safe_delete_directory_tree('backend_prod_files/')
    safe_delete_directory_tree('webpack_bundles/')
    print(ColorUtils.success('Cleanup completed.'))


def main(args: Optional[Sequence[str]] = None) -> None:
    """The main method of this script."""
    options = _PARSER.parse_args(args=args)

    if options.maintenance_mode and not options.prod_env:
        print(ColorUtils.error(
            'Error: maintenance_mode should only be enabled in prod build.'))
        raise Exception(
            'maintenance_mode should only be enabled in prod build.')

    # Clean up the existing generated folders.
    clean()

    print(ColorUtils.info('Regenerating /third_party/generated from scratch...'))
    safe_delete_directory_tree(THIRD_PARTY_GENERATED_DEV_DIR)
    build_third_party_libs(THIRD_PARTY_GENERATED_DEV_DIR)

    if options.minify_third_party_libs_only:
        if options.prod_env:
            print(ColorUtils.info(
                'Minifying third-party libs only (prod environment)...'))
            minify_third_party_libs(THIRD_PARTY_GENERATED_DEV_DIR)
            print(ColorUtils.success('Third-party libs minified successfully.'))
            return
        else:
            print(ColorUtils.error(
                'Error: minify_third_party_libs_only should not be set in non-prod env.'))
            raise Exception(
                'minify_third_party_libs_only should not be '
                'set in non-prod env.')

    print(ColorUtils.info('Modifying constants for build configuration...'))
    common.modify_constants(
        prod_env=options.prod_env,
        emulator_mode=not options.deploy_mode,
        maintenance_mode=options.maintenance_mode)

    if options.prod_env:
        print(ColorUtils.info('Running production build steps...'))
        minify_third_party_libs(THIRD_PARTY_GENERATED_DEV_DIR)
        hashes = generate_hashes()
        if not feconf.OPPIA_IS_DOCKERIZED:
            print(ColorUtils.info('Generating Python package...'))
            generate_python_package()
            if options.source_maps:
                print(ColorUtils.info('Building using Webpack (with source maps)...'))
                build_using_webpack(WEBPACK_PROD_SOURCE_MAPS_CONFIG)
            else:
                print(ColorUtils.info('Building using Webpack...'))
                build_using_webpack(WEBPACK_PROD_CONFIG)
            print(ColorUtils.info('Building using Angular CLI...'))
            build_using_ng()
        print(ColorUtils.info('Generating app.yaml...'))
        generate_app_yaml(deploy_mode=options.deploy_mode)
        print(ColorUtils.info('Generating build directory...'))
        generate_build_directory(hashes)

    print(ColorUtils.info('Saving hashes to file...'))
    save_hashes_to_file({})
    print(ColorUtils.success('Build process completed successfully.'))


# The 'no coverage' pragma is used as this line is un-testable. This is because
# it will only be called when build.py is used as a script.
if __name__ == '__main__':  # pragma: no cover
    main()
