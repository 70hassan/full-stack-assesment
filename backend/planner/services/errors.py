class PlannerError(Exception):
    """Base class for errors that map to an HTTP error response."""

    status_code = 400

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class InvalidRequest(PlannerError):
    status_code = 400


class NoRouteFound(PlannerError):
    status_code = 422


class UpstreamError(PlannerError):
    """A third-party API failed, timed out or rate-limited us."""

    status_code = 502
