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

"""Utility functions for managing server processes required by Oppia."""

from __future__ import annotations

import contextlib
import logging
import os
import re
import shutil
import signal
import subprocess
import threading
from scripts.utils.color_utils import ColorUtils
from core import feconf
from core import utils
from scripts import common

import psutil

from typing import (
    Any, Callable, ContextManager, Dict, Iterator, List, Optional, Sequence,
    Union
)


@contextlib.contextmanager
def managed_process(
    command_args: Sequence[Union[int, str]],
    human_readable_name: str = 'Process',
    shell: bool = False,
    timeout_secs: int = 60,
    raise_on_nonzero_exit: bool = True,
    **popen_kwargs: Any
) -> Iterator[psutil.Process]:
    """Context manager for starting and stopping a process gracefully.

    Args:
        command_args: list(int|str). A sequence of program arguments, where the
            program to execute is the first item. Ints are allowed in order to
            accomodate e.g. port numbers.
        human_readable_name: str. The human-readable name of the process. Used
            by the function's logging logic to improve readability.
        shell: bool. Whether the command should be run inside of its own shell.
        timeout_secs: int. The time allotted for the managed process and its
            descendants to terminate themselves. After the timeout, any
            remaining processes will be killed abruptly.
        raise_on_nonzero_exit: bool. If True, raise an Exception when the
            managed process has a nonzero exit code. If False, no Exception is
            raised, and it is the caller's responsibility to handle the error.
        **popen_kwargs: dict(str: *). Same kwargs as `subprocess.Popen`.

    Yields:
        psutil.Process. The process managed by the context manager.

    Raises:
        Exception. The process exited unexpectedly (only raised if
            raise_on_nonzero_exit is True).
    """
    get_proc_info: Callable[[psutil.Process], str] = lambda p: (
        '%s(name="%s", pid=%d)' % (human_readable_name, p.name(), p.pid)
        if p.is_running() else '%s(pid=%d)' % (human_readable_name, p.pid))

    stripped_args = (('%s' % arg).strip() for arg in command_args)
    non_empty_args = (s for s in stripped_args if s)

    command = ' '.join(non_empty_args) if shell else list(non_empty_args)
    human_readable_command = command if shell else ' '.join(command)
    msg = ColorUtils.info(f"Starting new {human_readable_name}: {human_readable_command}")
    print(msg)
    popen_proc = psutil.Popen(command, shell=shell, **popen_kwargs)

    try:
        yield popen_proc
    finally:
        proc_name = get_proc_info(popen_proc)
        print(ColorUtils.error(f"Stopping {proc_name}..."))
        procs_still_alive = [popen_proc]

        try:
            if popen_proc.is_running():
                # Children must be terminated before the parent, otherwise they
                # may become zombie processes.
                procs_still_alive = (
                    popen_proc.children(recursive=True) + [popen_proc])

            procs_to_kill = []
            for proc in procs_still_alive:
                if proc.is_running():
                    logging.info(ColorUtils.warning(f"Terminating {get_proc_info(proc)}..."))
                    proc.terminate()
                    procs_to_kill.append(proc)
                else:
                    logging.info(ColorUtils.success(f"{get_proc_info(proc)} has already ended."))

            procs_gone, procs_still_alive = (
                psutil.wait_procs(procs_to_kill, timeout=timeout_secs))
            for proc in procs_still_alive:
                logging.warning(ColorUtils.error(f"Forced to kill {get_proc_info(proc)}!"))
                proc.kill()
            for proc in procs_gone:
                logging.info(ColorUtils.success(f"{get_proc_info(proc)} has already ended."))
        except Exception:
            logging.exception(
                ColorUtils.error(f"Failed to stop {get_proc_info(popen_proc)} gracefully!"))

        exit_code = popen_proc.returncode
        if (
            exit_code is not None and exit_code > 0 and exit_code != 143
            and raise_on_nonzero_exit
        ):
            raise Exception(
                ColorUtils.error(
                    f"Process {proc_name} exited unexpectedly with exit code {exit_code}"))

