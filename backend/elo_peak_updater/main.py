"""Cloud Function entry point for the daily peak updater."""

import functions_framework

from updater import handle_http_request


@functions_framework.http
def update_peaks(request):
    body, status, headers = handle_http_request(request)
    return body, status, headers
