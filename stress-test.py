import asyncio
import os
from nicegui import ui
import requests
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import splunklib.client as client
import splunklib.results as results

load_dotenv()

# Splunk connection settings
SPLUNK_HOST = os.getenv("SPLUNK_HOST", "your_splunk_host")
SPLUNK_PORT = int(os.getenv("SPLUNK_PORT", "8089"))
SPLUNK_TOKEN = os.getenv("SPLUNK_TOKEN")
SPLUNK_APP = os.getenv("SPLUNK_APP", "search")

# Shared state
success_count = 0
failure_count = 0
is_running = False
url_options = []  # This will store our dynamic URLs


async def fetch_splunk_paths():
    """Fetch paths from Splunk using token authentication"""
    try:
        # Connect to Splunk using token
        service = client.connect(
            host=SPLUNK_HOST,
            port=SPLUNK_PORT,
            token=SPLUNK_TOKEN,
            app=SPLUNK_APP
        )

        # Run the search query
        query = 'index="otel_logging" earliest=-1d | dedup path | table path | sort path'
        kwargs = {"exec_mode": "normal"}
        search_results = service.jobs.oneshot(query, **kwargs)

        # Parse results
        reader = results.ResultsReader(search_results)
        paths = [str(result['path']) for result in reader if isinstance(result, dict)]

        # Create full URLs (modify this logic as needed)
        base_url = "http://home.dev.com"
        urls = [f"{base_url}{path}" for path in paths]

        return urls
    except Exception as e:
        print(f'SPLUNK_HOST: {SPLUNK_HOST}')
        print(f'SPLUNK_PORT: {SPLUNK_PORT}')
        print(f'SPLUNK_TOKEN: {SPLUNK_TOKEN}')
        print(f'SPLUNK_APP: {SPLUNK_APP}')
        print(f"Error fetching paths from Splunk: {e}")
        return []


async def initialize_url_options():
    """Initialize the URL options from Splunk when the app starts"""
    global url_options
    url_options = await fetch_splunk_paths()
    if not url_options:
        # Fallback to default options if Splunk query fails
        url_options = [
            "http://home.dev.com/api/flask-test/v1/info",
            "http://home.dev.com/api/fastapi-test/v1/info",
            "http://home.dev.com/api/fastapi-test-revert/v1/info",
            "http://home.dev.com/api/robert/v1/info",
            "http://home.dev.com/api/flask-test/v1/sample",
            "http://home.dev.com/api/fastapi-test/v1/sample",
            "http://home.dev.com/api/fastapi-test-revert/v1/sample",
            "http://home.dev.com/api/robert/v1/sample"
        ]
    url_input.set_options(url_options)
    if url_options:
        url_input.value = url_options[0]  # Set default value


# --- UI Setup ---
with ui.column().classes('items-start ml-[50px]'):
    with ui.card().classes('p-6 w-[800px]'):
        ui.label('API Load Test Configuration').classes('text-lg font-bold mb-4')

        url_input = ui.select(
            options=[],
            label="Select API Endpoint",
            value=None,
            with_input=True
        ).classes('mb-4 w-full')

        request_input = ui.input('Number of Requests', value='1000').props('type=number').classes('mb-4 w-full')
        thread_input = ui.input('Number of Threads', value='10').props('type=number').classes('mb-6 w-full')

# --- Status Display ---
with ui.column().classes('items-start ml-[50px] mt-6'):
    with ui.card().classes('p-6 w-[800px]'):
        ui.label('Test Results').classes('text-lg font-bold mb-4')

        success_label = ui.label('Total Success: 0').classes('mb-2')
        failure_label = ui.label('Total Failures: 0').classes('mb-2')
        status_label = ui.label('Status: IDLE').classes('text-lg font-bold text-gray-600 mb-6')

# --- Buttons ---
start_button = ui.button('Start Test', on_click=lambda: run_test()).classes('ml-[50px] mt-4')
refresh_button = ui.button('Refresh Endpoints', on_click=lambda: initialize_url_options()).classes('ml-[50px] mt-4')


# --- Test Logic ---
def call_endpoint(url: str):
    global success_count, failure_count
    try:
        response = requests.get(url, timeout=5)
        if 200 <= response.status_code < 400:
            success_count += 1
        else:
            failure_count += 1
    except Exception:
        failure_count += 1


def background_test(url: str, total_requests: int, num_threads: int):
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(call_endpoint, url) for _ in range(total_requests)]
        for future in as_completed(futures):
            future.result()


async def run_test():
    global success_count, failure_count, is_running

    # Validate input
    if not url_input.value:
        ui.notify("Please select an API endpoint", type='negative')
        return

    # Reset state for new run
    success_count = 0
    failure_count = 0
    is_running = True

    # Update UI
    success_label.text = 'Total Success: 0'
    failure_label.text = 'Total Failures: 0'
    status_label.text = 'Status: RUNNING'
    status_label.classes(replace='text-lg font-bold text-orange-600 mb-6')
    start_button.disable()
    refresh_button.disable()

    url = url_input.value
    total = int(request_input.value)
    threads = int(thread_input.value)

    async def update_ui_periodically(stop_event_internal):
        while not stop_event_internal.is_set():
            success_label.text = f'Total Success: {success_count}'
            failure_label.text = f'Total Failures: {failure_count}'
            await asyncio.sleep(0.1)

    stop_event = asyncio.Event()
    update_task = asyncio.create_task(update_ui_periodically(stop_event))

    try:
        await asyncio.to_thread(background_test, url, total, threads)
    except Exception as e:
        ui.notify(f"Test failed: {str(e)}", type='negative')
    finally:
        stop_event.set()
        await update_task

        # Final update
        success_label.text = f'Total Success: {success_count}'
        failure_label.text = f'Total Failures: {failure_count}'
        status_label.text = 'Status: COMPLETE'
        status_label.classes(replace='text-lg font-bold text-green-600 mb-6')
        is_running = False
        start_button.enable()
        refresh_button.enable()


# Initialize the URL options when the app starts
ui.timer(0.1, initialize_url_options, once=True)

# Run the app with your custom configuration
ui.run(
    title="API Load Tester",
    port=8080,
    reload=False,
    dark=None,  # Auto dark mode
    storage_secret="your_secret_key_here",  # For session storage
    show=True  # Open browser automatically
)