@contextlib.contextmanager
def managed_dev_appserver(
    app_yaml_path: str,
    env: Optional[Dict[str, str]] = None,
    log_level: str = 'info',
    host: str = '0.0.0.0',
    port: int = 8080,
    admin_host: str = '0.0.0.0',
    admin_port: int = 8000,
    enable_host_checking: bool = True,
    automatic_restart: bool = False,
    skip_sdk_update_check: bool = False
) -> Iterator[psutil.Process]:
    """Returns a context manager to start up and shut down a GAE dev appserver.

    Args:
        app_yaml_path: str. Path to the app.yaml file which defines the
            structure of the server.
        env: dict(str: str) or None. Defines the environment variables for the
            new process.
        log_level: str. The lowest log level generated by the application code
            and the development server. Expected values are: debug, info,
            warning, error, critical.
        host: str. The host name to which the app server should bind.
        port: int. The lowest port to which application modules should bind.
        admin_host: str. The host name to which the admin server should bind.
        admin_port: int. The port to which the admin server should bind.
        enable_host_checking: bool. Whether to enforce HTTP Host checking for
            application modules, API server, and admin server. Host checking
            protects against DNS rebinding attacks, so only disable after
            understanding the security implications.
        automatic_restart: bool. Whether to restart instances automatically when
            files relevant to their module are changed.
        skip_sdk_update_check: bool. Whether to skip checking for SDK updates.
            If false, uses .appcfg_nag to decide.

    Yields:
        psutil.Process. The dev_appserver process.
    """
    dev_appserver_args: List[Union[str, int]] = [
        common.CURRENT_PYTHON_BIN,
        common.DEV_APPSERVER_PATH,
        '--host', host,
        '--port', port,
        '--admin_host', admin_host,
        '--admin_port', admin_port,
        '--enable_host_checking', 'true' if enable_host_checking else 'false',
        '--automatic_restart', 'true' if automatic_restart else 'false',
        '--skip_sdk_update_check', 'true' if skip_sdk_update_check else 'false',
        '--log_level', log_level,
        '--dev_appserver_log_level', log_level,
        app_yaml_path
    ]
    print(ColorUtils.info(f"Starting GAE Development Server on port {port}..."))
    with managed_process(
        dev_appserver_args,
        human_readable_name='GAE Development Server',
        shell=True,
        env=env,
    ) as proc:
        common.wait_for_port_to_be_in_use(port)
        yield proc
    print(ColorUtils.error("GAE Development Server stopped."))


@contextlib.contextmanager
def managed_firebase_auth_emulator(
    recover_users: bool = False
) -> Iterator[psutil.Process]:
    """Returns a context manager to manage the Firebase auth emulator.

    Args:
        recover_users: bool. Whether to recover users created by the previous
            instance of the Firebase auth emulator.

    Yields:
        psutil.Process. The Firebase emulator process.
    """
    emulator_args = [
        common.FIREBASE_PATH, 'emulators:start', '--only', 'auth',
        '--project', feconf.OPPIA_PROJECT_ID,
        '--config', feconf.FIREBASE_EMULATOR_CONFIG_PATH,
    ]

    emulator_args.extend(
        ['--import', common.FIREBASE_EMULATOR_CACHE_DIR, '--export-on-exit']
        if recover_users else
        ['--export-on-exit', common.FIREBASE_EMULATOR_CACHE_DIR])

    # OK to use shell=True here because we are passing string literals and
    # constants, so there is no risk of a shell-injection attack.
    print(ColorUtils.info("Starting Firebase Emulator..."))
    with managed_process(
        emulator_args, human_readable_name='Firebase Emulator', shell=True
    ) as proc:
        common.wait_for_port_to_be_in_use(feconf.FIREBASE_EMULATOR_PORT)
        yield proc
    print(ColorUtils.error("Firebase Emulator stopped."))



