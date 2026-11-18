class BusinessError(Exception):
    """An actionable error safe to display verbatim."""


class DuplicateRecord(BusinessError):
    pass


class RecordUnavailable(BusinessError):
    pass
