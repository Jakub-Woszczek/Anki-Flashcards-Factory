"""Read-only node connectivity probe, independent of scheduling and Anki status."""

import os
import time
from contextlib import closing

from external_apis.diki_remote import RemoteDownloads, RemoteError


def check_remote_node():
    url = os.getenv("DIKI_REMOTE_URL", "")
    token = os.getenv("DIKI_REMOTE_TOKEN", "")
    configured = bool(url and token)
    result = {
        "configured": configured,
        "healthy": False,
        "schedulingAvailable": False,
        "message": "Set DIKI_REMOTE_URL and DIKI_REMOTE_TOKEN to connect the node.",
        "checkedAt": time.time(),
    }
    if not configured:
        return result
    try:
        with closing(RemoteDownloads(url, token)) as client:
            status = client.status(timeout=(2, 3))
        if (
            not isinstance(status, dict)
            or type(status.get("protocol")) is not int
            or status["protocol"] not in {1, 2}
            or not isinstance(status.get("jobs"), dict)
        ):
            raise RemoteError("Node returned an unsupported status response")
        result.update(
            healthy=True,
            schedulingAvailable=status.get("schedulingVersion") == 1,
            message="Node API is online."
            if status.get("schedulingVersion") == 1
            else "Node API is online; update the worker to enable automatic scheduling.",
        )
    except RemoteError as error:
        result["message"] = str(error)
    result["checkedAt"] = time.time()
    return result