@contextlib.contextmanager
def managed_elasticsearch_dev_server() -> Iterator[psutil.Process]:
    """Returns a context manager for ElasticSearch server for running tests
    in development mode and running a local dev server. This is only required
    in a development environment.

    Yields:
        psutil.Process. The ElasticSearch server process.
    """
    # Clear previous data stored in the local cluster.
    if os.path.exists(common.ES_PATH_DATA_DIR):
        shutil.rmtree(common.ES_PATH_DATA_DIR)

    es_args = [
        '%s/bin/elasticsearch' % common.ES_PATH,
        # -q is the quiet flag.
        '-q'
    ]
    # Override the default path to ElasticSearch config files.
    es_env = {
        'ES_PATH_CONF': common.ES_PATH_CONFIG_DIR,
        # Set the minimum heap size to 100 MB and maximum to 500 MB.
        'ES_JAVA_OPTS': '-Xms100m -Xmx500m'
    }
    # OK to use shell=True here because we are passing string literals and
    # constants, so there is no risk of a shell-injection attack.
    print(ColorUtils.info("Starting ElasticSearch Server..."))
    with managed_process(
        es_args, human_readable_name='ElasticSearch Server', env=es_env,
        shell=True
    ) as proc:
        common.wait_for_port_to_be_in_use(feconf.ES_LOCALHOST_PORT)
        yield proc
    print(ColorUtils.error("ElasticSearch Server stopped."))

@contextlib.contextmanager
def managed_cloud_datastore_emulator(
    clear_datastore: bool = False
) -> Iterator[psutil.Process]:
    """Returns a context manager for the Cloud Datastore emulator.

    Args:
        clear_datastore: bool. Whether to delete the datastore's config and data
            before starting the emulator.

    Yields:
        psutil.Process. The emulator process.
    """
    emulator_hostport = '%s:%d' % (
        feconf.CLOUD_DATASTORE_EMULATOR_HOST,
        feconf.CLOUD_DATASTORE_EMULATOR_PORT)
    emulator_args = [
        common.GCLOUD_PATH, 'beta', 'emulators', 'datastore', 'start',
        '--project', feconf.OPPIA_PROJECT_ID,
        '--data-dir', common.CLOUD_DATASTORE_EMULATOR_DATA_DIR,
        '--host-port', emulator_hostport,
        '--consistency=1.0',
        '--quiet'
    ]

    if clear_datastore:
        emulator_args.append('--no-store-on-disk')

    with contextlib.ExitStack() as stack:
        data_dir_exists = os.path.exists(
            common.CLOUD_DATASTORE_EMULATOR_DATA_DIR)
        if clear_datastore and data_dir_exists:
            # Replace it with an empty directory.
            shutil.rmtree(common.CLOUD_DATASTORE_EMULATOR_DATA_DIR)
            os.makedirs(common.CLOUD_DATASTORE_EMULATOR_DATA_DIR)
        elif not data_dir_exists:
            os.makedirs(common.CLOUD_DATASTORE_EMULATOR_DATA_DIR)

        # OK to use shell=True here because we are passing string literals and
        # constants, so there is no risk of a shell-injection attack.
        proc = stack.enter_context(managed_process(
            emulator_args, human_readable_name='Cloud Datastore Emulator',
            shell=True))

        common.wait_for_port_to_be_in_use(feconf.CLOUD_DATASTORE_EMULATOR_PORT)
        print(ColorUtils.success("Cloud Datastore Emulator started."))

        # Environment variables required to communicate with the emulator.
        stack.enter_context(common.swap_env(
            'DATASTORE_DATASET', feconf.OPPIA_PROJECT_ID))
        stack.enter_context(common.swap_env(
            'DATASTORE_EMULATOR_HOST', emulator_hostport))
        stack.enter_context(common.swap_env(
            'DATASTORE_EMULATOR_HOST_PATH', '%s/datastore' % emulator_hostport))
        stack.enter_context(common.swap_env(
            'DATASTORE_HOST', 'http://%s' % emulator_hostport))
        stack.enter_context(common.swap_env(
            'DATASTORE_PROJECT_ID', feconf.OPPIA_PROJECT_ID))
        stack.enter_context(common.swap_env(
            'DATASTORE_USE_PROJECT_ID_AS_APP_ID', 'true'))
        stack.enter_context(common.swap_env(
            'GOOGLE_CLOUD_PROJECT', feconf.OPPIA_PROJECT_ID))

        yield proc

        print(ColorUtils.error("Stopping Cloud Datastore Emulator..."))
        
