import time
from utils.api_client import APIClient
from utils.data_loader import load_payload
from utils.request_info import get_request_info
from utils.config import search_params

def search_entity(entity_type, token, client, entity_id, payload_file, endpoint, response_key):
    payload = load_payload(entity_type, payload_file)

    # Dynamically pick the top-level key in payload (e.g. "Product", "ProductVariant")
    top_key = next(iter(payload))

    # Handle different payload structures (dict vs list)
    if isinstance(payload[top_key], list):
        # For payloads like Projects: [{id: ..., tenantId: ...}]
        payload[top_key][0]["id"] = entity_id
    else:
        # For payloads like Product: {id: [...]}
        payload[top_key]["id"] = [entity_id]

    payload["RequestInfo"] = get_request_info(token)

    query_string = "&".join(f"{k}={v}" for k, v in search_params.items())
    url = f"{endpoint}?{query_string}"

    res = client.post(url, payload)
    assert res.status_code == 200, f"Search failed: {res.text}"

    response_data = res.json()
    return response_data.get(response_key, [])



def poll_until_found(search_fn, retries=5, delay=3):
    """Call search_fn() repeatedly until it returns a non-empty list or retries are exhausted."""
    for attempt in range(retries):
        result = search_fn()
        if result:
            return result
        time.sleep(delay)
    return []


def poll_until_match(search_fn, condition_fn, retries=5, delay=3):
    """Call search_fn() repeatedly until condition_fn(results) returns True or retries are exhausted.
    Returns the last result regardless — caller should assert the condition."""
    result = []
    for attempt in range(retries):
        result = search_fn()
        if result and condition_fn(result):
            return result
        time.sleep(delay)
    return result


def extract_id_from_file(label):
    with open("output/ids.txt", "r") as f:
        lines = f.readlines()
    return next((line.split(":", 1)[1].strip() for line in lines if line.startswith(label)), None)


def extract_boundary_levels_from_file():
    """Read all 'Boundary TYPE: code' entries from ids.txt in order.
    Returns a list of (boundaryType, code) tuples."""
    try:
        with open("output/ids.txt", "r") as f:
            lines = f.readlines()
        levels = []
        for line in lines:
            if line.startswith("Boundary ") and ":" in line:
                rest = line[len("Boundary "):]
                btype, code = rest.split(":", 1)
                levels.append((btype.strip(), code.strip()))
        return levels
    except FileNotFoundError:
        return []
