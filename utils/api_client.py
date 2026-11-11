from utils.auth import get_auth_token
from utils.config import BASE_URL
import requests
import time
import os

# eventual-consistency slack: persisters return 202 then write async to DB.
# downstream tests immediately reference the just-created entity, so we pause
# briefly when a response indicates async acceptance.
_ASYNC_DELAY_S = float(os.getenv("ASYNC_PERSISTER_DELAY", "6.0"))


def _maybe_wait_for_persist(resp):
    if resp.status_code == 202:
        time.sleep(_ASYNC_DELAY_S)
    return resp


class APIClient:
    _last_instance = None

    def __init__(self, service=None, token=None):
        if not token and service:
            token = get_auth_token(service)
        elif not token:
            raise ValueError("Either 'service' or 'token' must be provided")

        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        # Track the last request/response for failed test logging
        self.last_request = None
        APIClient._last_instance = self

    def _track(self, method, url, payload, response):
        """Store request and response details for failure debugging."""
        self.last_request = {
            "method": method,
            "url": url,
            "request_payload": payload,
            "response_status": response.status_code,
            "response_body": response.text
        }
        return response

    def get(self, endpoint):
        url = BASE_URL + endpoint
        response = requests.get(url, headers=self.headers)
        return self._track("GET", url, None, response)

    def post(self, endpoint, data):
        url = BASE_URL + endpoint
        response = requests.post(url, headers=self.headers, json=data)
        return self._track("POST", url, data, response)

    def put(self, endpoint, data):
        url = BASE_URL + endpoint
        response = requests.put(url, headers=self.headers, json=data)
        return self._track("PUT", url, data, response)

    def delete(self, endpoint):
        url = BASE_URL + endpoint
        response = requests.delete(url, headers=self.headers)
        return self._track("DELETE", url, None, response)

    def upload_file(self, endpoint, file_path, form_fields=None):
        """Multipart upload, as used by the filestore service.

        The JSON Content-Type header is deliberately dropped: requests must set
        multipart/form-data itself so it can generate the boundary. Passing the
        class-level headers here yields a 400 from the filestore.

        Returns the raw response; the filestore answers with
        ``{"files": [{"fileStoreId": ..., "tenantId": ...}]}``.
        """
        url = BASE_URL + endpoint
        headers = {"Authorization": self.headers["Authorization"]}

        filename = os.path.basename(file_path)
        content_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if filename.lower().endswith((".xlsx", ".xlsm"))
            else "application/octet-stream"
        )

        with open(file_path, "rb") as handle:
            files = {"file": (filename, handle, content_type)}
            response = requests.post(
                url, headers=headers, files=files, data=form_fields or {}
            )

        return self._track("POST", url, {"file": filename, **(form_fields or {})}, response)