@contextlib.contextmanager
def managed_redis_server() -> Iterator[psutil.Process]:
    """Run the redis server within a context manager that ends it gracefully."""

    # Check if a redis dump file currently exists. This file contains residual
    # data from a previous run of the redis server. If it exists, remove it so
    # that the redis server starts with a clean slate.
    if os.path.exists(common.REDIS_DUMP_PATH):
        print(ColorUtils.warning("Redis dump file found. Removing it..."))
        os.remove(common.REDIS_DUMP_PATH)

    print(ColorUtils.info("Starting Redis Server..."))
    proc_context = managed_process(
        [common.REDIS_SERVER_PATH, common.REDIS_CONF_PATH],
        human_readable_name='Redis Server', shell=True)
    with proc_context as proc:
        common.wait_for_port_to_be_in_use(feconf.REDISPORT)
        print(ColorUtils.success("Redis Server started successfully."))
        try:
            yield proc
        finally:
            print(ColorUtils.error("Stopping Redis Server..."))
            subprocess.check_call([common.REDIS_CLI_PATH, 'shutdown', 'nosave'])


def create_managed_web_browser(
    port: int
) -> ContextManager[psutil.Process]:
    """Returns a ContextManager for a web browser targeting the given port on
    localhost. If a web browser cannot be opened on the current system by Oppia,
    then raises an exception.

    Args:
        port: int. The port number to open in the web browser.

    Returns:
        ContextManager. The ContextManager to a web browser window if the
        current operating system can be identified and a web browser can be
        launched automatically.

    Raises:
        Exception. Unable to launch the web browser (this happens when the
            Operating System cannot be identified).
    """
    url = 'http://localhost:%s/' % port
    human_readable_name = 'Web Browser'

    print(ColorUtils.info(f"Attempting to open web browser for {url}..."))
    if common.is_linux_os():
        return managed_process(
            ['xdg-open', url], human_readable_name=human_readable_name)
    elif common.is_mac_os():
        return managed_process(
            ['open', url], human_readable_name=human_readable_name)
    else:
        raise Exception(
            ColorUtils.error(
                "Unable to identify the Operating System and therefore, unable to launch the web browser."
            )
        )


@contextlib.contextmanager
def managed_ng_build(
    *, use_prod_env: bool = False, watch_mode: bool = False
) -> Iterator[psutil.Process]:
    """Returns context manager to start/stop the ng compiler gracefully.

    Args:
        use_prod_env: bool. Whether to compile for use in production.
        watch_mode: bool. Run the compiler in watch mode, which rebuilds on file
            change.

    Yields:
        psutil.Process. The ng compiler process.

    Raises:
        OSError. First build never completed.
    """
    compiler_args = [common.NG_BIN_PATH, 'build']
    if use_prod_env:
        compiler_args.append('--prod')
    if watch_mode:
        compiler_args.append('--watch')

    print(ColorUtils.info("Starting Angular Compiler..."))
    with contextlib.ExitStack() as exit_stack:
        proc = exit_stack.enter_context(managed_process(
            compiler_args,
            human_readable_name='Angular Compiler',
            shell=True,
            stdout=subprocess.PIPE
        ))

        read_line_func: Callable[[], Optional[bytes]] = (
            lambda: proc.stdout.readline() or None
        )
        if watch_mode:
            for line in iter(read_line_func, None):
                common.write_stdout_safe(line)
                if b'Build at: ' in line:
                    break
            else:
                raise IOError(ColorUtils.error("First Angular build never completed"))

        def print_proc_output() -> None:
            """Prints the proc's output until it is exhausted."""
            for line in iter(read_line_func, None):
                common.write_stdout_safe(line)

        printer_thread = threading.Thread(target=print_proc_output)
        printer_thread.start()
        exit_stack.callback(printer_thread.join)

        print(ColorUtils.success("Angular Compiler is running."))
        yield proc


