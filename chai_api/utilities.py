# pylint: disable=line-too-long, missing-module-docstring, c-extension-no-member

from dataclasses import dataclass
from typing import Optional, Dict, Callable, Union, TypeVar

import falcon
from falcon import Request, Response

V = TypeVar("V")
K = TypeVar("K")
T = TypeVar("T")


@dataclass
class Configuration:
    """ Configuration used by this application. """
    # whenever an Optional value is None it means that this should value should be ignored a.k.a. open access
    host: str
    port: int
    secret: str


def optional(source: Optional[Dict[K, V]], key: K, default: V = None,
             mapping: Optional[Callable[[V], T]] = None) -> Optional[Union[V, T]]:
    """
    Safely access a resource assuming the resource either exists or is None.
    :param source: A dictionary of values, which is possibly empty or None.
    :param key: The desired key to access in the dictionary.
    :param default: The default value to return when the value associated with `key` cannot be found.
    :param mapping: An optional mapping to apply to the value or default before returning it.
    :return: The value in the dictionary if the key exists, otherwise the default value if one is provided.
             If a mapping is provided the value in the dictionary or the default if it is exists is mapped.
             Returns None in all other cases.
    """
    if source is None:
        return default if mapping is None or default is None else mapping(default)
    try:
        element = source[key]
        return element if mapping is None else mapping(element)
    except (KeyError, IndexError):
        return default if mapping is None or default is None else mapping(default)


def _get_header_token(header: Optional[str]) -> Optional[str]:
    prefix = "Bearer "
    if header is None:
        return None
    if not header.startswith(prefix):
        return None
    return header[len(prefix):]


def _validate_bearer(header: Optional[str], valid_bearer: str) -> bool:
    token = _get_header_token(header)
    if token is None:
        return False

    return token == valid_bearer


def bearer_authentication(token: str):
    def decorator(function):
        def verify(self, request: Request, response: Response):
            header = request.get_header("Authorization")
            if header is None:
                response.status = falcon.HTTP_UNAUTHORIZED
                response.content_type = falcon.MEDIA_TEXT
                response.text = "An authorization bearer is required."
                return

            if not _validate_bearer(header, token):
                response.status = falcon.HTTP_UNAUTHORIZED
                response.content_type = falcon.MEDIA_TEXT
                response.text = "The bearer token is not valid."
                return

            function(self, request, response)
        return verify
    return decorator


if __name__ == "__main__":
    pass
