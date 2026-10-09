"""Short-lived, signed proof of the payload and revision actually previewed."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

import projects

SECRET = os.environ.get("TIMBERBIM_PREVIEW_SECRET", "").encode() or secrets.token_bytes(32)


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def issue(payload, revision):
    data = json.dumps({"project": projects.project_id.get(), "revision": revision,
                       "hash": digest(payload), "expires": time.time() + 1800}, sort_keys=True).encode()
    return base64.urlsafe_b64encode(data).decode() + "." + hmac.new(SECRET, data, hashlib.sha256).hexdigest()


def verify(token, payload):
    try:
        encoded, signature = token.split(".")
        data = base64.urlsafe_b64decode(encoded)
        if not hmac.compare_digest(signature, hmac.new(SECRET, data, hashlib.sha256).hexdigest()):
            raise ValueError()
        proof = json.loads(data)
        if proof["project"] != projects.project_id.get() or proof["expires"] < time.time() or proof["hash"] != digest(payload):
            raise ValueError()
        return proof["revision"]
    except (ValueError, KeyError, TypeError):
        raise projects.ProjectConflict("Preview is missing, expired, or does not match this draft/project. Preview again.") from None
