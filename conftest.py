import pytest
import json
import os
import re
from datetime import datetime
from utils.data_loader import clear_ids_file
from utils.dashboard_generator import generate_dashboard
from utils.auth import clear_token_cache


FAILED_REQUESTS_DIR = os.path.join(os.path.dirname(__file__), "output", "failed_requests")


def _is_master(config):
    return not hasattr(config, "workerinput")


def pytest_sessionstart(session):
    """Runs on master (and non-xdist) before workers are spawned — guaranteed clear."""
    if _is_master(session.config):
        clear_ids_file()
        clear_token_cache()
        if os.path.exists(FAILED_REQUESTS_DIR):
            for f in os.listdir(FAILED_REQUESTS_DIR):
                os.remove(os.path.join(FAILED_REQUESTS_DIR, f))
        os.makedirs(FAILED_REQUESTS_DIR, exist_ok=True)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Runs on the master after all tests complete. Builds test_results and dashboard."""
    if not _is_master(config):
        return

    stats = terminalreporter.stats
    passed  = [r for r in stats.get("passed",  []) if r.when == "call"]
    failed  = [r for r in stats.get("failed",  []) if r.when == "call"]
    skipped = [r for r in stats.get("skipped", []) if r.when == "call"]
    errors  = [r for r in stats.get("error",   []) if r.when in ("call", "setup")]

    tests = []
    for report in passed + failed + skipped + errors:
        info = {
            "name": report.nodeid,
            "outcome": report.outcome,
            "duration": round(report.duration, 2),
        }
        if report.outcome == "failed" and hasattr(report, "longrepr"):
            info["error"] = str(report.longrepr)
        if hasattr(report, "capstdout") and report.capstdout:
            info["stdout"] = report.capstdout
        tests.append(info)

    end_dt = datetime.now()
    if hasattr(terminalreporter, "_sessionstarttime"):
        start_dt = datetime.fromtimestamp(terminalreporter._sessionstarttime)
    else:
        start_dt = end_dt

    test_results = {
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "duration": round((end_dt - start_dt).total_seconds(), 2),
        "total":   len(passed) + len(failed) + len(skipped) + len(errors),
        "passed":  len(passed),
        "failed":  len(failed) + len(errors),
        "skipped": len(skipped),
        "tests":   tests,
    }

    try:
        output_dir = os.path.join(os.path.dirname(__file__), "output")
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "test_results.json"), "w", encoding="utf-8") as f:
            json.dump(test_results, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save test results: {e}")

    print("\n" + "=" * 60)
    print("Generating interactive dashboard...")
    print("=" * 60)
    try:
        dashboard_path = generate_dashboard()
        print(f"\n Dashboard URL: file://{dashboard_path}")
    except Exception as e:
        print(f"Warning: Could not generate dashboard: {e}")

def pytest_runtest_logreport(report):
    """Persist the request/response of any failed test for debugging.

    Result totals are built in pytest_terminal_summary from the reporter's own
    stats, so nothing is accumulated here.
    """
    if report.when != "call" or report.outcome != "failed":
        return

    error = str(report.longrepr) if hasattr(report, "longrepr") else "Unknown error"
    if hasattr(report, "_failed_request_data"):
        _save_failed_request(report.nodeid, report._failed_request_data, error)


def _save_failed_request(nodeid, request_data, error_message):
    """Save the request and response details for a failed test to output/failed_requests/"""
    try:
        # Create a safe filename from the test nodeid  e.g. test_household_service__test_update_household_member
        safe_name = re.sub(r'[^\w]', '_', nodeid.replace("tests/", "").replace(".py::", "__"))
        filepath = os.path.join(FAILED_REQUESTS_DIR, f"{safe_name}.json")

        failed_data = {
            "test": nodeid,
            "timestamp": datetime.now().isoformat(),
            "request": {
                "method": request_data.get("method"),
                "url": request_data.get("url"),
                "payload": request_data.get("request_payload")
            },
            "response": {
                "status_code": request_data.get("response_status"),
                "body": request_data.get("response_body")
            },
            "error": error_message
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(failed_data, f, indent=2, default=str)

        print(f"\nFailed request saved to: {filepath}")
    except Exception as e:
        print(f"Warning: Could not save failed request: {e}")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Hook to capture stdout/stderr and failed request data for each test"""
    outcome = yield
    report = outcome.get_result()

    if call.when == "call":
        # Capture stdout
        if hasattr(item, '_captured_stdout'):
            report.capstdout = item._captured_stdout
        # Capture stderr
        if hasattr(item, '_captured_stderr'):
            report.capstderr = item._captured_stderr

        # On failure, read APIClient._last_instance directly (fixture teardown hasn't run yet)
        if report.failed:
            from utils.api_client import APIClient
            if APIClient._last_instance and APIClient._last_instance.last_request:
                report._failed_request_data = APIClient._last_instance.last_request


@pytest.fixture(autouse=True)
def capture_test_output(request, capfd):
    """Fixture to capture test output"""
    yield
    captured = capfd.readouterr()
    request.node._captured_stdout = captured.out
    request.node._captured_stderr = captured.err