@contextlib.contextmanager
def managed_webpack_compiler(
    config_path: Optional[str] = None,
    use_prod_env: bool = False,
    use_source_maps: bool = False,
    watch_mode: bool = False,
    max_old_space_size: Optional[int] = None
) -> Iterator[psutil.Process]:
    """Returns context manager to start/stop the webpack compiler gracefully.

    Args:
        config_path: str|None. Path to an explicit webpack config, or None to
            determine it from the other args.
        use_prod_env: bool. Whether to compile for use in production. Only
            respected if config_path is None.
        use_source_maps: bool. Whether to compile with source maps. Only
            respected if config_path is None.
        watch_mode: bool. Run the compiler in watch mode, which rebuilds on file
            change.
        max_old_space_size: int|None. Sets the max memory size of the compiler's
            "old memory" section. As memory consumption approaches the limit,
            the compiler will spend more time on garbage collection in an effort
            to free unused memory.

    Yields:
        psutil.Process. The Webpack compiler process.

    Raises:
        OSError. First build never completed.
    """
    if config_path is not None:
        pass
    elif use_prod_env:
        config_path = (
            common.WEBPACK_PROD_SOURCE_MAPS_CONFIG if use_source_maps else
            common.WEBPACK_PROD_CONFIG)
    else:
        config_path = (
            common.WEBPACK_DEV_SOURCE_MAPS_CONFIG if use_source_maps else
            common.WEBPACK_DEV_CONFIG)

    compiler_args = [
        common.NODE_BIN_PATH, common.WEBPACK_BIN_PATH, '--config', config_path,
    ]
    if max_old_space_size:
        compiler_args.insert(1, '--max-old-space-size=%d' % max_old_space_size)
    if watch_mode:
        compiler_args.extend(['--color', '--watch', '--progress'])

    print(ColorUtils.info("Starting Webpack Compiler..."))
    with contextlib.ExitStack() as exit_stack:
        proc = exit_stack.enter_context(managed_process(
            compiler_args,
            human_readable_name='Webpack Compiler',
            shell=True,
            stdout=subprocess.PIPE
        ))

        read_line_func: Callable[[], Optional[bytes]] = (
            lambda: proc.stdout.readline() or None
        )
        if watch_mode:
            for line in iter(read_line_func, None):
                common.write_stdout_safe(line)
                if b'Built at: ' in line:
                    break
            else:
                raise IOError(ColorUtils.error("First Webpack build never completed"))

        def print_proc_output() -> None:
            """Prints the proc's output until it is exhausted."""
            for line in iter(read_line_func, None):
                common.write_stdout_safe(line)

        printer_thread = threading.Thread(target=print_proc_output)
        printer_thread.start()
        exit_stack.callback(printer_thread.join)

        print(ColorUtils.success("Webpack Compiler is running."))
        yield proc


def get_chromedriver_version() -> str:
    """Returns the version of Chromedriver compatible with the installed version
    of Chrome.
    """
    # Although there are spaces between Google and Chrome in the path, we
    # don't need to escape them for Popen (as opposed to on the terminal, in
    # which case we would need to escape them for the command to run).
    chrome_command = (
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        if common.is_mac_os() else 'google-chrome')
    try:
        print(ColorUtils.info("Fetching Chrome version..."))
        output = subprocess.check_output([chrome_command, '--version'])
    except OSError as e:
        # For the error message on macOS, we need to add the backslashes in.
        # This is because it is likely that a user will try to run the
        # command on their terminal and, as mentioned above, the macOS
        # chrome version command has spaces in the path which need to be
        # escaped for successful terminal use.
        error_message = (
            'Failed to execute "%s --version" command. This is used to '
            'determine the chromedriver version to use. Please set the '
            'chromedriver version manually using the '
            '--chrome_driver_version flag. To determine the '
            'chromedriver version to be used, please follow the '
            'instructions mentioned in the following URL:\n'
            'https://chromedriver.chromium.org/downloads/version-selection'
            % chrome_command.replace(' ', r'\ '))
        print(ColorUtils.error(error_message))
        raise Exception(error_message) from e

    installed_version_bytes = b''.join(re.findall(rb'[0-9.]', output))
    installed_version_parts = installed_version_bytes.decode('utf-8').split('.')
        # For Chrome versions 115 and above, compatible Chromedriver and Chrome
    # versions have the same version numbers. For earlier versions, we use a
    # Google API to find the compatible Chromedriver version. See
    # https://chromedriver.chromium.org/downloads/version-selection for details.
    
    if int(installed_version_parts[0]) >= 115:
        chromedriver_version: str = '.'.join(installed_version_parts)
    else:
        print(ColorUtils.info("Fetching compatible Chromedriver version..."))
        response = utils.url_open(
            'https://chromedriver.storage.googleapis.com/LATEST_RELEASE_%s' % (
                '.'.join(installed_version_parts[:-1])
            )
        )
        chromedriver_version = response.read().decode('utf-8')

    print(ColorUtils.success(f"Chromedriver version: {chromedriver_version}"))
    return chromedriver_version


@contextlib.contextmanager
def managed_portserver() -> Iterator[psutil.Process]:
    """Returns context manager to start/stop the portserver gracefully.

    The portserver listens at PORTSERVER_SOCKET_FILEPATH and allocates free
    ports to clients. This prevents race conditions when two clients request
    ports in quick succession. The local Google App Engine server that we use to
    serve the development version of Oppia uses python_portpicker, which is
    compatible with the portserver this function starts, to request ports.

    By "compatible" we mean that python_portpicker requests a port by sending a
    request consisting of the PID of the requesting process and expects a
    response consisting of the allocated port number. This is the interface
    provided by this portserver.

    Yields:
        psutil.Popen. The Popen subprocess object.
    """
    # Check if a socket file exists. This file can exist when previous instance
    # of the portserver did not close properly. We need to remove as otherwise
    # the portserver will fail to start.
    if os.path.exists(common.PORTSERVER_SOCKET_FILEPATH):
        print((
            "Portserver socket file exists. Removing stale file..."))
        os.remove(common.PORTSERVER_SOCKET_FILEPATH)

    portserver_args = [
        'python', '-m', 'scripts.run_portserver',
        '--portserver_unix_socket_address', common.PORTSERVER_SOCKET_FILEPATH,
    ]
    print(ColorUtils.info("Starting Portserver..."))
    # OK to use shell=True here because we are passing string literals and
    # constants, so there is no risk of a shell-injection attack.
    proc_context = managed_process(
        portserver_args, human_readable_name='Portserver', shell=True)

    with proc_context as proc:
        try:
            print(ColorUtils.success("Portserver started successfully."))
            yield proc
        finally:
            print(ColorUtils.error("Stopping Portserver..."))
            try:
                proc.send_signal(signal.SIGINT)
                proc.wait(timeout=10)
            except OSError:
                print(ColorUtils.error("Portserver already shut down."))
            except psutil.TimeoutExpired:
                print(ColorUtils.error("Portserver failed to shut down after 10 seconds."))



@contextlib.contextmanager
def managed_webdriverio_server(
    suite_name: str = 'full',
    dev_mode: bool = True,
    debug_mode: bool = False,
    sharding_instances: int = 1,
    chrome_version: Optional[str] = None,
    mobile: bool = False,
    stdout: int = subprocess.PIPE
) -> Iterator[psutil.Process]:
    """Returns context manager to start/stop the WebdriverIO server gracefully.

    Args:
        suite_name: str. The suite name whose tests should be run. If the value
            is `full`, all tests will run.
        dev_mode: bool. Whether the test is running on dev_mode.
        debug_mode: bool. Whether to run the webdriverio tests in debugging
            mode. Read the following instructions to learn how to run e2e
            tests in debugging mode:
            https://webdriver.io/docs/debugging/#the-debug-command.
        sharding_instances: int. How many sharding instances to be running.
        chrome_version: str|None. The version of Google Chrome to run the tests
            on. If None, then the currently-installed version of Google Chrome
            is used instead.
        stdout: int. This parameter specifies the executed program's standard
            output file handle.
        mobile: bool. Whether to run the webdriverio tests in mobile mode.

    Yields:
        psutil.Process. The webdriverio process.

    Raises:
        ValueError. Number of sharding instances are less than 0.
    """
    if sharding_instances <= 0:
        raise ValueError(ColorUtils.error('Sharding instance should be larger than 0'))


    if chrome_version is None:
        chrome_version = get_chromedriver_version()

    if mobile:
        os.environ['MOBILE'] = 'true'
    else:
        os.environ['MOBILE'] = 'false'

    webdriverio_args = [
        common.NPX_BIN_PATH,
        # This flag ensures tests fail if the `waitFor()` calls time out.
        '--unhandled-rejections=strict',
        common.NODEMODULES_WDIO_BIN_PATH, common.WEBDRIVERIO_CONFIG_FILE_PATH,
        '--suite', suite_name, chrome_version,
        '--params.devMode=%s' % dev_mode,
    ]

    # Capabilities in wdio.conf.js are added as an array of object,
    # so in order to set the value of maxmium instances of chrome
    # in wdio.conf.js, we need to provide the index of the capability
    # at which chrome is present, i.e. 0.
    if sharding_instances > 1:
        webdriverio_args.extend([
           '--capabilities[0].maxInstances=%d' % sharding_instances,
       ])

    if debug_mode:
        webdriverio_args.insert(0, 'DEBUG=true')
        
    print(ColorUtils.info("Starting WebdriverIO Server..."))

    # OK to use shell=True here because we are passing string literals and
    # constants, so there is no risk of a shell-injection attack.
    managed_webdriverio_proc = managed_process(
        webdriverio_args, human_readable_name='WebdriverIO Server', shell=True,
        raise_on_nonzero_exit=False, stdout=stdout)

    try:
        with managed_webdriverio_proc as proc:
            print(ColorUtils.success("WebdriverIO Server started successfully."))
            yield proc
    finally:
        print(ColorUtils.error("Stopping WebdriverIO Server..."))
        del os.environ['MOBILE']

@contextlib.contextmanager
def managed_acceptance_tests_server(
    suite_name: str,
    headless: bool = False,
    mobile: bool = False,
    prod_env: bool = False,
    stdout: int = subprocess.PIPE,
) -> Iterator[psutil.Process]:
    """Returns context manager to start/stop the acceptance tests
    server gracefully. If the suite_name is not in the list of the
    acceptance tests suite names, then raises an exception.

    Args:
        suite_name: str. The suite name whose tests should be run.
        headless: bool. Whether to run the acceptance tests in headless mode.
        mobile: bool. Whether to run the acceptance tests in mobile mode.
        prod_env: bool. Whether to run the acceptance tests in production mode.
        stdout: int. The file descriptor where the standard output of the 
            subprocess is sent.

    Yields:
        psutil.Process. The jest testing process.

    Raises:
        Exception. The suite_name is not in the list of the acceptance tests
            suite names.
    """
    if suite_name not in common.ACCEPTANCE_TESTS_SUITE_NAMES:
        raise Exception(ColorUtils.error(f'Invalid suite name: {suite_name}'))

    os.environ['HEADLESS'] = 'true' if headless else 'false'
    os.environ['MOBILE'] = 'true' if mobile else 'false'
    os.environ['SPEC_NAME'] = suite_name
    os.environ['PROD_ENV'] = 'true' if prod_env else 'false'

    nodemodules_jest_bin_path = os.path.join(
        common.NODE_MODULES_PATH, '.bin', 'jest')
    puppeteer_acceptance_tests_dir_path = os.path.join(
        common.CURR_DIR, 'core', 'tests', 'puppeteer-acceptance-tests', 'specs')

    acceptance_tests_args = [
        nodemodules_jest_bin_path,
        '%s' % os.path.join(puppeteer_acceptance_tests_dir_path, suite_name),
        '--config=./core/tests/puppeteer-acceptance-tests/jest.config.js'
    ]

    print(ColorUtils.info(f"Starting acceptance tests for suite: {suite_name}..."))
    managed_acceptance_tests_proc = managed_process(
        acceptance_tests_args,
        human_readable_name='Acceptance Tests Server',
        shell=True,
        raise_on_nonzero_exit=False,
        stdout=stdout,
    )

    with managed_acceptance_tests_proc as proc:
        print(ColorUtils.success(f"Acceptance tests for suite '{suite_name}' started successfully."))
        yield proc
